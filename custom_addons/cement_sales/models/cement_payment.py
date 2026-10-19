from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)

# 原生收款可同步的过账状态（Odoo 18 起收款状态含 in_process / paid）
NATIVE_SYNC_STATES = ("posted", "in_process", "paid")
# 日记账类型 -> 回款方式
JOURNAL_TYPE_TO_METHOD = {"cash": "cash", "bank": "bank_transfer"}


class CementPayment(models.Model):
    _name = "cement.payment"
    _description = "KCG Cement Business Payment"
    _order = "payment_date desc, id desc"
    _allowed_status_transitions = {
        "draft": {"confirmed", "cancelled"},
        "confirmed": set(),
        "cancelled": {"draft"},
    }

    payment_date = fields.Date(
        string="回款日期", required=True, default=fields.Date.context_today
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        compute="_compute_company_id",
        store=True,
    )
    customer_id = fields.Many2one(
        "cement.customer",
        string="客户",
        required=True,
        ondelete="restrict",
        index=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="销售订单",
        ondelete="restrict",
        domain="[('cement_customer_id', '=', customer_id)]",
    )
    customer_commercial_partner_id = fields.Many2one(
        "res.partner",
        related="customer_id.partner_id.commercial_partner_id",
        readonly=True,
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="发票",
        ondelete="restrict",
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('commercial_partner_id', '=', customer_commercial_partner_id)]",
    )
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="收款日记账",
        check_company=True,
        ondelete="restrict",
        groups="account.group_account_invoice",
        domain="[('company_id', '=', company_id), ('type', 'in', ['bank', 'cash'])]",
    )
    native_payment_id = fields.Many2one(
        "account.payment",
        string="原生会计付款",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount = fields.Monetary(
        string="回款金额", currency_field="currency_id", required=True
    )
    payment_method = fields.Selection(
        [
            ("cash", "现金"),
            ("bank_transfer", "银行转账"),
            ("mobile_money", "Mobile Money"),
            ("cheque", "支票"),
            ("other", "其他"),
        ],
        string="回款方式",
    )
    reference = fields.Char(string="回款凭证号")
    status = fields.Selection(
        [
            ("draft", "草稿"),
            ("confirmed", "已确认"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        copy=False,
        index=True,
    )
    notes = fields.Text(string="备注")
    salesperson_id = fields.Many2one(
        "res.users",
        string="销售员",
        default=lambda self: self.env.user,
        index=True,
    )

    _sql_constraints = [
        (
            "native_payment_unique",
            "unique(native_payment_id)",
            "An Odoo payment can only be linked to one cement payment.",
        ),
    ]

    @api.depends("invoice_id.company_id", "sale_order_id.company_id")
    def _compute_company_id(self):
        for payment in self:
            payment.company_id = (
                payment.invoice_id.company_id
                or payment.sale_order_id.company_id
                or self.env.company
            )

    @api.onchange("payment_method", "invoice_id", "sale_order_id")
    def _onchange_payment_journal_domain(self):
        self.ensure_one()
        company = (
            self.invoice_id.company_id
            or self.sale_order_id.company_id
            or self.env.company
        )
        journal_types = self._expected_journal_types()
        return {
            "domain": {
                "payment_journal_id": [
                    ("company_id", "=", company.id),
                    ("type", "in", list(journal_types)),
                ]
            }
        }

    def _expected_journal_types(self):
        self.ensure_one()
        if self.payment_method == "cash":
            return ("cash",)
        if self.payment_method in ("bank_transfer", "mobile_money", "cheque"):
            return ("bank",)
        if self.payment_method == "other":
            return ("bank", "cash")
        return ()

    def _get_payment_journal_and_method_line(self, company):
        self.ensure_one()
        journal_types = self._expected_journal_types()
        if not journal_types:
            raise ValidationError(_("请选择回款方式后再确认。"))

        Journal = self.env["account.journal"].with_company(company)
        if self.payment_journal_id:
            journal = self.payment_journal_id
            if journal.company_id != company or journal.type not in journal_types:
                raise ValidationError(_("所选收款日记账与公司或回款方式不匹配。"))
        else:
            journals = Journal.search(
                [
                    ("company_id", "=", company.id),
                    ("type", "in", list(journal_types)),
                ]
            )
            journals = journals.filtered(
                lambda item: item._get_available_payment_method_lines("inbound")
                .filtered(lambda line: line.code == "manual")
            )
            if not journals:
                if self.payment_method == "cash":
                    raise ValidationError(
                        _("当前公司没有配置带手工入账方式的现金日记账，请先配置收款日记账。")
                    )
                raise ValidationError(
                    _("当前公司没有可用于该回款方式的银行/现金日记账及手工收款方式。")
                )
            if len(journals) > 1:
                raise ValidationError(_("找到多个收款日记账，请在回款表单中明确选择。"))
            journal = journals

        if journal.currency_id and journal.currency_id != self.currency_id:
            raise ValidationError(
                _("所选日记账币种与回款币种不一致，请选择兼容的日记账。")
            )
        method_lines = journal._get_available_payment_method_lines("inbound").filtered(
            lambda line: line.code == "manual"
        )
        if len(method_lines) != 1:
            raise ValidationError(
                _("所选日记账必须且只能配置一个可用的手工收款方式。")
            )
        return journal, method_lines

    def _prepare_native_payment(self):
        self.ensure_one()
        invoice = self.invoice_id
        if invoice:
            if invoice.move_type != "out_invoice":
                raise ValidationError(_("关联单据必须是客户发票。"))
            if invoice.state != "posted":
                raise ValidationError(_("只能确认已过账客户发票的回款。"))
            customer_partner = self.customer_id.partner_id
            if (
                not customer_partner
                or invoice.commercial_partner_id
                != customer_partner.commercial_partner_id
            ):
                raise ValidationError(_("发票客户与回款客户不匹配。"))
            if invoice.currency_id != self.currency_id:
                raise ValidationError(_("回款币种必须与关联发票币种一致。"))
            if self.amount <= 0:
                raise ValidationError(_("回款金额必须大于 0。"))
            if invoice.currency_id.compare_amounts(
                self.amount, invoice.amount_residual
            ) > 0:
                raise ValidationError(_("回款金额不能超过该发票当前未付款金额。"))
            if invoice.currency_id.is_zero(invoice.amount_residual):
                raise ValidationError(_("该发票已经结清，不能再登记回款。"))
            company = invoice.company_id
            if self.sale_order_id and self.sale_order_id.company_id != company:
                raise ValidationError(_("发票与销售订单必须属于同一公司。"))
            receivable_lines = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
                and not line.reconciled
            )
            if not receivable_lines:
                raise ValidationError(_("发票没有可核销的未结应收分录。"))
            receivable_accounts = receivable_lines.mapped("account_id")
            if len(receivable_accounts) != 1:
                raise ValidationError(
                    _("发票包含多个应收科目，无法安全地用单笔收款自动核销。")
                )
        else:
            if self.amount <= 0:
                raise ValidationError(_("回款金额必须大于 0。"))
            company = self.sale_order_id.company_id or self.env.company
            customer_partner = self.customer_id.partner_id
            if not customer_partner:
                raise ValidationError(
                    _("请先为客户创建或关联 Odoo 联系人，再确认回款。")
                )
            if self.sale_order_id and self.sale_order_id.company_id != company:
                raise ValidationError(_("销售订单与回款必须属于同一公司。"))
            receivable_lines = self.env["account.move.line"]

        partner = (
            invoice.commercial_partner_id
            if invoice
            else customer_partner.commercial_partner_id
        )
        journal, method_lines = self._get_payment_journal_and_method_line(company)
        vals = {
            "cement_payment_id": self.id,
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "date": self.payment_date,
            "company_id": company.id,
            "journal_id": journal.id,
            "payment_method_line_id": method_lines.id,
            "payment_reference": self.reference or "",
            "memo": self.reference or _("Cement payment %s", self.id),
        }
        if invoice:
            vals["destination_account_id"] = receivable_lines[0].account_id.id
        return company, invoice, receivable_lines, vals

    @api.onchange("customer_id")
    def _onchange_customer_id(self):
        if (
            self.sale_order_id
            and self.sale_order_id.cement_customer_id != self.customer_id
        ):
            self.sale_order_id = False
        if self.invoice_id and (
            not self.customer_id.partner_id
            or self.invoice_id.commercial_partner_id
            != self.customer_id.partner_id.commercial_partner_id
        ):
            self.invoice_id = False
        return {
            "domain": {
                "sale_order_id": [
                    ("cement_customer_id", "=", self.customer_id.id or False)
                ],
                "invoice_id": [
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    (
                    "commercial_partner_id",
                    "=",
                    self.customer_commercial_partner_id.id or False,
                    ),
                ],
            }
        }

    @api.constrains("amount")
    def _check_positive_amount(self):
        for payment in self:
            if payment.amount <= 0:
                raise ValidationError(_("回款金额必须大于 0。"))

    @api.constrains("customer_id", "sale_order_id", "invoice_id")
    def _check_customer_links(self):
        for payment in self:
            if (
                payment.sale_order_id
                and payment.sale_order_id.cement_customer_id != payment.customer_id
            ):
                raise ValidationError(_("所选销售订单不属于该客户。"))
            if payment.invoice_id:
                customer_partner = payment.customer_id.partner_id
                if (
                    payment.invoice_id.move_type != "out_invoice"
                    or payment.invoice_id.state != "posted"
                    or not customer_partner
                    or payment.invoice_id.commercial_partner_id
                    != customer_partner.commercial_partner_id
                ):
                    raise ValidationError(
                        _("发票必须是该客户关联联系人的已过账客户发票。")
                    )

    @api.model_create_multi
    def create(self, vals_list):
        if any(values.get("status", "draft") != "draft" for values in vals_list):
            raise UserError(_("新建回款必须从草稿状态开始。"))
        return super().create(vals_list)

    def action_confirm(self):
        if not self.env.user.has_group("account.group_account_invoice"):
            raise UserError(_("需要会计/发票权限才能过账原生收款。"))
        for payment in self:
            if payment.status != "draft":
                raise UserError(_("只有草稿回款可以确认。"))
            if payment.native_payment_id:
                raise ValidationError(
                    _("该回款已经关联原生会计付款，不能再次创建付款。")
                )
            company, invoice, invoice_lines, payment_vals = (
                payment._prepare_native_payment()
            )
            native_payment = self.env["account.payment"].with_company(company).create(
                payment_vals
            )
            native_payment.action_post()
            if not native_payment.move_id or native_payment.move_id.state != "posted":
                raise ValidationError(_("原生会计付款未能成功过账，回款确认已取消。"))

            if invoice:
                receivable_account = invoice_lines[0].account_id
                payment_lines = native_payment.move_id.line_ids.filtered(
                    lambda line: line.account_id == receivable_account
                    and line.account_id.account_type == "asset_receivable"
                    and not line.reconciled
                )
                invoice_lines = invoice_lines.filtered(
                    lambda line: line.account_id == receivable_account
                    and not line.reconciled
                )
                if not payment_lines or not invoice_lines:
                    raise ValidationError(_("未找到可核销的发票和付款应收分录。"))
                (invoice_lines | payment_lines).reconcile()

            payment.native_payment_id = native_payment
            payment.status = "confirmed"
        return True

    def action_cancel(self):
        for payment in self:
            if payment.status != "draft":
                raise UserError(_("只有草稿回款可以取消。"))
            payment.status = "cancelled"
        return True

    def action_reset_to_draft(self):
        for payment in self:
            if payment.status != "cancelled":
                raise UserError(_("只有已取消回款可以重置为草稿。"))
            payment.status = "draft"
        return True

    def write(self, vals):
        if "status" in vals:
            target_status = vals["status"]
            for payment in self:
                allowed = self._allowed_status_transitions.get(payment.status, set())
                if target_status != payment.status and target_status not in allowed:
                    raise UserError(
                        _("不允许将回款状态从“%s”变更为“%s”。")
                        % (payment.status, target_status)
                    )
        return super().write(vals)

    def unlink(self):
        if any(payment.status == "confirmed" for payment in self):
            raise UserError(_("已确认的回款不能直接删除。"))
        return super().unlink()

    def action_open_native_payment(self):
        self.ensure_one()
        if not self.native_payment_id:
            raise UserError(_("该回款尚未关联原生会计付款。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("原生会计付款"),
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.native_payment_id.id,
            "target": "current",
        }

    # ------------------------------------------------------------------
    # 反向同步：原生收款（account.payment） -> 回款（cement.payment）
    #
    # 之前只有「回款 -> 原生付款」单向同步，导致在发票上登记付款、
    # 或在会计模块直接录入收款时，钱收到了但回款模块里查不到。
    # ------------------------------------------------------------------
    _native_sync_states = NATIVE_SYNC_STATES
    _journal_type_to_method = JOURNAL_TYPE_TO_METHOD

    @api.model
    def _find_cement_customer_for_partner(self, partner):
        """按联系人或其商业伙伴匹配水泥客户，找不到返回空记录集。"""
        if not partner:
            return self.env["cement.customer"]
        partner_ids = (partner | partner.commercial_partner_id).ids
        return (
            self.env["cement.customer"]
            .sudo()
            .search([("partner_id", "in", partner_ids)], order="id", limit=1)
        )

    @api.model
    def _prepare_cement_payment_vals_from_native(self, payment):
        """根据原生收款构造回款 vals；客户无法匹配时返回 None。"""
        customer = self._find_cement_customer_for_partner(payment.partner_id)
        if not customer:
            return None

        invoices = payment.reconciled_invoice_ids.filtered(
            lambda move: move.move_type == "out_invoice"
            and move.state == "posted"
        )
        invoice = invoices[:1] if invoices else self.env["account.move"]

        sale_order = self.env["sale.order"]
        if invoice:
            sale_order = invoice.invoice_line_ids.sale_line_ids.order_id.filtered(
                lambda order: order.cement_customer_id == customer
            )[:1]
        if not sale_order:
            sale_order = (
                self.env["sale.order"]
                .sudo()
                .search(
                    [
                        ("cement_customer_id", "=", customer.id),
                        ("state", "in", ("sale", "done")),
                    ],
                    order="date_order desc, id desc",
                    limit=1,
                )
            )

        salesperson = (
            sale_order.user_id
            or customer.sales_person
            or payment.create_uid
            or self.env.user
        )
        journal_type = payment.journal_id.type if payment.journal_id else False
        return {
            "customer_id": customer.id,
            "invoice_id": invoice.id if invoice else False,
            "sale_order_id": sale_order.id if sale_order else False,
            "payment_date": payment.date or fields.Date.context_today(payment),
            "amount": payment.amount,
            "currency_id": payment.currency_id.id,
            "payment_method": self._journal_type_to_method.get(journal_type, "other"),
            "reference": payment.payment_reference or payment.name,
            "salesperson_id": salesperson.id,
            "notes": _("由 Odoo 原生收款 %s 自动同步", payment.name or ""),
        }

    @api.model
    def _create_cement_payments_from_native(self, payments):
        """把原生收款批量同步成已确认回款，返回 (创建数, 跳过数, 失败数)。"""
        CementPayment = self.sudo()
        created = skipped = failed = 0
        for payment in payments:
            if payment.cement_payment_id or payment.amount <= 0:
                continue
            if CementPayment.search(
                [("native_payment_id", "=", payment.id)], limit=1
            ):
                continue
            try:
                with CementPayment.env.cr.savepoint():
                    vals = CementPayment._prepare_cement_payment_vals_from_native(
                        payment
                    )
                    if not vals:
                        skipped += 1
                        continue
                    record = CementPayment.with_company(payment.company_id).create(
                        vals
                    )
                    record.write(
                        {"status": "confirmed", "native_payment_id": payment.id}
                    )
                    # 回写关联，方便后续核销/重算时快速去重。
                    payment.sudo().cement_payment_id = record.id
                    created += 1
            except Exception:
                # 单笔同步失败只回滚 savepoint，不阻塞原生收款过账，
                # 稍后可用「同步原生收款」补录。
                _logger.exception(
                    "同步原生收款 %s 到回款模块失败", payment.display_name
                )
                failed += 1
        return created, skipped, failed

    @api.model
    def action_sync_native_payments(self):
        """手动补录：把已过账但尚未同步的原生收款补成回款记录。"""
        payments = self.env["account.payment"].sudo().search(
            [
                ("payment_type", "=", "inbound"),
                ("partner_type", "=", "customer"),
                ("state", "in", list(self._native_sync_states)),
                ("cement_payment_id", "=", False),
                ("partner_id", "!=", False),
            ]
        )
        if not payments:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("同步原生收款"),
                    "message": _("没有需要同步的原生收款。"),
                    "type": "info",
                    "sticky": False,
                },
            }
        created, skipped, failed = self._create_cement_payments_from_native(payments)
        parts = [_("已同步 %s 笔回款记录。") % created]
        if skipped:
            parts.append(_("%s 笔未找到对应的水泥客户，已跳过。") % skipped)
        if failed:
            parts.append(_("%s 笔同步失败，详情请查看服务器日志。") % failed)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("同步原生收款"),
                "message": " ".join(parts),
                "type": "info" if not failed else "warning",
                "sticky": bool(failed),
            },
        }


class AccountPayment(models.Model):
    _inherit = "account.payment"

    cement_payment_id = fields.Many2one(
        "cement.payment",
        string="水泥业务回款",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
    )

    _sql_constraints = [
        (
            "cement_payment_unique_source",
            "unique(cement_payment_id)",
            "A cement payment can only create one Odoo payment.",
        ),
    ]

    def action_post(self):
        # 原生收款过账后立即反向同步一条回款记录；
        # 由回款模块确认产生的付款（cement_payment_id 已设置）会被自动跳过。
        res = super().action_post()
        if not self.env.context.get("skip_cement_payment_sync"):
            try:
                self._sync_posted_to_cement()
            except Exception:
                # 只记录日志，绝不回滚：收款过账本身不能被同步失败拖累。
                _logger.exception(
                    "原生收款过账后同步回款记录失败，稍后可用「同步原生收款」补录。"
                )
        return res

    def _syncable_native_candidates(self):
        return self.filtered(
            lambda payment: payment.payment_type == "inbound"
            and payment.partner_type == "customer"
            and payment.state in NATIVE_SYNC_STATES
            and payment.partner_id
            and not payment.cement_payment_id
        )

    def _sync_posted_to_cement(self):
        candidates = self._syncable_native_candidates()
        if not candidates:
            return
        self.env["cement.payment"]._create_cement_payments_from_native(candidates)


class AccountPartialReconcile(models.Model):
    """在「登记付款」流程里，先过账、后核销发票。
    挂在核销创建上，能保证同步时 reconciled_invoice_ids 已经有值，
    回款记录才能正确关联发票和销售订单。"""

    _inherit = "account.partial.reconcile"

    @api.model_create_multi
    def create(self, vals_list):
        reconciles = super().create(vals_list)
        try:
            reconciles._sync_cement_payments_from_reconcile()
        except Exception:
            # 只记录日志，绝不回滚：核销本身不能被同步失败拖累。
            _logger.exception("核销后同步回款记录失败，稍后可用「同步原生收款」补录。")
        return reconciles

    def _sync_cement_payments_from_reconcile(self):
        if self.env.context.get("skip_cement_payment_sync"):
            return
        Payment = self.env["account.payment"]
        payments = Payment
        for partial in self:
            for line in partial.debit_move_id | partial.credit_move_id:
                move = line.move_id
                if not move:
                    continue
                payments |= Payment.search([("move_id", "=", move.id)], limit=1)
        candidates = payments._syncable_native_candidates()
        if candidates:
            self.env["cement.payment"]._create_cement_payments_from_native(candidates)
