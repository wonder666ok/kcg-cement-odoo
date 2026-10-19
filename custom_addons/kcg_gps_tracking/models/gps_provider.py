from odoo import api, fields, models

from ..services.provider_adapter import available_adapters, unavailable_adapters


class GpsProvider(models.Model):
    _name = "gps.provider"
    _description = "GPS 数据源"
    _order = "sequence, name, id"
    _check_company_auto = True

    name = fields.Char(string="数据源名称", required=True)
    code = fields.Char(
        string="标识",
        required=True,
        help="稳定标识，用于拼出该数据源的推送地址：/kcg/gps/webhook/<标识>。"
        "建档后不建议改动，平台侧配置的地址会失效。",
    )
    adapter_code = fields.Selection(
        selection="_selection_adapter_code",
        string="适配器",
        help="决定用哪段代码解析该平台的数据。取值为已注册的适配器，"
        "接新平台时先在 services/provider_adapter.py 里新增并注册一个适配器类。",
    )
    auth_type = fields.Selection(
        [
            ("none", "不校验"),
            ("api_key", "API Key"),
            ("hmac", "HMAC 签名"),
            ("oauth2", "OAuth2"),
        ],
        string="认证方式",
        default="hmac",
        required=True,
        help="推送接口的签名方案。选「不校验」时推送地址会直接拒绝请求，"
        "公网接口不应在不校验的情况下开放。",
    )
    api_base_url = fields.Char(string="接口地址", help="主动拉取模式下的平台接口地址。")
    # 凭据类字段限制为车队主管可见。字段级 groups 会让非授权用户完全看不到这些字段，
    # 视图里引用它们的地方必须声明同样的 groups，否则视图加载会报权限错。
    api_key = fields.Char(
        string="API Key",
        groups="kcg_fleet_base.group_kcg_fleet_manager",
    )
    api_secret = fields.Char(
        string="API Secret",
        groups="kcg_fleet_base.group_kcg_fleet_manager",
    )
    webhook_secret = fields.Char(
        string="Webhook 签名密钥",
        help="用于校验推送来源的 HMAC-SHA256 密钥。未配置时推送接口一律拒绝。",
        groups="kcg_fleet_base.group_kcg_fleet_manager",
    )
    poll_interval_minutes = fields.Integer(
        string="拉取间隔(分钟)",
        default=5,
        help="主动拉取模式下的轮询间隔。",
    )
    last_poll_datetime = fields.Datetime(string="上次拉取时间", readonly=True)
    sequence = fields.Integer(string="排序", default=10)
    active = fields.Boolean(string="启用", default=True)
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    device_ids = fields.One2many("gps.device", "provider_id", string="设备")
    device_count = fields.Integer(string="设备数", compute="_compute_device_count")
    alert_ids = fields.One2many("gps.alert", "provider_id", string="告警")
    adapter_warning = fields.Char(
        string="适配器缺失",
        compute="_compute_adapter_warning",
        help="数据源引用的适配器在代码里找不到时提示，通常出现在模块卸载或改名之后。",
    )
    webhook_path = fields.Char(
        string="推送地址",
        compute="_compute_webhook_path",
        help="把该地址配置到平台的推送设置里。主机名取自系统参数 web.base.url。",
    )
    notes = fields.Text(string="备注")

    _sql_constraints = [
        ("code_uniq", "UNIQUE(code)", "数据源标识不能重复。"),
    ]

    @api.model
    def _selection_adapter_code(self):
        return available_adapters()

    @api.depends("code")
    def _compute_webhook_path(self):
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for provider in self:
            if provider.code:
                provider.webhook_path = "%s/kcg/gps/webhook/%s" % (
                    base_url,
                    provider.code,
                )
            else:
                provider.webhook_path = False

    @api.depends("device_ids")
    def _compute_device_count(self):
        for provider in self:
            provider.device_count = len(provider.device_ids)

    @api.depends("adapter_code")
    def _compute_adapter_warning(self):
        for provider in self:
            missing = unavailable_adapters(provider)
            provider.adapter_warning = (
                "代码里找不到适配器 %s，该数据源的数据不会被解析。" % missing
                if missing
                else False
            )

    def action_view_devices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "设备",
            "res_model": "gps.device",
            "view_mode": "list,form",
            "domain": [("provider_id", "=", self.id)],
            "context": {"default_provider_id": self.id},
        }
