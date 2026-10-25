from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import image_process


class CementCustomer(models.Model):
    _name = "cement.customer"
    _description = "Cement Customer"
    _rec_name = "name"
    _order = "name"

    name = fields.Char(string="客户名称", required=True)
    # 客户照片 / Logo：表单左侧头像展示，点击可放大；
    # 列表显示小头像；创建/更新 Odoo 联系人时同步过去。
    image_1920 = fields.Binary(
        string="照片/Logo",
        attachment=True,
        help="客户照片、店铺门头或公司 Logo，支持 png/jpg。",
    )
    image_128 = fields.Binary(
        string="头像(小图)", compute="_compute_image_128", store=True, attachment=True
    )
    has_image = fields.Boolean(compute="_compute_image_128")
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    phone = fields.Char(string="电话")
    email = fields.Char(string="邮箱")
    company_name = fields.Char(string="公司名称")
    customer_type = fields.Selection(
        selection=[
            ("individual", "个人"),
            ("company", "企业"),
        ],
        string="客户类型",
        default="individual",
        required=True,
    )
    active = fields.Boolean(string="是否启用", default=True)
    whatsapp = fields.Char(string="WhatsApp")
    region = fields.Char(string="地区")
    sales_person = fields.Many2one("res.users", string="销售员")
    customer_source = fields.Selection(
        selection=[
            ("website", "网站"),
            ("whatsapp", "WhatsApp"),
            ("wechat", "微信"),
            ("referral", "客户介绍"),
            ("walk_in", "上门客户"),
            ("other", "其他"),
        ],
        string="客户来源",
    )
    customer_status = fields.Selection(
        selection=[
            ("new", "新客户"),
            ("active", "活跃客户"),
            ("inactive", "不活跃客户"),
        ],
        string="客户状态",
        default="new",
    )
    notes = fields.Text(string="备注")
    next_followup_date = fields.Date(string="下次跟进日期", index=True)
    last_followup_date = fields.Date(
        string="最近一次跟进日期", compute="_compute_followup_statistics"
    )
    followup_count = fields.Integer(
        string="跟进次数", compute="_compute_followup_statistics"
    )
    pending_followup_count = fields.Integer(
        string="待跟进数量", compute="_compute_followup_statistics"
    )
    overdue_followup_count = fields.Integer(
        string="逾期跟进数量", compute="_compute_followup_statistics"
    )
    partner_id = fields.Many2one(
        "res.partner", string="Odoo联系人", ondelete="restrict"
    )
    sale_order_ids = fields.One2many(
        "sale.order", "cement_customer_id", string="销售订单"
    )
    quotation_count = fields.Integer(
        string="报价数量", compute="_compute_sales_statistics"
    )
    confirmed_order_count = fields.Integer(
        string="已确认订单数量", compute="_compute_sales_statistics"
    )
    sales_currency_id = fields.Many2one(
        "res.currency", string="销售统计币种", compute="_compute_sales_statistics"
    )
    total_sales_amount = fields.Monetary(
        string="累计销售金额（当前公司本位币）",
        currency_field="sales_currency_id",
        compute="_compute_sales_statistics",
    )
    last_order_date = fields.Datetime(
        string="最近订单日期", compute="_compute_sales_statistics"
    )
    invoice_ids = fields.Many2many(
        "account.move",
        string="客户发票",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    invoice_count = fields.Integer(
        string="发票数量",
        compute="_compute_financial_statistics",
        store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    financial_currency_id = fields.Many2one(
        "res.currency",
        string="财务统计币种",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    has_multiple_invoice_currencies = fields.Boolean(
        string="发票含多种币种",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    total_invoiced_amount = fields.Monetary(
        string="累计开票金额",
        currency_field="financial_currency_id",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    total_paid_amount = fields.Monetary(
        string="累计已收款",
        currency_field="financial_currency_id",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    total_due_amount = fields.Monetary(
        string="应收余额",
        currency_field="financial_currency_id",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    account_payment_ids = fields.Many2many(
        "account.payment",
        string="Odoo原生收款",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    payment_count = fields.Integer(
        string="回款数量",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    last_payment_date = fields.Date(
        string="最近付款日期",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    receivable_status = fields.Selection(
        [
            ("none", "无应收"),
            ("unpaid", "待付款"),
            ("partial", "部分付款"),
            ("overdue", "已逾期"),
            ("paid", "已结清"),
        ],
        string="应收账款状态",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    has_receivable = fields.Boolean(
        string="有应收",
        compute="_compute_financial_statistics",
        search="_search_has_receivable",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    overdue_invoice_count = fields.Integer(
        string="逾期发票数量",
        compute="_compute_financial_statistics",
        search="_search_overdue_invoice_count",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    overdue_amount = fields.Monetary(
        string="逾期未收款金额",
        currency_field="financial_currency_id",
        compute="_compute_financial_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    delivery_count = fields.Integer(
        string="交付数量", compute="_compute_delivery_count"
    )
    payment_ids = fields.One2many(
        "cement.payment", "customer_id", string="回款记录"
    )
    payment_currency_id = fields.Many2one(
        "res.currency", string="回款统计币种", compute="_compute_cement_payment_statistics"
    )
    payment_record_count = fields.Integer(
        string="回款记录数量", compute="_compute_cement_payment_statistics"
    )
    confirmed_payment_count = fields.Integer(
        string="已确认回款数量", compute="_compute_cement_payment_statistics"
    )
    last_cement_payment_date = fields.Date(
        string="最近一次回款日期", compute="_compute_cement_payment_statistics"
    )
    total_payment_amount = fields.Monetary(
        string="累计回款",
        currency_field="payment_currency_id",
        compute="_compute_cement_payment_statistics",
    )
    has_multiple_payment_currencies = fields.Boolean(
        string="回款含多种币种", compute="_compute_cement_payment_statistics"
    )
    picking_count = fields.Integer(
        string="发货数量",
        compute="_compute_picking_count",
        groups="stock.group_stock_user",
    )
    recent_order = fields.Boolean(
        string="近期有订单",
        compute="_compute_recent_order",
        search="_search_recent_order",
    )
    followup_ids = fields.One2many(
        "cement.followup", "customer_id", string="跟进记录"
    )
    delivery_ids = fields.One2many(
        "cement.delivery", "customer_id", string="交付记录"
    )

    @api.depends(
        "sale_order_ids",
        "sale_order_ids.state",
        "sale_order_ids.amount_total",
        "sale_order_ids.date_order",
        "sale_order_ids.currency_id",
        "sale_order_ids.company_id",
        "company_id",
    )
    def _compute_sales_statistics(self):
        statistics = {
            customer.id: {
                "quotation_count": 0,
                "confirmed_order_count": 0,
                "total_sales_amount": 0.0,
                "last_order_date": False,
            }
            for customer in self
        }
        orders = self.env["sale.order"].search(
            [("cement_customer_id", "in", self.ids)]
        ) if self.ids else self.env["sale.order"]
        fallback_currency = self.env.company.currency_id
        for order in orders:
            customer = order.cement_customer_id
            # 多公司下只统计客户所属公司的订单，否则会跨公司混算销售额。
            if customer.company_id and order.company_id != customer.company_id:
                continue
            values = statistics[customer.id]
            values["quotation_count"] += 1
            if order.date_order and (
                not values["last_order_date"]
                or order.date_order > values["last_order_date"]
            ):
                values["last_order_date"] = order.date_order
            if order.state in ("sale", "done"):
                values["confirmed_order_count"] += 1
                values["total_sales_amount"] += order.currency_id._convert(
                    order.amount_total,
                    customer.company_id.currency_id or fallback_currency,
                    order.company_id,
                    fields.Date.to_date(order.date_order)
                    or fields.Date.context_today(order),
                )

        for customer in self:
            values = statistics[customer.id]
            customer.sales_currency_id = (
                customer.company_id.currency_id or fallback_currency
            )
            customer.quotation_count = values["quotation_count"]
            customer.confirmed_order_count = values["confirmed_order_count"]
            customer.total_sales_amount = values["total_sales_amount"]
            customer.last_order_date = values["last_order_date"]

    @api.depends("delivery_ids")
    def _compute_delivery_count(self):
        for customer in self:
            customer.delivery_count = len(customer.delivery_ids)

    @api.depends(
        "followup_ids",
        "followup_ids.date",
        "followup_ids.state",
        "followup_ids.next_followup_date",
    )
    def _compute_followup_statistics(self):
        today = fields.Date.context_today(self)
        for customer in self:
            active_followups = customer.followup_ids.filtered(
                lambda followup: followup.state != "cancelled"
            )
            customer.followup_count = len(active_followups)
            customer.last_followup_date = max(
                active_followups.mapped("date"), default=False
            )
            pending = active_followups.filtered(
                lambda followup: followup.state == "pending"
            )
            customer.pending_followup_count = len(pending)
            customer.overdue_followup_count = len(
                pending.filtered(
                    lambda followup: followup.next_followup_date
                    and followup.next_followup_date < today
                )
            )

    @api.depends(
        "payment_ids",
        "payment_ids.status",
        "payment_ids.payment_date",
        "payment_ids.amount",
        "payment_ids.currency_id",
        "payment_ids.company_id",
        "company_id",
    )
    def _compute_cement_payment_statistics(self):
        fallback_currency = self.env.company.currency_id
        for customer in self:
            target_currency = customer.company_id.currency_id or fallback_currency
            confirmed_payments = customer.payment_ids.filtered(
                lambda payment: payment.status == "confirmed"
            )
            currency_ids = set(confirmed_payments.mapped("currency_id").ids)
            customer.payment_record_count = len(customer.payment_ids)
            customer.confirmed_payment_count = len(confirmed_payments)
            customer.last_cement_payment_date = max(
                confirmed_payments.mapped("payment_date"), default=False
            )
            customer.has_multiple_payment_currencies = len(currency_ids) > 1
            if len(currency_ids) == 1:
                # 单一币种：按原币种直接累加，不做折算。
                customer.payment_currency_id = confirmed_payments.mapped(
                    "currency_id"
                )[:1]
                customer.total_payment_amount = sum(
                    confirmed_payments.mapped("amount")
                )
                continue
            # 多币种或暂无回款：逐笔按各自所属公司折算到客户所属公司的本位币后累加。
            customer.payment_currency_id = target_currency
            total = 0.0
            for payment in confirmed_payments:
                payment_company = (
                    payment.company_id or customer.company_id or self.env.company
                )
                if not payment.payment_date:
                    continue
                total += payment.currency_id._convert(
                    payment.amount,
                    target_currency,
                    payment_company,
                    payment.payment_date,
                )
            customer.total_payment_amount = total

    @api.depends("sale_order_ids.picking_ids")
    def _compute_picking_count(self):
        for customer in self:
            customer.picking_count = len(customer.sale_order_ids.mapped("picking_ids"))

    @api.depends("sale_order_ids.date_order", "sale_order_ids.state")
    def _compute_recent_order(self):
        cutoff = fields.Datetime.now() - timedelta(days=90)
        for customer in self:
            customer.recent_order = any(
                order.state in ("sale", "done")
                and order.date_order
                and order.date_order >= cutoff
                for order in customer.sale_order_ids
            )

    @api.model
    def _search_recent_order(self, operator, value):
        if operator not in ("=", "!="):
            raise NotImplementedError("近期订单筛选只支持等于和不等于条件。")
        cutoff = fields.Datetime.to_string(
            fields.Datetime.now() - timedelta(days=90)
        )
        orders = self.env["sale.order"].search(
            [
                ("state", "in", ("sale", "done")),
                ("date_order", ">=", cutoff),
                ("cement_customer_id", "!=", False),
            ]
        )
        customer_ids = orders.mapped("cement_customer_id").ids
        positive = (operator == "=" and bool(value)) or (
            operator == "!=" and not bool(value)
        )
        return [("id", "in", customer_ids)] if positive and customer_ids else (
            [("id", "=", 0)] if positive else [("id", "not in", customer_ids)]
        )

    @api.depends(
        "partner_id",
        "partner_id.commercial_partner_id",
        "partner_id.commercial_partner_id.invoice_ids.move_type",
        "partner_id.commercial_partner_id.invoice_ids.state",
        "partner_id.commercial_partner_id.child_ids.invoice_ids.move_type",
        "partner_id.commercial_partner_id.child_ids.invoice_ids.state",
        "partner_id.invoice_ids.move_type",
        "partner_id.invoice_ids.state",
        "partner_id.invoice_ids.invoice_date_due",
        "partner_id.invoice_ids.currency_id",
        "partner_id.invoice_ids.company_currency_id",
        "partner_id.invoice_ids.amount_total",
        "partner_id.invoice_ids.amount_total_signed",
        "partner_id.invoice_ids.amount_residual",
        "partner_id.invoice_ids.amount_residual_signed",
        "partner_id.invoice_ids.payment_state",
        "partner_id.invoice_ids.reconciled_payment_ids",
        "partner_id.invoice_ids.reconciled_payment_ids.date",
        "partner_id.invoice_ids.reconciled_payment_ids.state",
        "partner_id.invoice_ids.reconciled_payment_ids.payment_method_line_id",
    )
    def _compute_financial_statistics(self):
        invoices = self.env["account.move"]
        partner_ids = self.mapped("partner_id.commercial_partner_id").ids
        if partner_ids:
            # Credit notes are intentionally excluded from first-version totals.
            invoices = self.env["account.move"].search(
                [
                    ("commercial_partner_id", "in", partner_ids),
                    ("move_type", "=", "out_invoice"),
                    ("state", "!=", "cancel"),
                ]
            )

        invoices_by_partner = {}
        for invoice in invoices:
            invoices_by_partner.setdefault(
                invoice.commercial_partner_id.id, self.env["account.move"]
            )
            invoices_by_partner[invoice.commercial_partner_id.id] |= invoice

        today = fields.Date.context_today(self)
        for customer in self:
            customer_invoices = invoices_by_partner.get(
                customer.partner_id.commercial_partner_id.id,
                self.env["account.move"],
            )
            posted_invoices = customer_invoices.filtered(
                lambda invoice: invoice.state == "posted"
            )
            currency_ids = set(posted_invoices.mapped("currency_id").ids)
            multiple_currencies = len(currency_ids) > 1
            # 客户所属公司不一定是当前公司，统一折算到客户所属公司的本位币。
            currency = customer.company_id.currency_id or self.env.company.currency_id

            overdue_invoices = posted_invoices.filtered(
                lambda invoice: invoice.invoice_date_due
                and invoice.invoice_date_due < today
                and invoice.amount_residual > 0
            )
            invoiced_amount = 0.0
            paid_amount = 0.0
            due_amount = 0.0
            overdue_amount = 0.0
            for invoice in posted_invoices:
                company = invoice.company_id
                conversion_date = invoice.invoice_date or invoice.date
                if not company or not conversion_date or not invoice.company_currency_id:
                    continue
                invoice_amount = invoice.company_currency_id._convert(
                    abs(invoice.amount_total_signed),
                    currency,
                    company,
                    conversion_date,
                )
                residual_amount = invoice.company_currency_id._convert(
                    max(invoice.amount_residual_signed, 0.0),
                    currency,
                    company,
                    fields.Date.context_today(invoice),
                )
                invoiced_amount += invoice_amount
                due_amount += residual_amount
                paid_amount += max(invoice_amount - residual_amount, 0.0)
                if invoice in overdue_invoices:
                    overdue_amount += residual_amount

            payments = posted_invoices.mapped("reconciled_payment_ids").filtered(
                lambda payment: payment.state in ("in_process", "paid")
                and payment.payment_type == "inbound"
                and payment.partner_type == "customer"
            )
            customer.invoice_ids = customer_invoices
            customer.invoice_count = len(posted_invoices)
            customer.account_payment_ids = payments
            customer.payment_count = len(payments)
            customer.last_payment_date = max(payments.mapped("date"), default=False)
            customer.financial_currency_id = currency
            customer.has_multiple_invoice_currencies = multiple_currencies
            # Never add nominal values from different currencies together.
            customer.total_invoiced_amount = invoiced_amount
            customer.total_paid_amount = paid_amount
            customer.total_due_amount = due_amount
            customer.overdue_amount = overdue_amount
            if not posted_invoices:
                customer.receivable_status = "none"
            elif not any(invoice.amount_residual > 0 for invoice in posted_invoices):
                customer.receivable_status = "paid"
            elif overdue_invoices:
                customer.receivable_status = "overdue"
            elif paid_amount > 0:
                customer.receivable_status = "partial"
            else:
                customer.receivable_status = "unpaid"
            customer.has_receivable = any(
                invoice.amount_residual > 0 for invoice in posted_invoices
            )
            customer.overdue_invoice_count = len(overdue_invoices)

    @api.model
    def _search_has_receivable(self, operator, value):
        if operator not in ("=", "!="):
            raise NotImplementedError("有应收筛选仅支持等于和不等于条件。")
        invoices = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
            ]
        )
        partner_ids = invoices.mapped("commercial_partner_id").ids
        positive = (operator == "=" and bool(value)) or (
            operator == "!=" and not bool(value)
        )
        if positive:
            return [("partner_id.commercial_partner_id", "in", partner_ids)] if partner_ids else [("id", "=", 0)]
        return [("partner_id.commercial_partner_id", "not in", partner_ids)]

    @api.model
    def _search_overdue_invoice_count(self, operator, value):
        if operator != ">" or float(value) != 0:
            raise NotImplementedError("逾期发票筛选仅支持大于零的条件。")
        today = fields.Date.context_today(self)
        invoices = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("invoice_date_due", "<", today),
                ("amount_residual", ">", 0),
            ]
        )
        partner_ids = invoices.mapped("commercial_partner_id").ids
        return [("partner_id.commercial_partner_id", "in", partner_ids)] if partner_ids else [("id", "=", 0)]

    def action_view_customer_invoices(self):
        self.ensure_one()
        if not self.partner_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "需要关联 Odoo 联系人",
                    "message": "请先创建或关联 Odoo 联系人，再查看客户发票。",
                    "type": "warning",
                    "sticky": False,
                },
            }
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_move_out_invoice_type"
        )
        action["domain"] = [
            ("commercial_partner_id", "=", self.partner_id.commercial_partner_id.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
        ]
        action["context"] = {
            "default_partner_id": self.partner_id.id,
            "default_move_type": "out_invoice",
        }
        return action

    @api.depends("image_1920")
    def _compute_image_128(self):
        for customer in self:
            customer.image_128 = image_process(
                customer.image_1920, size=(128, 128)
            ) if customer.image_1920 else False
            customer.has_image = bool(customer.image_1920)

    def write(self, vals):
        res = super().write(vals)
        # 照片变更时同步到已关联的 Odoo 联系人
        if "image_1920" in vals:
            for customer in self.filtered(lambda item: item.partner_id):
                customer.partner_id.image_1920 = customer.image_1920
        return res

    def _get_or_create_res_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id

        is_company = self.customer_type == "company"
        partner_name = self.company_name if is_company and self.company_name else self.name
        comment_lines = []
        if is_company and self.name and self.name != partner_name:
            comment_lines.append("客户名称：%s" % self.name)
        if self.notes:
            comment_lines.append(self.notes)
        partner = self.env["res.partner"].create(
            {
                "name": partner_name,
                "company_type": "company" if is_company else "person",
                "phone": self.phone,
                "email": self.email,
                "city": self.region,
                "comment": "\n".join(comment_lines) or False,
                "image_1920": self.image_1920 or False,
            }
        )
        self.partner_id = partner
        return partner

    def action_create_partner(self):
        self.ensure_one()
        partner = self._get_or_create_res_partner()
        return {
            "type": "ir.actions.act_window",
            "name": "Odoo 联系人",
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": partner.id,
            "target": "current",
        }

    def action_view_partner(self):
        self.ensure_one()
        if not self.partner_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "需要关联 Odoo 联系人",
                    "message": "请先创建或关联 Odoo 联系人。",
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_window",
            "name": "Odoo 联系人",
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": self.partner_id.id,
            "target": "current",
        }

    def action_view_customer_receivables(self):
        self.ensure_one()
        if not self.partner_id:
            return {"type": "ir.actions.act_window_close"}
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_move_out_invoice_type"
        )
        action["domain"] = [
            ("commercial_partner_id", "=", self.partner_id.commercial_partner_id.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("amount_residual", ">", 0),
        ]
        action["context"] = {"default_partner_id": self.partner_id.id}
        return action

    def action_view_customer_overdue_receivables(self):
        self.ensure_one()
        if not self.partner_id:
            return {"type": "ir.actions.act_window_close"}
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_move_out_invoice_type"
        )
        action["domain"] = [
            ("commercial_partner_id", "=", self.partner_id.commercial_partner_id.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_date_due", "<", fields.Date.context_today(self)),
            ("amount_residual", ">", 0),
        ]
        action["context"] = {"default_partner_id": self.partner_id.id}
        return action

    def action_view_customer_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_account_payments"
        )
        action["domain"] = [("id", "in", self.account_payment_ids.ids)]
        action["context"] = {
            "default_partner_id": self.partner_id.id,
            "default_payment_type": "inbound",
            "default_partner_type": "customer",
        }
        return action

    def action_view_cement_payments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "客户回款记录",
            "res_model": "cement.payment",
            "view_mode": "list,form",
            "domain": [("customer_id", "=", self.id)],
            "context": {"default_customer_id": self.id},
        }

    def action_view_customer_deliveries(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "客户交付记录",
            "res_model": "cement.delivery",
            "view_mode": "list,form",
            "domain": [("customer_id", "=", self.id)],
            "context": {"default_customer_id": self.id},
        }

    def action_view_customer_pickings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "客户发货单",
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("sale_id", "in", self.sale_order_ids.ids)],
        }

    def action_view_cement_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "客户销售订单",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("cement_customer_id", "=", self.id)],
            "context": {"default_cement_customer_id": self.id},
        }

    def action_view_confirmed_cement_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "客户已确认订单",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [
                ("cement_customer_id", "=", self.id),
                ("state", "in", ("sale", "done")),
            ],
            "context": {"default_cement_customer_id": self.id},
        }

    def action_new_cement_quotation(self):
        self.ensure_one()
        context = {"default_cement_customer_id": self.id}
        if self.partner_id:
            context["default_partner_id"] = self.partner_id.id
        return {
            "type": "ir.actions.act_window",
            "name": "新建报价",
            "res_model": "sale.order",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": context,
        }
