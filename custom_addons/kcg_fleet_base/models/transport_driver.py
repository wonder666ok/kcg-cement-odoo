from odoo import api, fields, models

from .fleet_common import EXPIRY_STATE_SELECTION, expiry_state


class TransportDriver(models.Model):
    _name = "transport.driver"
    _description = "司机"
    _inherit = ["mail.thread"]
    _order = "name, id"
    _check_company_auto = True

    name = fields.Char(string="司机姓名", required=True, tracking=True, index=True)
    phone = fields.Char(string="联系电话", tracking=True)
    id_number = fields.Char(
        string="证件号码",
        help="司机身份证明文件号码，用于门岗备案与运输合规留存。",
    )
    license_number = fields.Char(string="驾照号码")
    license_type = fields.Selection(
        [
            ("A1", "A1 大型客车"),
            ("A2", "A2 牵引车"),
            ("A3", "A3 城市公交车"),
            ("B1", "B1 中型客车"),
            ("B2", "B2 大型货车"),
            ("C1", "C1 小型汽车"),
            ("C2", "C2 小型自动挡汽车"),
            ("other", "其他"),
        ],
        string="准驾车型",
    )
    license_expiry = fields.Date(string="驾照到期日", tracking=True)
    license_state = fields.Selection(
        EXPIRY_STATE_SELECTION,
        string="驾照状态",
        compute="_compute_license_state",
        store=True,
        help="距到期 30 天内标为「即将到期」，已过期标为「已过期」。",
    )
    carrier_id = fields.Many2one(
        "transport.carrier",
        string="所属承运商",
        ondelete="restrict",
        index=True,
        check_company=True,
        tracking=True,
    )
    is_own_staff = fields.Boolean(
        related="carrier_id.is_own_fleet",
        string="自有司机",
        store=True,
        readonly=True,
    )
    # 常驻关系只在车辆侧维护（transport.vehicle.driver_id），
    # 这里用 One2many 回读，避免两边各存一份互相同步、随后不一致。
    vehicle_ids = fields.One2many("transport.vehicle", "driver_id", string="常驻车辆")
    current_vehicle_id = fields.Many2one(
        "transport.vehicle",
        string="当前车辆",
        compute="_compute_current_vehicle",
        # 存库的理由同车辆上的 current_gps_device_id：非存储计算字段无法用于
        # domain，存下来也方便以后按车辆筛司机。
        store=True,
    )
    state = fields.Selection(
        [
            ("available", "待命"),
            ("on_trip", "在途"),
            ("rest", "休息"),
            ("inactive", "停用"),
        ],
        string="状态",
        default="available",
        required=True,
        tracking=True,
    )
    hire_date = fields.Date(string="入职/合作起始日")
    emergency_contact = fields.Char(string="紧急联系人")
    emergency_phone = fields.Char(string="紧急联系电话")
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="联系人",
        ondelete="restrict",
        index=True,
        help="司机在「联系人」模块里的对应记录，自动创建并归入「司机」分类，"
             "方便在联系人里把司机单独筛出来。",
    )
    notes = fields.Text(string="备注")
    active = fields.Boolean(string="启用", default=True)

    # ------------------------------------------------------------------
    # 联系人同步：司机 -> res.partner（带「司机」分类标签）
    # ------------------------------------------------------------------
    DRIVER_CATEGORY_NAME = "司机"

    @api.model
    def _get_driver_category(self):
        """取（或建）「司机」联系人分类标签，不绑公司，全公司共享。"""
        Category = self.env["res.partner.category"].sudo()
        category = Category.search(
            [("name", "=", self.DRIVER_CATEGORY_NAME)], limit=1
        )
        if not category:
            category = Category.create({"name": self.DRIVER_CATEGORY_NAME})
        return category

    def _prepare_partner_vals(self):
        self.ensure_one()
        return {
            "name": self.name,
            "phone": self.phone or False,
            "company_type": "person",
            "category_id": [(6, 0, self._get_driver_category().ids)],
            "comment": "由司机档案自动同步，请勿在此修改姓名/电话，以司机档案为准。",
        }

    def _ensure_partner_record(self):
        """给司机补齐联系人记录；已有联系人的司机跳过。"""
        for driver in self.filtered(lambda d: not d.partner_id):
            driver.partner_id = (
                self.env["res.partner"].sudo().create(driver._prepare_partner_vals())
            )

    @api.model_create_multi
    def create(self, vals_list):
        drivers = super().create(vals_list)
        drivers._ensure_partner_record()
        return drivers

    def write(self, vals):
        # 改名前先记旧姓名，用于判断联系人是否由本模块自动创建（姓名一致才跟改，
        # 避免覆盖手工关联的既有联系人）。
        old_names = dict(zip(self.ids, self.mapped("name"))) if "name" in vals else {}
        res = super().write(vals)
        if "name" in vals or "phone" in vals:
            for driver in self:
                partner = driver.partner_id
                if not partner:
                    continue
                partner_vals = {}
                if "name" in vals and partner.name == old_names.get(driver.id):
                    partner_vals["name"] = driver.name
                if "phone" in vals:
                    partner_vals["phone"] = driver.phone or False
                if partner_vals:
                    partner.sudo().write(partner_vals)
        return res

    def action_view_partner(self):
        self.ensure_one()
        self._ensure_partner_record()
        return {
            "type": "ir.actions.act_window",
            "name": "联系人",
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": self.partner_id.id,
            "target": "current",
        }

    @api.depends("license_expiry")
    def _compute_license_state(self):
        today = fields.Date.context_today(self)
        for driver in self:
            driver.license_state = expiry_state(driver.license_expiry, today)

    @api.depends("vehicle_ids", "vehicle_ids.state")
    def _compute_current_vehicle(self):
        for driver in self:
            usable = driver.vehicle_ids.filtered(lambda v: v.state != "retired")
            driver.current_vehicle_id = usable[:1]

    def action_view_vehicles(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "常驻车辆",
            "res_model": "transport.vehicle",
            "view_mode": "list,form",
            "domain": [("driver_id", "=", self.id)],
            "context": {"default_driver_id": self.id},
        }
