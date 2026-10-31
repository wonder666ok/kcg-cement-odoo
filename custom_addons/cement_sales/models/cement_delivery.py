from odoo import api, fields, models, _
from odoo.exceptions import UserError

import re


class CementDelivery(models.Model):
    _name = "cement.delivery"
    _description = "水泥交付与运输记录"
    _order = "delivery_date desc, id desc"

    _ALLOWED_STATE_TRANSITIONS = {
        "draft": {"scheduled", "cancelled"},
        "scheduled": {"in_transit", "cancelled"},
        "in_transit": {"delivered", "cancelled"},
        "delivered": set(),
        "cancelled": {"draft"},
    }
    _STATE_LABELS = {
        "draft": "待安排",
        "scheduled": "已安排",
        "in_transit": "运输中",
        "delivered": "已送达",
        "cancelled": "已取消",
    }

    sale_order_id = fields.Many2one(
        "sale.order",
        string="销售订单",
        required=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="原生发货单",
        ondelete="set null",
        domain="[('sale_id', '=', sale_order_id)]",
    )
    customer_id = fields.Many2one(
        "cement.customer",
        string="水泥客户",
        required=True,
        ondelete="restrict",
        index=True,
    )
    delivery_date = fields.Date(
        string="交货日期", required=True, default=fields.Date.context_today
    )
    delivery_region = fields.Char(string="交货地区")
    delivery_address = fields.Text(string="交货地址")
    quantity = fields.Float(
        string="交货数量(袋)",
        help="按袋计数。水泥按袋销售，1 袋 = 50kg，即 20 袋 = 1 吨。",
    )
    weight_tons = fields.Float(
        string="吨数",
        compute="_compute_weight_tons",
        store=True,
        digits=(16, 3),
        help="把交货数量折算成吨，仅用于显示与对账。订单金额与这一列无关。",
    )
    cement_grade = fields.Char(string="水泥等级")
    transport_type = fields.Selection(
        [
            ("truck", "卡车"),
            ("customer_pickup", "客户自提"),
            ("other", "其他"),
        ],
        string="运输方式",
    )
    vehicle_number = fields.Char(string="车牌号")
    driver_name = fields.Char(string="司机")
    transporter_name = fields.Char(string="承运人/运输公司")
    transporter_phone = fields.Char(string="承运人电话")
    driver_phone = fields.Char(string="司机电话")
    # ---- 运输档案关联 ----
    # 从运输档案（kcg_fleet_base）选承运商/车辆/司机，自由文本字段自动带出；
    # 未建档的临时车辆仍可手工填文本，保存后会按承运商自动归档，下次可直接选。
    transport_carrier_id = fields.Many2one(
        "transport.carrier",
        string="承运商",
        ondelete="restrict",
        index=True,
        check_company=True,
        help="从运输档案选择承运商，车辆、司机下拉会按此承运商过滤；"
             "「承运人/运输公司」文本自动带出。",
    )
    transport_vehicle_id = fields.Many2one(
        "transport.vehicle",
        string="车辆",
        ondelete="restrict",
        index=True,
        check_company=True,
        domain="[('carrier_id', '=?', transport_carrier_id)]",
        help="从运输档案选车，自动填车牌号；车辆的常驻司机也会一并带出。",
    )
    transport_driver_id = fields.Many2one(
        "transport.driver",
        string="司机",
        ondelete="restrict",
        index=True,
        check_company=True,
        domain="[('carrier_id', '=?', transport_carrier_id)]",
        help="从运输档案选司机，自动填司机姓名与电话。",
    )
    tracking_reference = fields.Char(string="运输参考号")
    scheduled_datetime = fields.Datetime(string="计划发车时间")
    loading_date = fields.Datetime(string="装车日期")
    departure_date = fields.Datetime(string="出发时间")
    actual_delivery_date = fields.Datetime(string="实际送达时间")
    delivery_contact = fields.Char(string="收货联系人")
    delivery_phone = fields.Char(string="收货电话")
    receiver_name = fields.Char(string="签收人")
    receiver_phone = fields.Char(string="签收人电话")
    received_quantity = fields.Float(string="实际签收数量(袋)")
    shortage_quantity = fields.Float(
        string="短少数量",
        compute="_compute_quantity_gap",
        store=True,
        help="发货数量 − 实际签收数量；未签收或超收时为 0。",
    )
    over_received_quantity = fields.Float(
        string="超收数量",
        compute="_compute_quantity_gap",
        store=True,
        help="实际签收数量超出发货数量的部分；未超收时为 0。超收不高亮拦截，仅供复核。",
    )
    damage_quantity = fields.Float(string="破损数量")
    proof_of_delivery = fields.Binary(string="签收凭证", attachment=True)
    proof_filename = fields.Char(string="签收凭证文件名")
    delivery_notes = fields.Text(string="运输备注")
    issue_note = fields.Text(string="运输异常说明")
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        related="sale_order_id.currency_id",
        readonly=True,
    )
    freight_amount = fields.Monetary(string="运费", currency_field="currency_id")
    freight_payer = fields.Selection(
        [
            ("customer", "客户"),
            ("company", "公司"),
            ("shared", "双方承担"),
        ],
        string="运费承担方",
    )
    state = fields.Selection(
        [
            ("draft", "待安排"),
            ("scheduled", "已安排"),
            ("in_transit", "运输中"),
            ("delivered", "已送达"),
            ("cancelled", "已取消"),
        ],
        string="运输状态",
        required=True,
        default="draft",
        index=True,
    )
    delivery_days = fields.Integer(
        string="运输天数", compute="_compute_delivery_days"
    )
    notes = fields.Text(string="交付备注")

    @api.depends("departure_date", "actual_delivery_date")
    def _compute_delivery_days(self):
        for delivery in self:
            if delivery.departure_date and delivery.actual_delivery_date:
                duration = delivery.actual_delivery_date - delivery.departure_date
                delivery.delivery_days = duration.days
            else:
                delivery.delivery_days = 0

    @api.depends("quantity", "received_quantity")
    def _compute_quantity_gap(self):
        for delivery in self:
            if not delivery.received_quantity:
                # 尚未签收时不产生短少/超收，否则所有在途单据都会被标成全额短少。
                delivery.shortage_quantity = 0.0
                delivery.over_received_quantity = 0.0
                continue
            gap = (delivery.quantity or 0.0) - delivery.received_quantity
            delivery.shortage_quantity = max(gap, 0.0)
            delivery.over_received_quantity = max(-gap, 0.0)

    def _get_cargo_uom(self):
        """交货数量的计量单位：跟随订单行上的产品单位；取不到时按水泥默认的「袋」。"""
        self.ensure_one()
        line = self.sale_order_id.order_line.filtered(
            lambda item: not item.display_type
        )[:1]
        if line and line.product_uom:
            return line.product_uom
        return self.env.ref("cement_sales.uom_bag", raise_if_not_found=False)

    @api.depends("quantity", "sale_order_id.order_line.product_uom")
    def _compute_weight_tons(self):
        ton_uom = self.env.ref("uom.product_uom_ton", raise_if_not_found=False)
        for delivery in self:
            uom = delivery._get_cargo_uom()
            if (
                not ton_uom
                or not uom
                or not delivery.quantity
                or uom.category_id != ton_uom.category_id
            ):
                # 计量单位不是重量单位时无法折算，直接给 0 而不是抛错。
                delivery.weight_tons = 0.0
                continue
            delivery.weight_tons = uom._compute_quantity(
                delivery.quantity, ton_uom, round=False
            )

    @api.model
    def _sale_order_default_values(self, sale_order):
        values = {}
        if sale_order.cement_customer_id:
            values["customer_id"] = sale_order.cement_customer_id.id
        if sale_order.company_id:
            # 交付记录跟随销售订单所属公司，避免多公司数据串味。
            values["company_id"] = sale_order.company_id.id
        if sale_order.delivery_region:
            values["delivery_region"] = sale_order.delivery_region
        if sale_order.delivery_address:
            values["delivery_address"] = sale_order.delivery_address

        grades = {
            grade
            for grade in sale_order.order_line.mapped(
                "product_id.product_tmpl_id.cement_grade"
            )
            if grade
        }
        if len(grades) == 1:
            values["cement_grade"] = grades.pop()
        return values

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = {
            values.get("sale_order_id")
            for values in vals_list
            if values.get("sale_order_id")
        }
        orders = {
            order.id: order
            for order in self.env["sale.order"].browse(order_ids)
        }
        for values in vals_list:
            order = orders.get(values.get("sale_order_id"))
            if not order:
                continue
            for field_name, value in self._sale_order_default_values(order).items():
                if not values.get(field_name):
                    values[field_name] = value
        deliveries = super().create(vals_list)
        deliveries._sync_transport_registry()
        return deliveries

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if not self.sale_order_id:
            return
        for field_name, value in self._sale_order_default_values(
            self.sale_order_id
        ).items():
            if not self[field_name]:
                self[field_name] = value

    # ------------------------------------------------------------------
    # 运输档案联动
    # ------------------------------------------------------------------
    @api.onchange("transport_carrier_id")
    def _onchange_transport_carrier_id(self):
        for delivery in self:
            carrier = delivery.transport_carrier_id
            if not carrier:
                continue
            delivery.transporter_name = carrier.name
            delivery.transporter_phone = carrier.phone or False
            # 换承运商后，原车辆/司机若不属于该承运商则清空，避免张冠李戴
            if (
                delivery.transport_vehicle_id
                and delivery.transport_vehicle_id.carrier_id != carrier
            ):
                delivery.transport_vehicle_id = False
                delivery.vehicle_number = False
            if (
                delivery.transport_driver_id
                and delivery.transport_driver_id.carrier_id != carrier
            ):
                delivery.transport_driver_id = False
                delivery.driver_name = False
                delivery.driver_phone = False

    @api.onchange("transport_vehicle_id")
    def _onchange_transport_vehicle_id(self):
        for delivery in self:
            vehicle = delivery.transport_vehicle_id
            if not vehicle:
                continue
            delivery.vehicle_number = vehicle.name
            if vehicle.carrier_id:
                delivery.transport_carrier_id = vehicle.carrier_id
                delivery.transporter_name = vehicle.carrier_id.name
                delivery.transporter_phone = vehicle.carrier_id.phone or False
            if vehicle.driver_id:
                delivery.transport_driver_id = vehicle.driver_id

    @api.onchange("transport_driver_id")
    def _onchange_transport_driver_id(self):
        for delivery in self:
            driver = delivery.transport_driver_id
            if not driver:
                continue
            delivery.driver_name = driver.name
            delivery.driver_phone = driver.phone or False
            if driver.carrier_id and not delivery.transport_carrier_id:
                delivery.transport_carrier_id = driver.carrier_id

    @api.model
    def _match_transport_carrier(self, name):
        """把交付单上的承运人文本匹配到运输档案里的承运商。"""
        clean = (name or "").strip()
        if not clean:
            return self.env["transport.carrier"]
        Carrier = self.env["transport.carrier"]
        carrier = Carrier.search([("name", "=ilike", clean)], limit=1)
        if not carrier and clean.upper() == "KCG":
            # 交付单上简写「KCG」，对应自有车队承运商
            carrier = Carrier.search(
                [("is_own_fleet", "=", True), ("name", "ilike", "KCG")], limit=1
            ) or Carrier.search([("is_own_fleet", "=", True)], limit=1)
        if not carrier:
            carrier = Carrier.search([("name", "ilike", clean)], limit=1)
        return carrier

    def _sync_transport_registry(self):
        """把交付单上手工填写的车辆/司机按承运商自动归档。

        - 车辆按「公司 + 规范车牌」查重，查不到就建档（挂在匹配到的承运商下）；
        - 司机按「承运商 + 姓名（忽略大小写）」查重，查不到就建档并带电话；
        - 同时把本单的承运商/车辆/司机档案字段补上，供下次直接下拉调用。
        客户自提（customer_pickup）不走承运商，跳过。
        """
        if self.env.context.get("skip_cement_transport_sync"):
            return
        for delivery in self:
            if delivery.transport_type == "customer_pickup":
                continue
            plate = (delivery.vehicle_number or "").strip()
            carrier = self._match_transport_carrier(delivery.transporter_name)
            if not plate or not carrier:
                continue
            Vehicle = self.env["transport.vehicle"].with_context(
                skip_cement_transport_sync=True
            )
            Driver = self.env["transport.driver"].with_context(
                skip_cement_transport_sync=True
            )
            plate_normalized = re.sub(r"[^A-Z0-9]", "", plate.upper())
            vehicle = Vehicle.search(
                [
                    ("company_id", "=", delivery.company_id.id),
                    ("plate_normalized", "=", plate_normalized),
                ],
                limit=1,
            )
            if not vehicle:
                vehicle = Vehicle.create(
                    {
                        "name": plate,
                        "carrier_id": carrier.id,
                        "company_id": delivery.company_id.id,
                        "notes": "由交付单自动建档",
                    }
                )
            driver = False
            driver_name = (delivery.driver_name or "").strip()
            if driver_name:
                driver = Driver.search(
                    [("carrier_id", "=", carrier.id), ("name", "=ilike", driver_name)],
                    limit=1,
                )
                if not driver:
                    driver = Driver.create(
                        {
                            "name": driver_name,
                            "phone": delivery.driver_phone or False,
                            "carrier_id": carrier.id,
                            "company_id": delivery.company_id.id,
                            "notes": "由交付单自动建档",
                        }
                    )
                elif not driver.phone and delivery.driver_phone:
                    driver.phone = delivery.driver_phone
            if vehicle and driver and not vehicle.driver_id:
                vehicle.driver_id = driver
            updates = {}
            if delivery.transport_carrier_id != carrier:
                updates["transport_carrier_id"] = carrier.id
            if delivery.transport_vehicle_id != vehicle:
                updates["transport_vehicle_id"] = vehicle.id
            if driver and delivery.transport_driver_id != driver:
                updates["transport_driver_id"] = driver.id
            if updates:
                super(CementDelivery, delivery).write(updates)

    def write(self, vals):
        if "state" not in vals:
            res = super().write(vals)
            self._sync_transport_registry()
            return res

        target_state = vals["state"]
        for delivery in self:
            if target_state == delivery.state:
                continue
            if target_state not in self._ALLOWED_STATE_TRANSITIONS.get(
                delivery.state, set()
            ):
                current_label = self._STATE_LABELS.get(delivery.state, delivery.state)
                target_label = self._STATE_LABELS.get(target_state, target_state)
                raise UserError(
                    _("不允许将运输状态从“%s”变更为“%s”。")
                    % (current_label, target_label)
                )

        now = fields.Datetime.now()
        for delivery in self:
            values = dict(vals)
            if (
                target_state == "in_transit"
                and not delivery.departure_date
                and not values.get("departure_date")
            ):
                values["departure_date"] = now
            elif (
                target_state == "delivered"
                and not delivery.actual_delivery_date
                and not values.get("actual_delivery_date")
            ):
                values["actual_delivery_date"] = now
            super(CementDelivery, delivery).write(values)
        self._sync_transport_registry()
        return True

    def _run_state_action(self, expected_state, target_state):
        for delivery in self:
            if delivery.state != expected_state:
                raise UserError(
                    _("当前运输状态为“%s”，无法执行此操作。")
                    % self._STATE_LABELS.get(delivery.state, delivery.state)
                )
            delivery.write({"state": target_state})
        return True

    def action_schedule_transport(self):
        return self._run_state_action("draft", "scheduled")

    def action_start_transport(self):
        return self._run_state_action("scheduled", "in_transit")

    def action_mark_transport_delivered(self):
        return self._run_state_action("in_transit", "delivered")

    def action_cancel_transport(self):
        for delivery in self:
            if delivery.state not in ("draft", "scheduled", "in_transit"):
                raise UserError(
                    _("当前运输状态不允许取消运输。")
                )
            delivery.write({"state": "cancelled"})
        return True

    def action_reset_transport(self):
        return self._run_state_action("cancelled", "draft")

    # Keep the previous button method names callable for compatibility.
    def action_schedule(self):
        return self.action_schedule_transport()

    def action_mark_delivered(self):
        return self.action_mark_transport_delivered()

    def action_cancel_delivery(self):
        return self.action_cancel_transport()

    def action_reset_draft(self):
        return self.action_reset_transport()
