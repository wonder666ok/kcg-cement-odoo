from odoo import api, fields, models

ALERT_TYPES = [
    ("overspeed", "超速"),
    ("long_stop", "长时间停留"),
    ("route_deviation", "偏离路线"),
    ("offline", "设备离线"),
    ("geofence_in", "进入区域"),
    ("geofence_out", "离开区域"),
    ("sos", "紧急求助"),
    ("other", "其他"),
]

SEVERITY = [
    ("info", "提示"),
    ("warning", "警告"),
    ("critical", "严重"),
]

STATE = [
    ("new", "待处理"),
    ("acknowledged", "已确认"),
    ("resolved", "已处理"),
    ("ignored", "已忽略"),
]


class GpsAlert(models.Model):
    """定位告警。

    与定位表相反，告警是低频且需要人工跟进的记录，因此挂 mail.thread 留存处理过程
    是合适的。定位表绝不能这么干。
    """

    _name = "gps.alert"
    _description = "GPS 告警"
    _inherit = ["mail.thread"]
    _order = "alert_datetime desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="告警", compute="_compute_name", store=True)
    alert_type = fields.Selection(ALERT_TYPES, string="告警类型", required=True, tracking=True)
    severity = fields.Selection(SEVERITY, string="严重程度", default="warning", required=True, tracking=True)
    device_id = fields.Many2one(
        "gps.device", string="设备", ondelete="cascade", index=True, tracking=True
    )
    vehicle_id = fields.Many2one(
        "transport.vehicle",
        string="车辆",
        related="device_id.vehicle_id",
        store=True,
        index=True,
    )
    driver_id = fields.Many2one(
        "transport.driver",
        string="司机",
        related="vehicle_id.driver_id",
        store=True,
        help="取车辆当前登记的常驻司机，仅作参考——实际驾驶人可能与档案不一致。",
    )
    provider_id = fields.Many2one(
        "gps.provider", string="数据源", related="device_id.provider_id", store=True
    )
    position_id = fields.Many2one(
        "gps.position", string="触发定位点", ondelete="set null", index=True
    )
    alert_datetime = fields.Datetime(
        string="告警时间", required=True, default=fields.Datetime.now, index=True
    )
    latitude = fields.Float(string="纬度", digits=(10, 7))
    longitude = fields.Float(string="经度", digits=(10, 7))
    detail = fields.Text(string="详情")
    state = fields.Selection(STATE, string="处理状态", default="new", required=True, index=True, tracking=True)
    handled_by = fields.Many2one("res.users", string="处理人", readonly=True)
    handled_datetime = fields.Datetime(string="处理时间", readonly=True)
    resolution_note = fields.Text(string="处理说明")
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    @api.depends("alert_type", "vehicle_id", "alert_datetime")
    def _compute_name(self):
        type_labels = dict(ALERT_TYPES)
        for alert in self:
            parts = [type_labels.get(alert.alert_type, alert.alert_type or "")]
            if alert.vehicle_id:
                parts.append(alert.vehicle_id.name)
            alert.name = " ".join(part for part in parts if part) or "告警"

    def action_acknowledge(self):
        self._mark("acknowledged")

    def action_resolve(self):
        self._mark("resolved")

    def action_ignore(self):
        self._mark("ignored")

    def action_reopen(self):
        self.write(
            {
                "state": "new",
                "handled_by": False,
                "handled_datetime": False,
            }
        )

    def _mark(self, state):
        self.write(
            {
                "state": state,
                "handled_by": self.env.user.id,
                "handled_datetime": fields.Datetime.now(),
            }
        )
