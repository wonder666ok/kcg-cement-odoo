from odoo import api, fields, models


class CementFollowup(models.Model):
    _name = "cement.followup"
    _description = "Cement Sales Follow-up"
    _order = "next_followup_date asc, date desc, id desc"

    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    customer_id = fields.Many2one(
        "cement.customer",
        string="客户",
        required=True,
        ondelete="restrict",
    )
    date = fields.Date(
        string="跟进日期", required=True, default=fields.Date.context_today
    )
    subject = fields.Char(string="主题", required=True)
    followup_type = fields.Selection(
        [
            ("phone", "电话"),
            ("whatsapp", "WhatsApp"),
            ("visit", "拜访"),
            ("email", "邮件"),
            ("other", "其他"),
        ],
        string="跟进类型",
        default="phone",
    )
    next_followup_date = fields.Date(string="下次跟进日期", index=True)
    salesperson_id = fields.Many2one("res.users", string="销售员")
    state = fields.Selection(
        [
            ("pending", "待跟进"),
            ("done", "已完成"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        required=True,
        default="pending",
    )
    result = fields.Selection(
        [
            ("waiting", "等待客户回复"),
            ("quoted", "已报价"),
            ("sample", "样品/测试"),
            ("negotiating", "洽谈中"),
            ("won", "已成交"),
            ("lost", "未成交"),
        ],
        string="跟进结果",
    )
    notes = fields.Text(string="跟进备注")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            customer_id = vals.get("customer_id") or self.env.context.get(
                "default_customer_id"
            )
            customer = self.env["cement.customer"].browse(customer_id).exists()
            if not vals.get("salesperson_id"):
                vals["salesperson_id"] = (
                    customer.sales_person.id if customer and customer.sales_person
                    else self.env.user.id
                )
            if not vals.get("company_id"):
                # 跟进记录跟随客户所属公司，避免多公司数据串味。
                vals["company_id"] = (
                    customer.company_id.id if customer and customer.company_id
                    else self.env.company.id
                )
        records = super().create(vals_list)
        records._sync_customer_next_followup_date(preserve_later=True)
        return records

    def write(self, vals):
        customers = self.mapped("customer_id")
        result = super().write(vals)
        customers |= self.mapped("customer_id")
        preserve_later = not (
            vals.get("state") == "cancelled"
            or ("next_followup_date" in vals and not vals["next_followup_date"])
        )
        self._sync_customer_next_followup_date(
            customers=customers, preserve_later=preserve_later
        )
        return result

    def unlink(self):
        customers = self.mapped("customer_id")
        result = super().unlink()
        self._sync_customer_next_followup_date(
            customers=customers, preserve_later=False
        )
        return result

    def _sync_customer_next_followup_date(self, customers=None, preserve_later=False):
        customers = customers or self.mapped("customer_id")
        if not customers:
            return
        Followup = self.env["cement.followup"]
        for customer in customers:
            followups = Followup.search(
                [
                    ("customer_id", "=", customer.id),
                    ("state", "!=", "cancelled"),
                    ("next_followup_date", "!=", False),
                ],
                order="write_date desc, id desc",
            )
            next_date = followups[:1].next_followup_date or False
            completed_records = (
                self.filtered(
                    lambda followup: followup.customer_id == customer
                    and followup.state == "done"
                )
                if preserve_later
                else self.browse()
            )
            if not next_date and preserve_later:
                continue
            if (
                preserve_later
                and next_date
                and customer.next_followup_date
                and customer.next_followup_date > next_date
                and customer.next_followup_date >= fields.Date.context_today(customer)
                and completed_records
            ):
                continue
            if customer.next_followup_date != next_date:
                customer.next_followup_date = next_date
