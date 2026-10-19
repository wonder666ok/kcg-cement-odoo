from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    cement_grade = fields.Char(string="水泥等级")
    bag_weight_kg = fields.Float(
        string="每袋重量(kg)",
        compute="_compute_bag_weight_kg",
        help="由产品主单位推导，不可直接修改：主单位为「袋」(1 袋 = 50kg) 时显示 50。"
             "若需要其它袋重（例如 40kg 装），请先在「设置 → 单位」新建对应单位，"
             "再把产品的主单位改为该单位，这里会跟着变。",
    )

    @api.depends("uom_id")
    def _compute_bag_weight_kg(self):
        """袋重只由主单位决定，避免「单位换算」与「袋重字段」两套口径互相打架。"""
        reference_kg = self.env.ref("uom.product_uom_kgm", raise_if_not_found=False)
        for product in self:
            uom = product.uom_id
            if not reference_kg or not uom or uom.category_id != reference_kg.category_id:
                # 主单位不是重量单位（如默认的「单位」）时没有袋重可言。
                product.bag_weight_kg = 0.0
                continue
            # 1 个主单位等于多少 kg：袋 → 50，吨 → 1000，kg → 1。
            product.bag_weight_kg = uom._compute_quantity(
                1.0, reference_kg, round=False
            )

    @api.onchange("cement_grade")
    def _onchange_cement_grade_set_bag_uom(self):
        """填了水泥等级、主单位又还是默认的「单位」时，自动切成「袋」。

        水泥按袋销售，新建水泥产品时默认按袋可以减少一步手工设置；
        已经手工改过单位的产品不会被覆盖。
        """
        if not self.cement_grade:
            return
        bag_uom = self.env.ref("cement_sales.uom_bag", raise_if_not_found=False)
        default_uom = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        if not bag_uom or not default_uom or self.uom_id != default_uom:
            return
        self.uom_id = bag_uom
        self.uom_po_id = bag_uom
