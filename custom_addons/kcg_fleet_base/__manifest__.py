{
    "name": "KCG Fleet Base",
    "summary": "车辆、司机、承运商与 GPS 设备基础档案",
    "description": """
KCG 运输基础档案
================

车辆、司机、承运商与 GPS 设备的主数据模块，供运输执行类模块（TMS、GPS 定位）
引用，把原先散落在交付单上的车牌/司机/承运商自由文本收敛成可统计、可追溯的档案。

模型命名说明
------------
模型刻意使用 ``transport.*`` 与 ``gps.*`` 命名空间，而不是 ``fleet.vehicle``。
Odoo 内置 ``fleet`` 模块已占用 ``fleet.vehicle`` 这个名字，虽然它当前处于未安装
状态，但一旦日后启用，两个模块各自定义同名模型会直接导致注册表加载失败。
""",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail"],
    "data": [
        "security/kcg_fleet_security.xml",
        "security/ir.model.access.csv",
        "views/transport_carrier_views.xml",
        "views/transport_driver_views.xml",
        "views/transport_vehicle_views.xml",
        "views/gps_device_views.xml",
        "views/kcg_fleet_menus.xml",
        "data/kcg_fleet_data.xml",
    ],
    "application": True,
    "installable": True,
    "post_init_hook": "post_init_hook",
}
