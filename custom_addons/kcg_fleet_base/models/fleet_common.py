"""车辆、司机、设备共用的到期判断逻辑。

单独放一个模块而不是复制三遍：年检、保险、驾照、行驶证的到期口径必须一致，
否则同一个「即将到期」在不同表单上会给出不同结果。
"""

#: 提前多少天开始提示「即将到期」
EXPIRY_WARN_DAYS = 30

EXPIRY_STATE_SELECTION = [
    ("unknown", "未填写"),
    ("valid", "有效"),
    ("soon", "即将到期"),
    ("expired", "已过期"),
]


def expiry_state(date_value, today, warn_days=EXPIRY_WARN_DAYS):
    """把一个到期日折算成状态。

    :param date_value: 到期日（``datetime.date``），为空表示未维护
    :param today: 参照日，调用方需传 ``fields.Date.context_today``，不要用
        ``fields.Date.today()``，否则跨时区会差一天
    """
    if not date_value:
        return "unknown"
    if date_value < today:
        return "expired"
    if (date_value - today).days <= warn_days:
        return "soon"
    return "valid"
