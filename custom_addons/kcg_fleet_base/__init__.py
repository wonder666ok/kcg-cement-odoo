from . import models


def post_init_hook(env):
    """模块升级后为存量司机补建联系人（带「司机」分类标签）。

    只补缺失的，不动已有联系人，可安全重复执行。
    """
    env["transport.driver"].search([("partner_id", "=", False)])._ensure_partner_record()
