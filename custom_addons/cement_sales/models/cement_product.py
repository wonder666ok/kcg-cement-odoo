from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    cement_grade = fields.Char(string="水泥等级")
    bag_weight_kg = fields.Float(string="每袋重量(kg)", default=50.0)
