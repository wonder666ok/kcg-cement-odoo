"""GPS 数据源适配器。

各家车联网服务商的接口差异很大：有的推 webhook，有的只能轮询；有的用 HMAC 签名，
有的用 OAuth2；字段名从 ``lat`` / ``latitude`` / ``y`` 到 ``wgs_lat`` 无奇不有。

这里用适配器模式把差异全部关在一个类里。上层（模型、控制器、定时任务）只认
``parse_webhook`` / ``fetch_positions`` 两个方法，接一个新平台时新增一个子类并注册，
不需要改数据模型。

**本轮不接真实平台**：只提供基类、注册表和一个 Mock 适配器，用于把数据链路先跑通。

两条硬性约束：

1. **第三方 SDK 一律在方法内部惰性导入**，绝不能在模块顶层 import。
   否则某个平台没装它的 SDK 时，整个 Odoo 服务起不来——一个定位数据源能把全公司
   ERP 拖挂，这个代价太大。
2. **签名校验默认拒绝**。基类不提供任何「放行」的默认实现，避免新适配器忘了实现
   校验就把公网接口敞开。
"""

import hashlib
import hmac
import logging

_logger = logging.getLogger(__name__)

#: 单次 webhook 请求允许的最大体积，防止超大报文打满 worker 内存
MAX_WEBHOOK_BYTES = 2 * 1024 * 1024


class GpsProviderAdapter:
    """第三方定位平台适配器基类。"""

    #: 适配器标识，需与 ``gps.provider.adapter_code`` 的值对应
    code = None
    #: 界面上显示的名称
    name = None

    def __init__(self, provider):
        self.provider = provider

    # ------------------------------------------------------------------
    # 签名校验
    # ------------------------------------------------------------------
    def verify_webhook_signature(self, raw_body, headers):
        """校验推送来源。

        默认实现按 HMAC-SHA256 校验，且要求数据源已配置 ``webhook_secret``。
        未配置密钥、或数据源未选用 ``hmac`` 认证方式时一律返回 False。

        :param raw_body: 未经任何处理的原始请求体（bytes）。必须用原始字节计算，
            一旦先做了 JSON 解析再序列化，签名字节就变了。
        """
        secret = self.provider.webhook_secret
        if not secret:
            return False
        if self.provider.auth_type != "hmac":
            # 没有专用签名方案的平台，其适配器应重写本方法实现自己的校验，
            # 而不是在这里放行。
            return False
        signature = headers.get("X-KCG-Signature") or headers.get("X-Signature") or ""
        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature.strip().lower(), expected)

    # ------------------------------------------------------------------
    # 数据转换
    # ------------------------------------------------------------------
    def parse_webhook(self, payload):
        """把平台推送的报文转成定位字典列表。

        返回的每个字典应包含 ``device_code``（平台上登记的设备编号，
        需与 ``gps.device.name`` 一致）以及 :meth:`normalize` 输出的定位字段。
        """
        raise NotImplementedError("该数据源未实现 webhook 解析")

    def fetch_positions(self, since=None):
        """主动拉取定位数据。

        :param since: 只取该时刻之后的数据，``None`` 表示由适配器自行决定
        """
        raise NotImplementedError("该数据源不支持主动拉取")

    def normalize(self, raw):
        """把平台单条记录映射成 ``gps.position`` 的字段名。

        子类实现。允许返回的字段：
        ``device_code`` / ``position_datetime`` / ``latitude`` / ``longitude`` /
        ``altitude`` / ``speed_kmh`` / ``heading`` / ``odometer_km`` / ``ignition`` /
        ``address``。

        ``position_datetime`` 可以是字符串，也可以是 Unix 秒或毫秒时间戳，
        入库前会统一解析成 UTC。
        """
        raise NotImplementedError("该数据源未实现字段映射")


# ----------------------------------------------------------------------
# 适配器注册表
# ----------------------------------------------------------------------
_ADAPTERS = {}


def register_adapter(adapter_cls):
    """把适配器类登记进注册表。用法：在类定义前加 ``@register_adapter``。"""
    if not adapter_cls.code:
        raise ValueError("适配器必须定义 code 属性：%s" % adapter_cls)
    if adapter_cls.code in _ADAPTERS:
        _logger.warning(
            "适配器 code=%s 重复注册，后者覆盖前者：%s -> %s",
            adapter_cls.code,
            _ADAPTERS[adapter_cls.code],
            adapter_cls,
        )
    _ADAPTERS[adapter_cls.code] = adapter_cls
    return adapter_cls


def get_adapter(provider):
    """按数据源配置取出适配器实例；未注册或未配置时返回 ``None``。

    返回 ``None`` 是刻意设计：调用方据此拒绝请求，而不是退化成某种放行路径。
    """
    if not provider or not provider.adapter_code:
        return None
    adapter_cls = _ADAPTERS.get(provider.adapter_code)
    if adapter_cls is None:
        _logger.warning(
            "数据源 %s 配置的适配器 %s 未注册", provider.name, provider.adapter_code
        )
        return None
    return adapter_cls(provider)


def unavailable_adapters(provider):
    """返回数据源引用了但尚未注册的适配器标识。"""
    if not provider or not provider.adapter_code:
        return None
    if provider.adapter_code in _ADAPTERS:
        return None
    return provider.adapter_code


def available_adapters():
    """返回 [(code, name)]，供 Selection 字段使用。"""
    return [
        (code, cls.name or code)
        for code, cls in sorted(_ADAPTERS.items(), key=lambda item: item[0])
    ]


# ----------------------------------------------------------------------
# 联调用适配器
# ----------------------------------------------------------------------
@register_adapter
class MockProviderAdapter(GpsProviderAdapter):
    """模拟数据源。

    不连接任何真实平台，接受如下结构的报文，用于在没有真实 GPS 数据的情况下
    把「接收 → 入库 → 去重 → 车辆最后定位 → 告警」这条链路跑通：

    .. code-block:: json

        {"positions": [
            {"device": "DEV-0001", "ts": "2026-10-15 08:00:00",
             "lat": 5.6037, "lng": -0.1870, "speed": 42.5, "course": 180, "acc": true}
        ]}
    """

    code = "mock"
    name = "模拟数据源（联调用，不接真实平台）"

    def parse_webhook(self, payload):
        rows = []
        for item in (payload or {}).get("positions", []):
            if not isinstance(item, dict):
                continue
            row = self.normalize(item)
            if row:
                rows.append(row)
        return rows

    def fetch_positions(self, since=None):
        # 模拟适配器不产生数据，真实平台的适配器在这里调平台接口。
        return []

    def normalize(self, raw):
        device_code = raw.get("device") or raw.get("device_code")
        if not device_code:
            return {}
        return {
            "device_code": device_code,
            "position_datetime": raw.get("ts") or raw.get("position_datetime"),
            "latitude": raw.get("lat", raw.get("latitude")),
            "longitude": raw.get("lng", raw.get("longitude")),
            "altitude": raw.get("alt") or 0.0,
            "speed_kmh": raw.get("speed") or 0.0,
            "heading": raw.get("course") or 0.0,
            "odometer_km": raw.get("odometer") or 0.0,
            "ignition": raw.get("acc"),
            "source": "provider",
        }
