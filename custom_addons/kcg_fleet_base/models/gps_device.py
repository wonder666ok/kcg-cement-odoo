from odoo import api, fields, models
from odoo.exceptions import ValidationError


class GpsDevice(models.Model):
    _name = "gps.device"
    _description = "GPS 定位设备"
    _order = "name, id"
    _check_company_auto = True

    name = fields.Char(
        string="设备编号",
        required=True,
        index=True,
        help="车载终端的编号或 IMEI，需与定位平台上登记的编号一致，否则轨迹对不上车。",
    )
    serial_number = fields.Char(string="序列号")
    sim_number = fields.Char(string="SIM 卡号")
    device_model = fields.Char(string="设备型号")
    manufacturer = fields.Char(string="设备厂商")
    vehicle_id = fields.Many2one(
        "transport.vehicle",
        string="安装车辆",
        ondelete="set null",
        index=True,
        check_company=True,
        help="设备与车辆的绑定关系只在这一侧维护，车辆表单上的设备列表是反查结果。",
    )
    vehicle_plate = fields.Char(
        related="vehicle_id.name",
        string="车牌号",
        store=False,
    )
    install_date = fields.Date(string="安装日期")
    removal_date = fields.Date(string="拆除日期")
    firmware_version = fields.Char(string="固件版本")
    state = fields.Selection(
        [
            ("stock", "库存未装"),
            ("active", "已装车"),
            ("faulty", "故障"),
            ("retired", "已报废"),
        ],
        string="设备状态",
        default="stock",
        required=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    notes = fields.Text(string="备注")
    active = fields.Boolean(string="启用", default=True)

    # provider_id（数据源）与最后定位快照由 kcg_gps_tracking 通过 _inherit 注入。
    # 不放在这里，否则 kcg_fleet_base 会反过来依赖 kcg_gps_tracking，形成循环依赖。

    _sql_constraints = [
        ("name_uniq", "UNIQUE(name)", "设备编号不能重复。"),
    ]

    @api.constrains("state", "vehicle_id")
    def _check_active_requires_vehicle(self):
        for device in self:
            if device.state == "active" and not device.vehicle_id:
                raise ValidationError(
                    "设备 %s 的状态为「已装车」时必须指定安装车辆。" % device.name
                )

    @api.constrains("state", "vehicle_id")
    def _check_single_active_device(self):
        """一辆车只能挂一个在用设备，否则同一时刻会有两条轨迹。"""
        for device in self.filtered(
            lambda d: d.state == "active" and d.vehicle_id
        ):
            siblings = device.vehicle_id.gps_device_ids.filtered(
                lambda other: other.state == "active" and other != device
            )
            if siblings:
                raise ValidationError(
                    "车辆 %s 已有在用设备 %s，请先把原设备改为故障或报废。"
                    % (device.vehicle_id.name, siblings[0].name)
                )

    @api.constrains("install_date", "removal_date")
    def _check_dates(self):
        for device in self:
            if (
                device.install_date
                and device.removal_date
                and device.removal_date < device.install_date
            ):
                raise ValidationError("拆除日期不能早于安装日期。")
