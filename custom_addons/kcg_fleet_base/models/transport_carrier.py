from odoo import api, fields, models


class TransportCarrier(models.Model):
    _name = "transport.carrier"
    _description = "承运商"
    _inherit = ["mail.thread"]
    _order = "is_own_fleet desc, name, id"
    _check_company_auto = True

    name = fields.Char(string="承运商名称", required=True, tracking=True, index=True)
    code = fields.Char(
        string="编码",
        help="内部编号，运费对账时用于快速识别。",
    )
    is_own_fleet = fields.Boolean(
        string="自有车队",
        tracking=True,
        help="勾选表示车辆与司机属本公司所有，运费属内部成本而非对外应付。",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="关联业务伙伴",
        ondelete="set null",
        check_company=True,
        help="若该承运商会开具运费发票，在此关联业务伙伴，便于后续运费应付挂账。",
    )
    contact_person = fields.Char(string="联系人")
    phone = fields.Char(string="联系电话")
    email = fields.Char(string="邮箱")
    address = fields.Text(string="地址")
    registration_no = fields.Char(string="营业执照号")
    active = fields.Boolean(string="启用", default=True)
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    vehicle_ids = fields.One2many("transport.vehicle", "carrier_id", string="车辆")
    driver_ids = fields.One2many("transport.driver", "carrier_id", string="司机")
    vehicle_count = fields.Integer(string="车辆数", compute="_compute_counts")
    driver_count = fields.Integer(string="司机数", compute="_compute_counts")
    notes = fields.Text(string="备注")

    _sql_constraints = [
        (
            "code_company_uniq",
            "UNIQUE(company_id, code)",
            "同一公司下承运商编码不能重复。",
        ),
    ]

    @api.depends("vehicle_ids", "driver_ids")
    def _compute_counts(self):
        for carrier in self:
            carrier.vehicle_count = len(carrier.vehicle_ids)
            carrier.driver_count = len(carrier.driver_ids)

    def action_view_vehicles(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "车辆",
            "res_model": "transport.vehicle",
            "view_mode": "list,form",
            "domain": [("carrier_id", "=", self.id)],
            "context": {"default_carrier_id": self.id},
        }

    def action_view_drivers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "司机",
            "res_model": "transport.driver",
            "view_mode": "list,form",
            "domain": [("carrier_id", "=", self.id)],
            "context": {"default_carrier_id": self.id},
        }
