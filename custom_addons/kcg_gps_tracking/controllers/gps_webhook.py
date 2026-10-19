"""GPS 平台推送接收接口。

第 3 轮定位数据源确认「先留接口不接真实数据」，所以这里提供的是一个可用的
接收端点，但默认是关闭的：只有同时满足下面三个条件才会真正处理请求。

1. 存在启用的 ``gps.provider``，且其 ``code`` 与地址里的标识一致；
2. 该数据源配置的适配器已在代码中注册；
3. 适配器的 :meth:`verify_webhook_signature` 返回 True。

任何一条不满足都直接拒绝。这是刻意的失败关闭设计——一个公网可达的写入接口，
绝对不能因为「还没配好」而默认放行。

另外，这个端点用的是 ``auth="public"``：平台推送方没有 Odoo 会话，因此不能依赖
用户身份做鉴权，安全边界完全落在签名校验上。入库用 ``sudo()`` 提权。
"""

import json
import logging

from odoo import http
from odoo.http import request

from ..services.provider_adapter import MAX_WEBHOOK_BYTES, get_adapter

_logger = logging.getLogger(__name__)


class GpsWebhookController(http.Controller):

    def _json(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, ensure_ascii=False),
            status=status,
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )

    @http.route(
        "/kcg/gps/webhook/<string:provider_code>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def gps_webhook(self, provider_code, **kwargs):
        provider = (
            request.env["gps.provider"]
            .sudo()
            .search([("code", "=", provider_code)], limit=1)
        )
        if not provider:
            # 不回显「该标识不存在」，避免被用来枚举数据源。
            return self._json({"ok": False, "error": "unknown provider"}, 404)
        if not provider.active:
            return self._json({"ok": False, "error": "provider disabled"}, 403)

        adapter = get_adapter(provider)
        if adapter is None:
            _logger.warning(
                "GPS 推送被拒：数据源 %s 的适配器 %s 未注册",
                provider.name,
                provider.adapter_code,
            )
            return self._json({"ok": False, "error": "adapter not available"}, 501)

        raw_body = request.httprequest.get_data() or b""
        if not raw_body:
            return self._json({"ok": False, "error": "empty body"}, 400)
        if len(raw_body) > MAX_WEBHOOK_BYTES:
            return self._json({"ok": False, "error": "payload too large"}, 413)

        # 必须用原始字节做签名校验：先解析 JSON 再重新序列化会改变字节，
        # 签名必然对不上。
        if not adapter.verify_webhook_signature(raw_body, request.httprequest.headers):
            _logger.warning(
                "GPS 推送签名校验失败：数据源 %s，来源 %s",
                provider.name,
                request.httprequest.remote_addr,
            )
            return self._json({"ok": False, "error": "invalid signature"}, 403)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._json({"ok": False, "error": "invalid json"}, 400)

        try:
            values_list = adapter.parse_webhook(payload)
        except Exception:  # noqa: BLE001 - 适配器解析失败不能把异常抛给推送方
            _logger.exception("GPS 推送解析失败：数据源 %s", provider.name)
            return self._json({"ok": False, "error": "parse failed"}, 500)

        if not values_list:
            return self._json({"ok": True, "received": 0, "inserted": 0})

        inserted = (
            request.env["gps.position"]
            .sudo()
            ._ingest_from_provider(values_list, provider)
        )
        return self._json(
            {"ok": True, "received": len(values_list), "inserted": inserted}
        )
