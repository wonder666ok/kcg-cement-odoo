from odoo import api, fields, models


from datetime import datetime, time, timedelta

import pytz


class SaleOrder(models.Model):
    _inherit = "sale.order"

    cement_customer_id = fields.Many2one(
        "cement.customer",
        string="水泥客户",
        ondelete="restrict",
    )
    cement_customer_company_name = fields.Char(
        string="水泥客户公司",
        related="cement_customer_id.company_name",
        readonly=True,
    )
    cement_customer_phone = fields.Char(
        string="水泥客户电话",
        related="cement_customer_id.phone",
        readonly=True,
    )
    cement_customer_region = fields.Char(
        string="水泥客户地区",
        related="cement_customer_id.region",
        readonly=True,
    )
    delivery_region = fields.Char(string="交付地区")
    delivery_address = fields.Text(string="交付地址")
    customer_reference = fields.Char(string="客户参考号")
    payment_term_note = fields.Char(string="付款条件说明")
    delivery_note = fields.Text(string="交付备注")
    sales_remark = fields.Text(string="销售备注")
    sales_source = fields.Selection(
        [
            ("whatsapp", "WhatsApp"),
            ("wechat", "微信"),
            ("phone", "电话"),
            ("visit", "客户拜访"),
            ("referral", "客户介绍"),
            ("other", "其他"),
        ],
        string="销售来源",
    )
    delivery_ids = fields.One2many(
        "cement.delivery", "sale_order_id", string="交付记录"
    )
    company_currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", readonly=True
    )
    cement_sales_amount_company_currency = fields.Monetary(
        string="销售额（公司本位币）",
        currency_field="company_currency_id",
        compute="_compute_cement_business_statistics",
        store=True,
    )
    cement_invoiced_amount = fields.Monetary(
        string="开票金额（公司本位币）",
        currency_field="company_currency_id",
        compute="_compute_cement_business_statistics",
        store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    cement_paid_amount = fields.Monetary(
        string="已收金额（公司本位币）",
        currency_field="company_currency_id",
        compute="_compute_cement_business_statistics",
        store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    cement_due_amount = fields.Monetary(
        string="未收金额（公司本位币）",
        currency_field="company_currency_id",
        compute="_compute_cement_business_statistics",
        store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    cement_payment_state = fields.Selection(
        [
            ("not_invoiced", "未开票"),
            ("not_paid", "未付款"),
            ("partial", "部分付款"),
            ("paid", "已付款"),
            ("overdue", "已逾期"),
        ],
        string="回款状态",
        compute="_compute_cement_business_statistics",
        store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    invoice_amount = fields.Monetary(
        string="开票金额", currency_field="company_currency_id",
        compute="_compute_cement_business_statistics", store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    paid_amount = fields.Monetary(
        string="已收款金额", currency_field="company_currency_id",
        compute="_compute_cement_business_statistics", store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    outstanding_amount = fields.Monetary(
        string="未收款金额", currency_field="company_currency_id",
        compute="_compute_cement_business_statistics", store=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    payment_status = fields.Selection(
        selection=[
            ("not_invoiced", "未开票"), ("not_paid", "未付款"),
            ("partial", "部分付款"), ("paid", "已付款"), ("overdue", "已逾期"),
        ], string="付款状态", compute="_compute_cement_business_statistics",
        store=True, groups="account.group_account_invoice,account.group_account_readonly",
    )
    cement_payment_count = fields.Integer(
        string="已收款笔数",
        compute="_compute_cement_business_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    cement_last_payment_date = fields.Date(
        string="最近付款日期",
        compute="_compute_cement_business_statistics",
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    cement_delivery_quantity = fields.Float(
        string="已交付数量",
        compute="_compute_cement_business_statistics",
        store=True,
    )
    cement_grade_analysis = fields.Char(
        string="水泥等级",
        compute="_compute_cement_business_statistics",
        store=True,
    )

    @api.depends(
        "amount_total",
        "currency_id",
        "company_id",
        "date_order",
        "state",
        "order_line.invoice_lines.move_id.state",
        "order_line.invoice_lines.move_id.move_type",
        "order_line.invoice_lines.move_id.amount_total",
        "order_line.invoice_lines.move_id.amount_residual",
        "order_line.invoice_lines.move_id.amount_total_signed",
        "order_line.invoice_lines.move_id.amount_residual_signed",
        "order_line.invoice_lines.move_id.payment_state",
        "order_line.invoice_lines.move_id.reconciled_payment_ids",
        "order_line.invoice_lines.move_id.reconciled_payment_ids.state",
        "order_line.invoice_lines.move_id.reconciled_payment_ids.date",
        "order_line.invoice_lines.price_total",
        "order_line.invoice_lines.sale_line_ids.order_id",
        "invoice_ids.state",
        "invoice_ids.move_type",
        "invoice_ids.amount_total",
        "invoice_ids.amount_residual",
        "invoice_ids.amount_total_signed",
        "invoice_ids.amount_residual_signed",
        "invoice_ids.company_currency_id",
        "invoice_ids.payment_state",
        "invoice_ids.invoice_line_ids.price_total",
        "invoice_ids.invoice_line_ids.sale_line_ids.order_id",
        "invoice_ids.currency_id",
        "invoice_ids.invoice_date",
        "invoice_ids.date",
        "invoice_ids.invoice_date_due",
        "invoice_ids.reconciled_payment_ids",
        "invoice_ids.reconciled_payment_ids.state",
        "invoice_ids.reconciled_payment_ids.date",
        "invoice_ids.reconciled_payment_ids.payment_type",
        "invoice_ids.reconciled_payment_ids.partner_type",
        "invoice_ids.invoice_date_due",
        "delivery_ids.quantity",
        "delivery_ids.state",
        "order_line.product_id.product_tmpl_id.cement_grade",
    )
    def _compute_cement_business_statistics(self):
        for order in self:
            company = order.company_id
            company_currency = company.currency_id
            sales_date = fields.Date.to_date(order.date_order) or fields.Date.context_today(order)
            if order.state in ("sale", "done"):
                order.cement_sales_amount_company_currency = order.currency_id._convert(
                    order.amount_total, company_currency, company, sales_date
                )
            else:
                order.cement_sales_amount_company_currency = 0.0

            invoices = order.invoice_ids.filtered(
                lambda invoice: invoice.state == "posted"
                and invoice.move_type == "out_invoice"
            )
            invoiced_amount = 0.0
            due_amount = 0.0
            has_overdue = False
            payments = self.env["account.payment"]
            for invoice in invoices:
                invoice_lines = invoice.invoice_line_ids.filtered(
                    lambda line: line.sale_line_ids
                )
                order_invoice_lines = invoice_lines.filtered(
                    lambda line: order in line.sale_line_ids.order_id
                )
                all_linked_orders = invoice_lines.mapped(
                    "sale_line_ids.order_id"
                )
                if len(all_linked_orders) > 1:
                    total_linked_value = sum(invoice_lines.mapped("price_total"))
                    order_linked_value = sum(order_invoice_lines.mapped("price_total"))
                    allocation = min(
                        max(order_linked_value / total_linked_value, 0.0), 1.0
                    ) if total_linked_value else 0.0
                else:
                    allocation = 1.0
                if not allocation:
                    continue

                has_overdue = has_overdue or bool(
                    invoice.invoice_date_due
                    and invoice.invoice_date_due < fields.Date.context_today(invoice)
                    and invoice.amount_residual > 0
                )

                conversion_date = invoice.invoice_date or invoice.date
                invoiced_amount += invoice.company_currency_id._convert(
                    abs(invoice.amount_total_signed) * allocation,
                    company_currency,
                    company,
                    conversion_date,
                )
                due_amount += invoice.company_currency_id._convert(
                    max(invoice.amount_residual_signed, 0.0) * allocation,
                    company_currency,
                    company,
                    fields.Date.context_today(invoice),
                )
                payments |= invoice.reconciled_payment_ids.filtered(
                    lambda payment: payment.state in ("in_process", "paid")
                    and payment.payment_type == "inbound"
                    and payment.partner_type == "customer"
                )
            order.cement_invoiced_amount = invoiced_amount
            order.cement_due_amount = due_amount
            order.cement_paid_amount = max(invoiced_amount - due_amount, 0.0)
            order.invoice_amount = invoiced_amount
            order.outstanding_amount = due_amount
            order.paid_amount = max(invoiced_amount - due_amount, 0.0)
            order.cement_payment_count = len(payments)
            order.cement_last_payment_date = max(payments.mapped("date"), default=False)
            if not invoices:
                order.cement_payment_state = "not_invoiced"
            elif due_amount <= 0:
                order.cement_payment_state = "paid"
            elif has_overdue:
                order.cement_payment_state = "overdue"
            elif order.cement_paid_amount > 0:
                order.cement_payment_state = "partial"
            else:
                order.cement_payment_state = "not_paid"
            order.payment_status = order.cement_payment_state

            order.cement_delivery_quantity = sum(
                order.delivery_ids.filtered(
                    lambda delivery: delivery.state == "delivered"
                ).mapped("quantity")
            )
            grades = sorted(
                {
                    grade
                    for grade in order.order_line.mapped(
                        "product_id.product_tmpl_id.cement_grade"
                    )
                    if grade
                }
            )
            order.cement_grade_analysis = ", ".join(grades) or False

    def action_view_cement_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "cement_sales.action_cement_payment_all"
        )
        payments = self.env["cement.payment"].search(
            [
                ("status", "=", "confirmed"),
                "|",
                ("sale_order_id", "=", self.id),
                ("invoice_id", "in", self.invoice_ids.ids),
            ]
        )
        action["domain"] = [("id", "in", payments.ids)]
        return action

    @api.model
    def get_cement_sales_dashboard_data(self, period="month"):
        """Return dashboard aggregates from existing cement and Odoo models."""
        period_labels = {
            "today": "今日",
            "week": "本周",
            "month": "本月",
            "quarter": "本季度",
            "year": "本年度",
        }
        if period not in period_labels:
            period = "month"

        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        if month_start.month == 12:
            next_month_start = month_start.replace(
                year=month_start.year + 1, month=1
            )
        else:
            next_month_start = month_start.replace(month=month_start.month + 1)
        if period == "today":
            date_from, date_to = today, today + timedelta(days=1)
        elif period == "week":
            date_from = today - timedelta(days=today.weekday())
            date_to = date_from + timedelta(days=7)
        elif period == "year":
            date_from = today.replace(month=1, day=1)
            date_to = date_from.replace(year=date_from.year + 1)
        elif period == "quarter":
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            date_from = today.replace(month=quarter_month, day=1)
            date_to = date_from + timedelta(days=93)
            date_to = date_to.replace(day=1)
            if date_to <= date_from:
                date_to = date_from.replace(year=date_from.year + 1)
        else:
            date_from = today.replace(day=1)
            if date_from.month == 12:
                date_to = date_from.replace(year=date_from.year + 1, month=1)
            else:
                date_to = date_from.replace(month=date_from.month + 1)

        timezone_name = self.env.context.get("tz") or self.env.user.tz or "UTC"
        try:
            user_timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            user_timezone = pytz.UTC

        def utc_midnight(local_date):
            local_value = user_timezone.localize(
                datetime.combine(local_date, time.min), is_dst=None
            )
            return local_value.astimezone(pytz.UTC).replace(tzinfo=None)

        company = self.env.company
        currency = company.currency_id
        date_from_datetime = fields.Datetime.to_string(utc_midnight(date_from))
        date_to_datetime = fields.Datetime.to_string(utc_midnight(date_to))
        month_start_datetime = fields.Datetime.to_string(utc_midnight(month_start))
        next_month_start_datetime = fields.Datetime.to_string(
            utc_midnight(next_month_start)
        )
        customer_model = self.env["cement.customer"].with_context(active_test=False)
        customers = customer_model.search([], order="name, id")
        customer_by_id = {customer.id: customer for customer in customers}

        reps = {}

        def ensure_rep(user):
            rep_id = user.id if user else 0
            if rep_id not in reps:
                reps[rep_id] = {
                    "id": rep_id or False,
                    "name": user.name if user else "未分配",
                    "customer_count": 0,
                    "followup_count": 0,
                    "quotation_count": 0,
                    "confirmed_order_count": 0,
                    "sales_amount": 0.0,
                    "sales_quantity": 0.0,
                    "sales_bags": 0.0,
                    "payment_amount": 0.0,
                    "receivable_amount": 0.0,
                }
            return reps[rep_id]

        customer_totals = {
            customer.id: {
                "order_count": 0,
                "sales_bags": 0.0,
                "sales_amount": 0.0,
                "delivered_quantity": 0.0,
                "invoice_amount": 0.0,
                "payment_amount": 0.0,
                "receivable_amount": 0.0,
            }
            for customer in customers
        }
        for customer in customers:
            ensure_rep(customer.sales_person)["customer_count"] += 1

        active_customers = sum(
            1 for customer in customers if customer.active and customer.customer_status == "active"
        )
        Followup = self.env["cement.followup"]
        today_followups = Followup.search(
            [("state", "=", "pending"), ("next_followup_date", "=", today)],
            order="salesperson_id, customer_id, id",
        )
        overdue_followups = Followup.search(
            [
                ("state", "=", "pending"),
                ("next_followup_date", "!=", False),
                ("next_followup_date", "<", today),
            ],
            order="next_followup_date, salesperson_id, customer_id, id",
        )
        today_followup_count = len(today_followups)
        overdue_followup_count = len(overdue_followups)
        today_followup_rows = [
            {
                "id": item.id,
                "customer": item.customer_id.name,
                "salesperson": item.salesperson_id.name or "未分配",
                "followup_type": dict(item._fields["followup_type"].selection).get(
                    item.followup_type, "其他"
                ),
                "date": fields.Date.to_string(item.next_followup_date),
                "state": dict(item._fields["state"].selection).get(item.state),
            }
            for item in today_followups[:100]
        ]
        overdue_followup_rows = [
            {
                "id": item.id,
                "customer": item.customer_id.name,
                "salesperson": item.salesperson_id.name or "未分配",
                "date": fields.Date.to_string(item.next_followup_date),
                "overdue_days": (today - item.next_followup_date).days,
                "state": dict(item._fields["state"].selection).get(item.state),
            }
            for item in overdue_followups[:100]
        ]

        company_domain = [("company_id", "=", company.id)]
        period_domain = [
            ("date_order", ">=", date_from_datetime),
            ("date_order", "<", date_to_datetime),
        ]
        period_orders = self.search(company_domain + period_domain)
        quotations = period_orders.filtered(
            lambda order: order.state in ("draft", "sent")
        )
        confirmed_orders = period_orders.filtered(
            lambda order: order.state in ("sale", "done")
        )

        sales_amount = 0.0
        for order in quotations:
            ensure_rep(order.user_id)["quotation_count"] += 1
        for order in confirmed_orders:
            customer_id = order.cement_customer_id.id
            if customer_id in customer_totals:
                customer_totals[customer_id]["order_count"] += 1
                customer_totals[customer_id]["sales_amount"] += (
                    order.cement_sales_amount_company_currency
                )
            rep = ensure_rep(order.user_id)
            rep["confirmed_order_count"] += 1
            if customer_id:
                rep.setdefault("_period_customer_ids", set()).add(customer_id)
            rep["sales_amount"] += order.cement_sales_amount_company_currency
            sales_amount += order.cement_sales_amount_company_currency

        monthly_orders = self.search(
            company_domain
            + [
                ("state", "in", ("sale", "done")),
                ("date_order", ">=", month_start_datetime),
                ("date_order", "<", next_month_start_datetime),
            ]
        )
        month_sales_amount = sum(
            monthly_orders.mapped("cement_sales_amount_company_currency")
        )
        month_sales_bags = sum(
            self.env["sale.order.line"]
            .search([("order_id", "in", monthly_orders.ids), ("display_type", "=", False)])
            .mapped("bag_count")
        ) if monthly_orders else 0.0

        def shift_month(value, offset):
            month_index = value.year * 12 + value.month - 1 + offset
            year, month_index = divmod(month_index, 12)
            return value.replace(year=year, month=month_index + 1, day=1)

        trend_start = shift_month(month_start, -11)
        trend_start_datetime = fields.Datetime.to_string(utc_midnight(trend_start))
        trend_rows_by_key = {}
        for offset in range(12):
            bucket_date = shift_month(trend_start, offset)
            key = bucket_date.strftime("%Y-%m")
            trend_rows_by_key[key] = {
                "month": key,
                "order_count": 0,
                "sales_amount": 0.0,
                "sales_bags": 0.0,
            }
        trend_orders = self.search(
            company_domain
            + [
                ("state", "in", ("sale", "done")),
                ("date_order", ">=", trend_start_datetime),
                ("date_order", "<", next_month_start_datetime),
            ]
        )
        for order in trend_orders:
            local_order_date = fields.Datetime.context_timestamp(
                order, order.date_order
            ).date()
            key = local_order_date.strftime("%Y-%m")
            bucket = trend_rows_by_key.get(key)
            if bucket:
                bucket["order_count"] += 1
                bucket["sales_amount"] += order.cement_sales_amount_company_currency
        if trend_orders:
            trend_lines = self.env["sale.order.line"].search(
                [("order_id", "in", trend_orders.ids), ("display_type", "=", False)]
            )
            for line in trend_lines:
                local_order_date = fields.Datetime.context_timestamp(
                    line.order_id, line.order_id.date_order
                ).date()
                bucket = trend_rows_by_key.get(local_order_date.strftime("%Y-%m"))
                if bucket:
                    bucket["sales_bags"] += line.bag_count or 0.0

        sales_quantity = 0.0
        sales_bags = 0.0
        grade_totals = {}
        order_grade_weights = {}
        if confirmed_orders:
            order_lines = self.env["sale.order.line"].search(
                [("order_id", "in", confirmed_orders.ids), ("display_type", "=", False)]
            )
            for line in order_lines:
                quantity = line.product_uom_qty or 0.0
                bags = line.bag_count or 0.0
                sales_quantity += quantity
                sales_bags += bags
                order = line.order_id
                rep = ensure_rep(order.user_id)
                rep["sales_quantity"] += quantity
                rep["sales_bags"] += bags
                grade = line.product_id.product_tmpl_id.cement_grade or "其他"
                grade_totals.setdefault(
                    grade,
                    {
                        "quantity": 0.0,
                        "bags": 0.0,
                        "sales_amount": 0.0,
                        "order_ids": set(),
                    },
                )
                grade_totals[grade]["quantity"] += quantity
                grade_totals[grade]["bags"] += bags
                grade_totals[grade]["order_ids"].add(order.id)
                order_grade_weights.setdefault(order.id, {})
                order_grade_weights[order.id][grade] = (
                    order_grade_weights[order.id].get(grade, 0.0)
                    + abs(line.price_subtotal)
                )
                customer_id = order.cement_customer_id.id
                if customer_id in customer_totals:
                    customer_totals[customer_id]["sales_bags"] += bags

        for order in confirmed_orders:
            grade_weights = order_grade_weights.get(order.id, {})
            total_weight = sum(grade_weights.values())
            if total_weight:
                for grade, weight in grade_weights.items():
                    grade_totals[grade]["sales_amount"] += (
                        order.cement_sales_amount_company_currency
                        * weight
                        / total_weight
                    )

        deliveries = self.env["cement.delivery"].search(
            [
                ("state", "=", "delivered"),
                ("delivery_date", ">=", date_from),
                ("delivery_date", "<", date_to),
                ("sale_order_id.company_id", "=", company.id),
            ]
        )
        delivered_quantity = sum(deliveries.mapped("quantity"))
        delivered_bags = sum(deliveries.mapped("bag_count"))
        for delivery in deliveries:
            customer_id = delivery.customer_id.id
            if customer_id in customer_totals:
                customer_totals[customer_id]["delivered_quantity"] += delivery.quantity

        pending_deliveries = self.env["cement.delivery"].search(
            [
                ("state", "in", ("draft", "scheduled", "in_transit")),
                ("sale_order_id.company_id", "=", company.id),
            ],
            order="delivery_date, id",
            limit=200,
        )
        pending_delivery_rows = [
            {
                "id": delivery.id,
                "order_id": delivery.sale_order_id.id,
                "order": delivery.sale_order_id.name,
                "customer": delivery.customer_id.name,
                "grade": delivery.cement_grade or "其他",
                "quantity": delivery.bag_count or delivery.quantity or 0.0,
                "date": fields.Date.to_string(delivery.delivery_date)
                if delivery.delivery_date
                else False,
                "state": dict(delivery._fields["state"].selection).get(
                    delivery.state, delivery.state
                ),
            }
            for delivery in pending_deliveries
        ]

        followups = Followup.search(
            [
                ("date", ">=", date_from),
                ("date", "<", date_to),
                ("state", "!=", "cancelled"),
            ]
        )
        for followup in followups:
            ensure_rep(followup.salesperson_id)["followup_count"] += 1

        has_accounting_access = self.env.user.has_group(
            "account.group_account_invoice"
        ) or self.env.user.has_group("account.group_account_readonly")
        invoice_amount = 0.0
        reconciled_payment_amount = 0.0
        receivable_amount = 0.0
        overdue_receivable_amount = 0.0
        receivable_rows = []
        reconciled_partial_ids = set()
        invoices = self.env["account.move"]
        if has_accounting_access:
            linked_invoice_ids = (
                self.env["sale.order.line"]
                .search([("order_id", "in", confirmed_orders.ids)])
                .mapped("invoice_lines.move_id").ids
                if confirmed_orders
                else []
            )
            invoices = self.env["account.move"].search(
                [
                    ("id", "in", linked_invoice_ids),
                    ("company_id", "=", company.id),
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                ]
            )
            customers_by_partner = {}
            for customer in customers.filtered(lambda item: item.partner_id):
                commercial_partner = customer.partner_id.commercial_partner_id
                customers_by_partner.setdefault(commercial_partner.id, []).append(
                    customer.id
                )

            def invoice_order_weights(invoice):
                weights = {}
                for invoice_line in invoice.invoice_line_ids.filtered(
                    lambda item: not item.display_type and item.sale_line_ids
                ):
                    linked_lines = invoice_line.sale_line_ids.filtered(
                        lambda line: line.order_id in confirmed_orders
                    )
                    line_weights = {}
                    for sale_line in linked_lines:
                        order_id = sale_line.order_id.id
                        line_weights[order_id] = line_weights.get(order_id, 0.0) + abs(
                            sale_line.price_subtotal
                        )
                    total_weight = sum(line_weights.values())
                    if not total_weight:
                        continue
                    for order_id, weight in line_weights.items():
                        weights[order_id] = weights.get(order_id, 0.0) + (
                            abs(invoice_line.price_subtotal) * weight / total_weight
                        )
                return weights

            def assign_invoice_amount(invoice, amount, field_name):
                weights = invoice_order_weights(invoice)
                total_weight = sum(weights.values())
                if total_weight:
                    for order_id, weight in weights.items():
                        order = self.browse(order_id)
                        customer_id = order.cement_customer_id.id
                        share = amount * weight / total_weight
                        if customer_id in customer_totals:
                            customer_totals[customer_id][field_name] += share
                        if field_name == "receivable_amount":
                            ensure_rep(order.user_id)[field_name] += share
                    return
                partner_customer_ids = customers_by_partner.get(
                    invoice.commercial_partner_id.id, []
                )
                if len(partner_customer_ids) == 1:
                    customer_id = partner_customer_ids[0]
                    customer_totals[customer_id][field_name] += amount
                    if field_name == "receivable_amount":
                        ensure_rep(customer_by_id[customer_id].sales_person)[
                            field_name
                        ] += amount

            for invoice in invoices:
                invoice_total = abs(invoice.amount_total_signed or 0.0)
                residual = max(invoice.amount_residual_signed or 0.0, 0.0)
                invoice_amount += invoice_total
                assign_invoice_amount(invoice, invoice_total, "invoice_amount")

                receivable_lines = invoice.line_ids.filtered(
                    lambda line: line.account_id.account_type == "asset_receivable"
                )
                partials = (
                    receivable_lines.mapped("matched_debit_ids")
                    | receivable_lines.mapped("matched_credit_ids")
                )
                new_partials = partials.filtered(
                    lambda partial: partial.id not in reconciled_partial_ids
                )
                reconciled_partial_ids.update(new_partials.ids)
                reconciled_payment_amount += sum(new_partials.mapped("amount"))
                if residual:
                    receivable_amount += residual
                    assign_invoice_amount(invoice, residual, "receivable_amount")
                    if invoice.invoice_date_due and invoice.invoice_date_due < today:
                        overdue_receivable_amount += residual
                    receivable_rows.append(
                        {
                            "id": invoice.id,
                            "customer": invoice.partner_id.display_name,
                            "name": invoice.name or invoice.ref or invoice.display_name,
                            "invoice_date": fields.Date.to_string(invoice.invoice_date)
                            if invoice.invoice_date
                            else False,
                            "due_date": fields.Date.to_string(invoice.invoice_date_due)
                            if invoice.invoice_date_due
                            else False,
                            "currency": invoice.currency_id.symbol
                            or invoice.currency_id.name,
                            "currency_decimals": invoice.currency_id.decimal_places,
                            "amount": abs(invoice.amount_total or 0.0),
                            "paid": max(
                                abs(invoice.amount_total or 0.0)
                                - abs(invoice.amount_residual or 0.0),
                                0.0,
                            ),
                            "residual": abs(invoice.amount_residual or 0.0),
                            "status": dict(
                                invoice._fields["payment_state"].selection
                            ).get(invoice.payment_state, invoice.payment_state),
                        }
                    )

        payment_scopes = []
        if confirmed_orders:
            payment_scopes.append(("sale_order_id", "in", confirmed_orders.ids))
        if invoices:
            payment_scopes.append(("invoice_id", "in", invoices.ids))
        payments = self.env["cement.payment"]
        if payment_scopes:
            payment_domain = [("status", "=", "confirmed")]
            if len(payment_scopes) == 2:
                payment_domain += ["|"] + payment_scopes
            else:
                payment_domain += payment_scopes
            payments = self.env["cement.payment"].search(payment_domain)
        payment_amount = 0.0
        for payment in payments:
            payment_company = (
                payment.sale_order_id.company_id
                or payment.invoice_id.company_id
                or company
            )
            payment_currency = payment.currency_id or currency
            converted_amount = payment_currency._convert(
                payment.amount,
                currency,
                payment_company,
                payment.payment_date or today,
            )
            payment_amount += converted_amount
            if payment.customer_id.id in customer_totals:
                customer_totals[payment.customer_id.id]["payment_amount"] += converted_amount
            ensure_rep(payment.salesperson_id)["payment_amount"] += converted_amount

        salesperson_rows = sorted(
            reps.values(), key=lambda row: (row["name"] == "未分配", row["name"].casefold())
        )
        for row in salesperson_rows:
            row["customer_count"] = len(row.pop("_period_customer_ids", set()))
        grade_rows = [
            {
                "grade": grade,
                "quantity": values["quantity"],
                "bags": values["bags"],
                "sales_amount": currency.round(values["sales_amount"]),
                "order_count": len(values["order_ids"]),
            }
            for grade, values in sorted(grade_totals.items(), key=lambda item: item[0].casefold())
        ]
        customer_rows = []
        for customer in customers:
            values = customer_totals[customer.id]
            customer_rows.append(
                {
                    "id": customer.id,
                    "name": customer.name,
                    "salesperson": customer.sales_person.name or "未分配",
                    "region": customer.region or "",
                    "last_order_date": fields.Date.to_string(customer.last_order_date)
                    if customer.last_order_date
                    else False,
                    **values,
                    "last_followup_date": fields.Date.to_string(
                        customer.last_followup_date
                    )
                    if customer.last_followup_date
                    else False,
                    "next_followup_date": fields.Date.to_string(
                        customer.next_followup_date
                    )
                    if customer.next_followup_date
                    else False,
                }
            )

        return {
            "period": period,
            "period_label": period_labels[period],
            "date_from": fields.Date.to_string(date_from),
            "date_to_exclusive": fields.Date.to_string(date_to),
            "date_from_datetime": date_from_datetime,
            "date_to_datetime": date_to_datetime,
            "month_start": fields.Date.to_string(month_start),
            "next_month_start_exclusive": fields.Date.to_string(next_month_start),
            "month_start_datetime": month_start_datetime,
            "next_month_start_datetime": next_month_start_datetime,
            "today": fields.Date.to_string(today),
            "currency": {
                "name": currency.name,
                "symbol": currency.symbol or currency.name,
                "decimal_places": currency.decimal_places,
            },
            "has_accounting_access": has_accounting_access,
            "company_id": company.id,
            "linked_invoice_ids": invoices.ids,
            "linked_order_ids": confirmed_orders.ids,
            "linked_payment_ids": payments.ids,
            "kpis": {
                "customer_count": len(customers),
                "active_customer_count": active_customers,
                "today_followup_count": today_followup_count,
                "overdue_followup_count": overdue_followup_count,
                "quotation_count": len(quotations),
                "confirmed_order_count": len(confirmed_orders),
                "sales_amount": currency.round(sales_amount),
                "sales_quantity": sales_quantity,
                "sales_bags": sales_bags,
                "delivered_quantity": delivered_quantity,
                "delivered_bags": delivered_bags,
                "invoice_amount": currency.round(invoice_amount),
                "payment_amount": currency.round(payment_amount),
                "reconciled_payment_amount": currency.round(
                    reconciled_payment_amount
                ),
                "receivable_amount": currency.round(receivable_amount),
                "overdue_receivable_amount": currency.round(
                    overdue_receivable_amount
                ),
                "pending_delivery_count": len(pending_deliveries),
                "month_sales_amount": currency.round(month_sales_amount),
                "month_sales_bags": month_sales_bags,
            },
            "trend": [
                {
                    **bucket,
                    "sales_amount": currency.round(bucket["sales_amount"]),
                }
                for bucket in trend_rows_by_key.values()
            ],
            "today_followups": today_followup_rows,
            "overdue_followups": overdue_followup_rows,
            "pending_deliveries": pending_delivery_rows,
            "receivables": receivable_rows[:200],
            "salespersons": salesperson_rows,
            "grades": grade_rows,
            "customers": customer_rows,
        }

    @api.model
    def action_open_cement_sales_analysis(self):
        pivot_view = self.env.ref(
            "cement_sales.view_cement_sales_analysis_pivot"
        )
        return {
            "type": "ir.actions.act_window",
            "name": "水泥销售分析",
            "res_model": "sale.order",
            "view_mode": "pivot,graph,list",
            "views": [
                (pivot_view.id, "pivot"),
                (self.env.ref("cement_sales.view_cement_sales_analysis_graph").id, "graph"),
                (self.env.ref("cement_sales.view_cement_sales_analysis_list").id, "list"),
            ],
            "domain": [
                ("company_id", "=", self.env.company.id),
                ("cement_customer_id", "!=", False),
                ("state", "in", ("sale", "done")),
            ],
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    bag_count = fields.Float(string="袋数")


class AccountPayment(models.Model):
    _inherit = "account.payment"

    cement_sale_order_ids = fields.Many2many(
        "sale.order",
        string="关联销售订单",
        compute="_compute_cement_sale_order_ids",
    )

    @api.depends("reconciled_invoice_ids.invoice_line_ids.sale_line_ids.order_id")
    def _compute_cement_sale_order_ids(self):
        for payment in self:
            invoices = payment.reconciled_invoice_ids.filtered(
                lambda invoice: invoice.move_type == "out_invoice"
            )
            payment.cement_sale_order_ids = invoices.mapped(
                "invoice_line_ids.sale_line_ids.order_id"
            )
