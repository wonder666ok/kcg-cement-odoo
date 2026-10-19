import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .fleet_common import EXPIRY_STATE_SELECTION, expiry_state


class TransportVehicle(models.Model):
    _name = "transport.vehicle"
    _description = "运输车辆"
    _inherit = ["mail.thread"]
    _order = "name, id"
    _check_company_auto = True

    name = fields.Char(string="车牌号", required=True, tracking=True, index=True)
    plate_normalized = fields.Char(
        string="车牌规范值",
        compute="_compute_plate_normalized",
        store=True,
        index=True,
        help="车牌去掉空格、连字符并转大写后的结果。"
        "「GX 396-22」「gx39622」会归一到同一个值，"
        "因此这类写法差异不会再被当成两辆不同的车。",
    )
    vehicle_type = fields.Selection(
        [
            ("bulk_tanker", "散装罐车"),
            ("flatbed", "袋装平板车"),
            ("dump", "自卸车"),
            ("tipper", "翻斗车"),
            ("other", "其他"),
        ],
        string="车辆类型",
        default="flatbed",
        tracking=True,
    )
    carrier_id = fields.Many2one(
        "transport.carrier",
        string="所属承运商",
        ondelete="restrict",
        index=True,
        check_company=True,
        tracking=True,
    )
    is_own_fleet = fields.Boolean(
        related="carrier_id.is_own_fleet",
        string="自有车辆",
        store=True,
        readonly=True,
    )
    driver_id = fields.Many2one(
        "transport.driver",
        string="常驻司机",
        ondelete="set null",
        check_company=True,
        tracking=True,
    )
    capacity_tons = fields.Float(
        string="核定载重(吨)",
        tracking=True,
        help="行驶证上的核定载质量。决定单车能拉多少袋，派车时可用来校验是否超载。",
    )
    bag_weight_kg = fields.Float(
        string="每袋重量(kg)",
        default=50.0,
        help="该车常运的包装规格。散装水泥或不同包装（40kg/50kg）在此调整，"
        "袋数容量会随之变化。",
    )
    capacity_bags = fields.Float(
        string="核定袋数",
        compute="_compute_capacity_bags",
        store=True,
        digits=(16, 0),
        help="核定载重 ÷ 每袋重量，只作参考容量，不参与订单金额。",
    )
    brand_model = fields.Char(string="品牌型号")
    manufacture_year = fields.Integer(string="出厂年份")
    vin = fields.Char(string="车架号")
    engine_no = fields.Char(string="发动机号")
    odometer_km = fields.Float(string="当前里程(km)")
    gps_device_ids = fields.One2many("gps.device", "vehicle_id", string="GPS 设备")
    current_gps_device_id = fields.Many2one(
        "gps.device",
        string="在用 GPS 设备",
        compute="_compute_current_gps_device",
        # 必须存库：非存储的计算字段不能用于 domain，搜索视图里
        # 「未装 GPS」这个筛选项会直接让视图加载失败。
        store=True,
    )
    gps_device_count = fields.Integer(
        string="设备数", compute="_compute_gps_device_count"
    )
    insurance_expiry = fields.Date(string="保险到期日", tracking=True)
    insurance_state = fields.Selection(
        EXPIRY_STATE_SELECTION,
        string="保险状态",
        compute="_compute_expiry_states",
        store=True,
    )
    inspection_expiry = fields.Date(string="年检到期日", tracking=True)
    inspection_state = fields.Selection(
        EXPIRY_STATE_SELECTION,
        string="年检状态",
        compute="_compute_expiry_states",
        store=True,
    )
    road_license_expiry = fields.Date(string="行驶证到期日", tracking=True)
    road_license_state = fields.Selection(
        EXPIRY_STATE_SELECTION,
        string="行驶证状态",
        compute="_compute_expiry_states",
        store=True,
    )
    state = fields.Selection(
        [
            ("available", "可用"),
            ("in_transit", "运输中"),
            ("maintenance", "维修中"),
            ("retired", "已停用"),
        ],
        string="状态",
        default="available",
        required=True,
        index=True,
        tracking=True,
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

    _sql_constraints = [
        (
            "plate_company_uniq",
            "UNIQUE(company_id, plate_normalized)",
            "同一公司下车牌号不能重复。系统已忽略空格与大小写差异，"
            "若提示重复说明这辆车已经建档。",
        ),
    ]

    @api.depends("name")
    def _compute_plate_normalized(self):
        for vehicle in self:
            raw = vehicle.name or ""
            vehicle.plate_normalized = re.sub(r"[^A-Z0-9]", "", raw.upper())

    @api.depends("capacity_tons", "bag_weight_kg")
    def _compute_capacity_bags(self):
        for vehicle in self:
            if vehicle.bag_weight_kg:
                vehicle.capacity_bags = (
                    vehicle.capacity_tons * 1000.0 / vehicle.bag_weight_kg
                )
            else:
                # 每袋重量未维护（例如散装），不折算袋数，避免除零或输出错误数字。
                vehicle.capacity_bags = 0.0

    @api.depends("gps_device_ids", "gps_device_ids.state")
    def _compute_current_gps_device(self):
        for vehicle in self:
            active_devices = vehicle.gps_device_ids.filtered(
                lambda device: device.state == "active"
            )
            vehicle.current_gps_device_id = active_devices[:1]

    @api.depends("gps_device_ids")
    def _compute_gps_device_count(self):
        for vehicle in self:
            vehicle.gps_device_count = len(vehicle.gps_device_ids)

    @api.depends(
        "insurance_expiry", "inspection_expiry", "road_license_expiry"
    )
    def _compute_expiry_states(self):
        today = fields.Date.context_today(self)
        for vehicle in self:
            vehicle.insurance_state = expiry_state(vehicle.insurance_expiry, today)
            vehicle.inspection_state = expiry_state(vehicle.inspection_expiry, today)
            vehicle.road_license_state = expiry_state(
                vehicle.road_license_expiry, today
            )

    @api.constrains("manufacture_year")
    def _check_manufacture_year(self):
        current_year = fields.Date.context_today(self).year
        for vehicle in self:
            if vehicle.manufacture_year and not (
                1950 <= vehicle.manufacture_year <= current_year + 1
            ):
                raise ValidationError(
                    "出厂年份 %(year)s 不合理，应为 1950 到 %(limit)s 之间。"
                    % {"year": vehicle.manufacture_year, "limit": current_year + 1}
                )

    @api.constrains("capacity_tons", "bag_weight_kg")
    def _check_capacity(self):
        for vehicle in self:
            if vehicle.capacity_tons < 0 or vehicle.bag_weight_kg < 0:
                raise ValidationError("核定载重与每袋重量不能为负数。")

    def action_view_gps_devices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "GPS 设备",
            "res_model": "gps.device",
            "view_mode": "list,form",
            "domain": [("vehicle_id", "=", self.id)],
            "context": {"default_vehicle_id": self.id},
        }
