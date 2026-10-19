{
    "name": "KCG GPS Tracking",
    "summary": "车辆 GPS 定位、轨迹与告警",
    "description": """
KCG 车辆定位
============

接收、存储和展示车载 GPS 定位数据，提供电子围栏外的轨迹回放基础数据与告警。

本轮范围说明
------------
**暂不接真实定位平台**：适配器层（``services/provider_adapter.py``）与数据模型、
索引、去重、保留策略已完整实现，只缺一个具体平台的适配器类。要接真平台时
新增一个 ``GpsProviderAdapter`` 子类并注册即可，不需要改模型和控制器。

数据量提示
----------
定位表是典型的时序数据：50 辆车按 10 秒一个点计，每天 43 万条、每月约 1300 万条。
因此：

- 复合唯一索引 ``(device_id, position_datetime)`` 由 ``_sql_constraints`` 建立，
  同时承担「查某车某时间段」的查询加速与「平台断线重推」的幂等去重；
- 批量写入走原生 ``INSERT ... ON CONFLICT DO NOTHING``，不逐条走 ORM；
- 内置保留策略定时任务，超期数据按批次删除；
- 该模型**不挂 mail.thread**——每条定位写一条消息会让库直接爆掉。
""",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail", "kcg_fleet_base"],
    "data": [
        "security/kcg_gps_security.xml",
        "security/ir.model.access.csv",
        "views/gps_provider_views.xml",
        "views/gps_device_views.xml",
        "views/gps_position_views.xml",
        "views/gps_alert_views.xml",
        "views/kcg_gps_menus.xml",
        "data/kcg_gps_cron.xml",
    ],
    "application": True,
    "installable": True,
}
