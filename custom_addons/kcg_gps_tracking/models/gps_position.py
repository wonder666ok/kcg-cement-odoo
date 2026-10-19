import datetime
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

#: 单条 INSERT 语句最多写入多少行。18 列 × 1000 行 = 18000 个占位符，
#: 仍远低于 PostgreSQL 单语句 65535 个参数的上限，同时避免语句过大。
INSERT_BATCH_SIZE = 1000

#: 清理保留策略每次删除的上限，避免一个长事务把整张表锁住。
PURGE_BATCH_SIZE = 20000

#: 定位数据的默认保留天数
DEFAULT_RETENTION_DAYS = 90

#: 写入定位时涉及的全部列，顺序必须与 _prepare_position_rows 的输出一致
INSERT_COLUMNS = (
    "device_id",
    "vehicle_id",
    "company_id",
    "provider_id",
    "position_datetime",
    "latitude",
    "longitude",
    "altitude",
    "speed_kmh",
    "heading",
    "odometer_km",
    "ignition",
    "address",
    "source",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
)


class GpsPosition(models.Model):
    _name = "gps.position"
    _description = "GPS 定位记录"
    _order = "position_datetime desc, id desc"
    _rec_name = "position_datetime"

    # 刻意不继承 mail.thread。定位是机器产生的时序数据，每条挂一条消息会让
    # mail_message 表以每天几十万条的速度膨胀，远超定位表本身。

    device_id = fields.Many2one(
        "gps.device",
        string="设备",
        required=True,
        ondelete="cascade",
        index=True,
    )
    # 下面三个都是从设备带出来的冗余列，用 store=True 落库：
    # 1. 记录规则与 domain 只能作用在真实列上，非存储的计算字段挂不上多公司规则；
    # 2. 按车辆、公司、数据源筛选是最高频的查询，冗余一份能直接走索引。
    vehicle_id = fields.Many2one(
        "transport.vehicle",
        string="车辆",
        related="device_id.vehicle_id",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        related="device_id.company_id",
        store=True,
        index=True,
    )
    provider_id = fields.Many2one(
        "gps.provider",
        string="数据源",
        related="device_id.provider_id",
        store=True,
        index=True,
    )
    position_datetime = fields.Datetime(
        string="定位时间",
        required=True,
        index=True,
        help="统一按 UTC 存储，界面按用户时区显示。",
    )
    latitude = fields.Float(string="纬度", digits=(10, 7), required=True)
    longitude = fields.Float(string="经度", digits=(10, 7), required=True)
    altitude = fields.Float(string="海拔(m)", digits=(10, 2))
    speed_kmh = fields.Float(string="速度(km/h)", digits=(10, 2))
    heading = fields.Float(string="方向角", digits=(5, 1), help="正北为 0，顺时针 0–360。")
    odometer_km = fields.Float(string="里程(km)", digits=(16, 1))
    ignition = fields.Boolean(string="点火", help="ACC 状态，用于区分行驶与停车。")
    address = fields.Char(string="位置描述", help="逆地理编码结果，由平台提供或后续补齐。")
    source = fields.Selection(
        [
            ("device", "设备直传"),
            ("provider", "平台推送"),
            ("manual", "手工录入"),
        ],
        string="来源",
        default="provider",
        required=True,
    )
    alert_ids = fields.One2many("gps.alert", "position_id", string="告警")

    _sql_constraints = [
        (
            "device_datetime_uniq",
            "UNIQUE(device_id, position_datetime)",
            "同一设备在同一时刻已有一条定位记录。"
            "该唯一约束同时用于承担平台断线重推时的幂等去重。",
        ),
    ]

    # ------------------------------------------------------------------
    # 入库
    # ------------------------------------------------------------------
    @api.model
    def _to_datetime(self, value):
        """把各种时间写法统一成 Odoo 的朴素 UTC datetime。"""
        if value is None or value == "":
            return None
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, (int, float)):
            # 多数平台用 Unix 时间戳；大于 1e11 的按毫秒处理
            seconds = float(value) / 1000.0 if float(value) > 1e11 else float(value)
            try:
                return datetime.datetime.fromtimestamp(
                    seconds, tz=datetime.timezone.utc
                ).replace(tzinfo=None)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(value, str):
            cleaned = value.strip().replace("Z", "").replace("T", " ")
            try:
                return fields.Datetime.to_datetime(cleaned)
            except (ValueError, TypeError):
                return None
        return None

    @api.model
    def _is_valid_coordinate(self, latitude, longitude):
        """挡住平台把未定位状态写成 0,0 或哨兵值的情况。"""
        if latitude is None or longitude is None:
            return False
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return False
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            return False
        # 几内亚湾上的 0,0 在设备未定位时极常见，几乎必然是无效点
        return not (abs(latitude) < 1e-9 and abs(longitude) < 1e-9)

    @api.model
    def _prepare_position_rows(self, values_list, provider=None):
        """把字典列表转成待插入的元组列表，并补上设备带出来的冗余列。"""
        device_ids = {
            values.get("device_id")
            for values in values_list
            if values.get("device_id")
        }
        if not device_ids:
            return []
        devices = self.env["gps.device"].sudo().browse(sorted(device_ids)).exists()
        snapshot = {
            device.id: (
                device.vehicle_id.id or None,
                device.company_id.id or None,
                device.provider_id.id or None,
            )
            for device in devices
        }
        now = fields.Datetime.now()
        uid = self.env.uid
        rows = []
        for values in values_list:
            device_id = values.get("device_id")
            if device_id not in snapshot:
                continue
            position_datetime = self._to_datetime(values.get("position_datetime"))
            latitude = values.get("latitude")
            longitude = values.get("longitude")
            if position_datetime is None or not self._is_valid_coordinate(
                latitude, longitude
            ):
                continue
            vehicle_id, company_id, provider_id = snapshot[device_id]
            if provider and not provider_id:
                provider_id = provider.id
            heading = values.get("heading") or 0.0
            rows.append(
                (
                    device_id,
                    vehicle_id,
                    company_id,
                    provider_id,
                    position_datetime,
                    float(latitude),
                    float(longitude),
                    values.get("altitude") or 0.0,
                    values.get("speed_kmh") or 0.0,
                    float(heading) % 360.0,
                    values.get("odometer_km") or 0.0,
                    bool(values.get("ignition")),
                    (values.get("address") or "")[:255] or None,
                    values.get("source") or "provider",
                    uid,
                    now,
                    uid,
                    now,
                )
            )
        return rows

    @api.model
    def _ingest_positions(self, values_list, provider=None):
        """批量写入定位点，返回实际新增的条数。

        用原生 ``INSERT ... ON CONFLICT DO NOTHING`` 而不是逐条 ``create``，原因：

        1. **幂等**。第三方平台断线重连后普遍会重推同一时间段的数据，
           唯一索引配合 DO NOTHING 天然去重，不需要额外的存在性检查。
        2. **性能**。逐条 create 意味着每条都跑一遍 ORM 校验、取号、缓存失效。
           7 辆车按 10 秒一个点算每天 6 万条，50 辆车就是 43 万条，ORM 撑不住。
        """
        if not values_list:
            return 0
        rows = self._prepare_position_rows(values_list, provider=provider)
        if not rows:
            return 0

        placeholders = "(" + ", ".join(["%s"] * len(INSERT_COLUMNS)) + ")"
        columns = ", ".join(INSERT_COLUMNS)
        inserted = 0
        touched_devices = set()
        for start in range(0, len(rows), INSERT_BATCH_SIZE):
            batch = rows[start : start + INSERT_BATCH_SIZE]
            query = (
                "INSERT INTO gps_position (%s) VALUES %s "
                "ON CONFLICT (device_id, position_datetime) DO NOTHING"
                % (columns, ", ".join([placeholders] * len(batch)))
            )
            self.env.cr.execute(
                query, [value for row in batch for value in row]
            )
            inserted += self.env.cr.rowcount
            touched_devices.update(row[0] for row in batch)

        if touched_devices:
            self._refresh_device_snapshots(touched_devices)
        _logger.info(
            "GPS 定位入库：提交 %s 条，实际新增 %s 条（其余为重复推送）",
            len(rows),
            inserted,
        )
        return inserted

    @api.model
    def _resolve_device_ids(self, values_list):
        """把适配器输出的 device_code 换成设备 id，丢弃对不上设备的记录。

        对不上的记录一律丢弃而不是新建设备：平台上的设备清单常包含已拆机、
        别家公司或测试用的终端，凭推送内容自动建设备档案会把主数据搞乱。
        """
        codes = {
            values.get("device_code") or values.get("device")
            for values in values_list
        }
        codes.discard(None)
        if not codes:
            return []
        devices = self.env["gps.device"].sudo().search([("name", "in", list(codes))])
        device_by_code = {device.name: device.id for device in devices}
        resolved = []
        unknown = set()
        for values in values_list:
            code = values.get("device_code") or values.get("device")
            device_id = device_by_code.get(code)
            if not device_id:
                if code not in unknown:
                    unknown.add(code)
                    _logger.warning("GPS 定位：设备编号 %s 未建档，已丢弃该条数据", code)
                continue
            row = dict(values)
            row["device_id"] = device_id
            resolved.append(row)
        return resolved

    @api.model
    def _ingest_from_provider(self, values_list, provider):
        """适配器输出的字典列表入库（含设备编号解析）。"""
        resolved = self._resolve_device_ids(values_list)
        return self._ingest_positions(resolved, provider=provider)

    @api.model
    def _refresh_device_snapshots(self, device_ids):
        """刷新设备的最后定位快照。"""
        for device in self.env["gps.device"].sudo().browse(sorted(device_ids)):
            latest = self.search(
                [("device_id", "=", device.id)],
                order="position_datetime desc",
                limit=1,
            )
            if latest:
                device.write(
                    {
                        "last_position_datetime": latest.position_datetime,
                        "last_latitude": latest.latitude,
                        "last_longitude": latest.longitude,
                        "last_speed_kmh": latest.speed_kmh,
                    }
                )

    # ------------------------------------------------------------------
    # 界面动作
    # ------------------------------------------------------------------
    def action_open_in_maps(self):
        """在外网地图中打开该定位点。"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "https://www.google.com/maps?q=%s,%s"
            % (self.latitude, self.longitude),
            "target": "new",
        }

    # ------------------------------------------------------------------
    # 保留策略
    # ------------------------------------------------------------------
    @api.model
    def _retention_days(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("kcg_gps_tracking.retention_days")
        )
        try:
            days = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_RETENTION_DAYS
        # 0 或负数表示不清理，便于调试时关掉
        return days

    @api.model
    def _cron_purge_old_positions(self, batch_size=PURGE_BATCH_SIZE):
        """清理超过保留期的原始定位点。

        分批次删除并在批次之间提交：一次性 DELETE 上千万行会长时间持有锁、
        把 WAL 撑大，期间整个 Odoo 的写操作都可能被拖住。
        """
        retention_days = self._retention_days()
        if retention_days <= 0:
            _logger.info("GPS 定位保留策略已关闭（retention_days=%s），跳过清理", retention_days)
            return 0
        cutoff = fields.Datetime.now() - datetime.timedelta(days=retention_days)
        total = 0
        while True:
            self.env.cr.execute(
                """
                DELETE FROM gps_position
                WHERE id IN (
                    SELECT id FROM gps_position
                    WHERE position_datetime < %s
                    LIMIT %s
                )
                """,
                (cutoff, batch_size),
            )
            deleted = self.env.cr.rowcount
            total += deleted
            self.env.cr.commit()
            if deleted < batch_size:
                break
        if total:
            _logger.info(
                "GPS 定位保留策略：已清理 %s 条早于 %s 的记录", total, cutoff
            )
        return total
