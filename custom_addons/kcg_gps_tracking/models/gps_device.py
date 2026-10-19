from odoo import api, fields, models


class GpsDevice(models.Model):
    """给基础档案里的 GPS 设备补上「数据源」与「最后定位」。

    关键点：``provider_id`` 由本模块（kcg_gps_tracking）反向注入，
    而不是写在 kcg_fleet_base 的 gps_device.py 里。

    如果写在 fleet_base，fleet_base 就需要 import gps.provider，
    于是形成 kcg_fleet_base → kcg_gps_tracking 的依赖，而 gps_tracking 又依赖
    fleet_base，Odoo 加载时直接循环依赖报错。基础档案模块必须保持零外部依赖。
    """

    _inherit = "gps.device"

    provider_id = fields.Many2one(
        "gps.provider",
        string="数据源",
        ondelete="set null",
        index=True,
        help="该设备的数据由哪个平台推送。未指定时数据源无法匹配设备，定位不会入库。",
    )
    position_ids = fields.One2many("gps.position", "device_id", string="定位记录")
    alert_ids = fields.One2many("gps.alert", "device_id", string="告警")

    # 最后定位快照。之所以冗余存到设备上，而不是每次读列表时去 position 表里
    # 取每台设备的最后一条：车辆列表一屏几十台车就是几十次查询，而定位表动辄
    # 千万行，这个 N+1 会非常明显。入库时顺手更新这几个字段，读的时候零成本。
    last_position_datetime = fields.Datetime(
        string="最后定位时间", readonly=True, index=True
    )
    last_latitude = fields.Float(string="最后纬度", digits=(10, 7), readonly=True)
    last_longitude = fields.Float(string="最后经度", digits=(10, 7), readonly=True)
    last_speed_kmh = fields.Float(string="最后速度(km/h)", readonly=True)
    track_state = fields.Selection(
        [
            ("unknown", "无数据"),
            ("live", "正常"),
            ("stale", "数据陈旧"),
            ("offline", "离线"),
        ],
        string="信号状态",
        compute="_compute_track_state",
        help="超过 2 小时没有新定位标为「数据陈旧」，超过 24 小时标为「离线」。"
        "刻意不存库：该状态取决于当前时间，存下来就不会随时间变旧，"
        "设备会永远停在最后一次计算出的状态。需要按离线筛选时，"
        "请直接比较「最后定位时间」字段（搜索视图里已提供该筛选）。",
    )

    @api.depends("last_position_datetime")
    def _compute_track_state(self):
        now = fields.Datetime.now()
        for device in self:
            last = device.last_position_datetime
            if not last:
                device.track_state = "unknown"
                continue
            age_hours = (now - last).total_seconds() / 3600.0
            if age_hours > 24:
                device.track_state = "offline"
            elif age_hours > 2:
                device.track_state = "stale"
            else:
                device.track_state = "live"

    def action_view_positions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "定位记录",
            "res_model": "gps.position",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }
