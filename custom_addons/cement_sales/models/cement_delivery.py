from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
    quantity = fields.Float(string="交货数量")
    bag_count = fields.Float(string="袋数")
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
    tracking_reference = fields.Char(string="运输参考号")
    scheduled_datetime = fields.Datetime(string="计划发车时间")
    loading_date = fields.Datetime(string="装车日期")
    departure_date = fields.Datetime(string="出发时间")
    actual_delivery_date = fields.Datetime(string="实际送达时间")
    delivery_contact = fields.Char(string="收货联系人")
    delivery_phone = fields.Char(string="收货电话")
    receiver_name = fields.Char(string="签收人")
    receiver_phone = fields.Char(string="签收人电话")
    received_quantity = fields.Float(string="实际签收数量")
    received_bag_count = fields.Float(string="实际签收袋数")
    shortage_quantity = fields.Float(string="短少数量")
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

    @api.model
    def _sale_order_default_values(self, sale_order):
        values = {}
        if sale_order.cement_customer_id:
            values["customer_id"] = sale_order.cement_customer_id.id
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
        return super().create(vals_list)

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if not self.sale_order_id:
            return
        for field_name, value in self._sale_order_default_values(
            self.sale_order_id
        ).items():
            if not self[field_name]:
                self[field_name] = value

    def write(self, vals):
        if "state" not in vals:
            return super().write(vals)

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
