from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CementPrepaidTransaction(models.Model):
    """客户预存款流水：充值/发货扣款/退款/调整共用一张流水表。

    金额带正负号：正数入账（充值、退款），负数出账（发货扣款），
    客户余额 = 全部流水金额之和。
    """
    _name = "cement.prepaid.transaction"
    _description = "客户预存款流水"
    _order = "date desc, id desc"

    customer_id = fields.Many2one(
        "cement.customer",
        string="客户",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        related="company_id.currency_id",
        readonly=True,
    )
    date = fields.Datetime(
        string="时间", required=True, default=fields.Datetime.now
    )
    type = fields.Selection(
        [
            ("recharge", "充值"),
            ("deduction", "扣款"),
            ("refund", "退款"),
            ("adjust", "调整"),
        ],
        string="类型",
        required=True,
        index=True,
        default="recharge",
    )
    deduction_kind = fields.Selection(
        [("goods", "货款"), ("freight", "运费")],
        string="扣款类别",
        index=True,
        help="扣款流水的类别：订单确认扣货款、运输安排扣运费。",
    )
    amount = fields.Monetary(
        string="金额",
        help="正数入账（充值/退款），负数出账（发货扣款）。",
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="销售订单",
        ondelete="set null",
        index=True,
    )
    delivery_id = fields.Many2one(
        "cement.delivery",
        string="交付单",
        ondelete="set null",
        index=True,
    )
    note = fields.Char(string="备注")

    @api.constrains("amount")
    def _check_amount(self):
        for tx in self:
            if not tx.amount:
                raise UserError(_("预存款流水金额不能为 0。"))

    def action_view_related_delivery(self):
        self.ensure_one()
        if not self.delivery_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "cement.delivery",
            "res_id": self.delivery_id.id,
            "view_mode": "form",
            "target": "current",
        }


class CementCustomer(models.Model):
    _inherit = "cement.customer"

    is_prepaid = fields.Boolean(
        string="预存款客户",
        help="勾选后，销售订单确认时自动扣除货款、运输安排成功时自动扣除运费，均从预存款余额中扣。",
    )
    prepaid_transaction_ids = fields.One2many(
        "cement.prepaid.transaction",
        "customer_id",
        string="预存款流水",
    )
    prepaid_count = fields.Integer(
        string="流水数", compute="_compute_prepaid_balance"
    )
    prepaid_balance = fields.Monetary(
        string="预存款余额",
        compute="_compute_prepaid_balance",
        currency_field="prepaid_currency_id",
        help="全部预存款流水之和：充值与退款为正、发货扣款为负。",
    )
    prepaid_currency_id = fields.Many2one(
        "res.currency",
        string="预存款币种",
        compute="_compute_prepaid_balance",
    )

    @api.depends("prepaid_transaction_ids.amount")
    def _compute_prepaid_balance(self):
        for customer in self:
            txs = customer.prepaid_transaction_ids
            customer.prepaid_balance = sum(txs.mapped("amount"))
            customer.prepaid_count = len(txs)
            customer.prepaid_currency_id = (
                txs[:1].currency_id
                or customer.company_id.currency_id
                or self.env.company.currency_id
            )

    def action_recharge_prepaid(self):
        """打开充值向导。"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("客户预存款充值"),
            "res_model": "cement.prepaid.recharge",
            "view_mode": "form",
            "target": "new",
            "context": {"default_customer_id": self.id},
        }

    def action_view_prepaid_transactions(self):
        """查看该客户的预存款流水。"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("预存款流水 - %s") % self.name,
            "res_model": "cement.prepaid.transaction",
            "view_mode": "list,form",
            "domain": [("customer_id", "=", self.id)],
            "context": {
                "default_customer_id": self.id,
                "search_default_group_by_type": 1,
            },
            "target": "current",
        }


class CementPrepaidRecharge(models.TransientModel):
    _name = "cement.prepaid.recharge"
    _description = "客户预存款充值向导"

    customer_id = fields.Many2one(
        "cement.customer", string="客户", required=True, readonly=True
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )
    amount = fields.Monetary(
        string="充值金额", currency_field="currency_id", required=True
    )
    note = fields.Char(string="备注")

    def action_confirm(self):
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_("充值金额必须大于 0。"))
        self.env["cement.prepaid.transaction"].create(
            {
                "customer_id": self.customer_id.id,
                "type": "recharge",
                "amount": self.amount,
                "note": self.note or _("客户预存款充值"),
                "company_id": self.customer_id.company_id.id
                or self.env.company.id,
            }
        )
        return {"type": "ir.actions.act_window_close"}


class CementPrepaidMixinLogic:
    """预存款扣款共用小工具（纯 Python 类，不参与 ORM 继承）。"""

    @staticmethod
    def _check_prepaid_sufficient(customer, amount, scenario):
        if amount and (customer.prepaid_balance or 0.0) < amount:
            raise UserError(
                _(
                    "客户「%(customer)s」预存款余额不足：当前余额 %(balance).2f，"
                    "%(scenario)s需扣款 %(amount).2f。请先为客户充值，或取消预存款客户标记。"
                )
                % {
                    "customer": customer.name,
                    "balance": customer.prepaid_balance or 0.0,
                    "scenario": scenario,
                    "amount": amount,
                }
            )


class CementSaleOrder(models.Model):
    _inherit = "sale.order"

    # ------------------------------------------------------------------
    # 预存款扣款（货款）：订单确认（state -> sale）时按订单未税金额全额
    # 扣款；订单取消/退回草稿时自动撤销扣款流水。仅对勾选了
    # 「预存款客户」的客户生效；余额不足时阻止确认；重复确认不会重复扣款。
    # ------------------------------------------------------------------
    def _get_prepaid_goods_tx(self):
        self.ensure_one()
        return self.env["cement.prepaid.transaction"].search(
            [
                ("sale_order_id", "=", self.id),
                ("type", "=", "deduction"),
                ("deduction_kind", "=", "goods"),
            ],
            limit=1,
        )

    def _create_prepaid_goods_deduction(self):
        self.ensure_one()
        customer = self.cement_customer_id
        if not customer or not customer.is_prepaid:
            return False
        if self._get_prepaid_goods_tx():
            return False  # 已扣过款，防重复
        amount = round(self.amount_untaxed or 0.0, 2)
        if not amount:
            return False
        CementPrepaidMixinLogic._check_prepaid_sufficient(
            customer, amount, _("订单确认")
        )
        return self.env["cement.prepaid.transaction"].create(
            {
                "customer_id": customer.id,
                "type": "deduction",
                "deduction_kind": "goods",
                "amount": -amount,
                "sale_order_id": self.id,
                "company_id": self.company_id.id,
                "note": _("订单 %(order)s 确认自动扣款（货款）")
                % {"order": self.name or self.id},
            }
        )

    def _remove_prepaid_goods_deduction(self):
        self.ensure_one()
        self._get_prepaid_goods_tx().unlink()

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            order._create_prepaid_goods_deduction()
        return res

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state") and vals["state"] in ("draft", "cancel"):
            for order in self:
                order._remove_prepaid_goods_deduction()
        return res


class CementDelivery(models.Model):
    _inherit = "cement.delivery"

    # ------------------------------------------------------------------
    # 预存款扣款（运费）：运输安排成功（state -> scheduled）时按交付单
    # 运费扣款；运输取消或重置回待安排时自动撤销扣款流水。仅对勾选了
    # 「预存款客户」的客户生效；余额不足时阻止安排；重复操作不会重复扣款。
    # 货款在销售订单确认时已扣（见 CementSaleOrder）。
    # ------------------------------------------------------------------
    def _get_prepaid_freight_tx(self):
        self.ensure_one()
        return self.env["cement.prepaid.transaction"].search(
            [
                ("delivery_id", "=", self.id),
                ("type", "=", "deduction"),
                ("deduction_kind", "=", "freight"),
            ],
            limit=1,
        )

    def _create_prepaid_freight_deduction(self):
        self.ensure_one()
        customer = self.customer_id
        if not customer or not customer.is_prepaid:
            return False
        if self._get_prepaid_freight_tx():
            return False  # 已扣过款，防重复
        amount = round(self.freight_amount or 0.0, 2)
        if not amount:
            return False
        CementPrepaidMixinLogic._check_prepaid_sufficient(
            customer, amount, _("运输安排")
        )
        return self.env["cement.prepaid.transaction"].create(
            {
                "customer_id": customer.id,
                "type": "deduction",
                "deduction_kind": "freight",
                "amount": -amount,
                "sale_order_id": self.sale_order_id.id,
                "delivery_id": self.id,
                "company_id": self.company_id.id,
                "note": _("交付单 %(delivery)s 运输安排自动扣款（运费）")
                % {"delivery": self.sale_order_id.name or self.id},
            }
        )

    def _remove_prepaid_freight_deduction(self):
        self.ensure_one()
        self._get_prepaid_freight_tx().unlink()

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state"):
            for delivery in self:
                if delivery.state == "scheduled":
                    delivery._create_prepaid_freight_deduction()
                elif delivery.state in ("draft", "cancelled"):
                    delivery._remove_prepaid_freight_deduction()
        return res
