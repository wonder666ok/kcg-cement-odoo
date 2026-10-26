import re
from urllib.parse import quote

from odoo import _, models
from odoo.exceptions import AccessError, UserError


class CementWhatsappMixin:
    """WhatsApp 网页版发送辅助（纯 Python 混入类，不注册为 Odoo 模型）。

    通过 wa.me 的 click-to-chat 链接调起 WhatsApp 网页版（web.whatsapp.com）
    或手机客户端，自动带出收件人与预填消息，用户确认后发送。
    不依赖任何外部 API，无额外费用与封号风险。
    """

    def _whatsapp_normalize(self, phone):
        """把各种写法的电话号码规范成 wa.me 需要的国际格式（纯数字，无 + 号）。

        - 去掉所有非数字字符；
        - 「00」国际前缀去掉；
        - 「0」开头按加纳本地号码换成国家码 233；
        - 9 位无前缀号码视为加纳号码补 233。
        """
        digits = re.sub(r"\D", "", phone or "")
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("0"):
            digits = "233" + digits[1:]
        elif len(digits) == 9:
            digits = "233" + digits
        if len(digits) < 8:
            raise UserError(
                _("电话号码无效，无法通过 WhatsApp 发送：%s") % (phone or _("（空）"))
            )
        return digits

    def _whatsapp_action(self, phone, message):
        """返回打开 WhatsApp 网页版并预填消息的动作。"""
        digits = self._whatsapp_normalize(phone)
        return {
            "type": "ir.actions.act_url",
            "url": "https://wa.me/%s?text=%s" % (digits, quote(message, safe="")),
            "target": "new",
        }


class CementCustomerWhatsapp(CementWhatsappMixin, models.Model):
    _inherit = "cement.customer"

    def _whatsapp_customer_phone(self):
        self.ensure_one()
        # 优先用专门的 WhatsApp 号码字段
        return self.whatsapp or self.phone

    def action_send_whatsapp(self):
        """打开 WhatsApp 网页版，给该客户发送通用消息（可编辑后发送）。"""
        self.ensure_one()
        phone = self._whatsapp_customer_phone()
        if not phone:
            raise UserError(_("客户「%s」没有填写 WhatsApp/电话号码。") % self.name)
        display_name = self.company_name or self.name
        lines = [
            "Hello %s," % display_name,
            "",
            "This is KCG Cement Sales. Please feel free to contact us for",
            "cement orders, deliveries or any questions.",
            "",
            "Thank you!",
            "- KCG Cement Sales",
        ]
        return self._whatsapp_action(phone, "\n".join(lines))

    def action_send_whatsapp_reminder(self):
        """打开 WhatsApp 网页版，给该客户发送对账/催款提醒。"""
        self.ensure_one()
        phone = self._whatsapp_customer_phone()
        if not phone:
            raise UserError(_("客户「%s」没有填写 WhatsApp/电话号码。") % self.name)
        display_name = self.company_name or self.name
        try:
            due = self.total_due_amount or 0.0
            currency = self.financial_currency_id.name or ""
        except AccessError:
            due = 0.0
            currency = ""
        lines = [
            "Dear %s," % display_name,
            "",
            "This is a payment reminder from KCG Cement Sales.",
        ]
        if due:
            lines.append(
                "Your current outstanding balance is %s %s."
                % (currency, "{:,.2f}".format(due))
            )
        else:
            lines.append("Our records show your account is fully settled. Thank you!")
        lines += [
            "",
            "Kindly arrange the payment at your convenience.",
            "Please contact us if you have any questions.",
            "",
            "Thank you!",
            "- KCG Cement Sales",
        ]
        return self._whatsapp_action(phone, "\n".join(lines))


class CementDeliveryWhatsapp(CementWhatsappMixin, models.Model):
    _inherit = "cement.delivery"

    def _whatsapp_customer_phone(self):
        self.ensure_one()
        customer = self.customer_id
        return (customer.whatsapp or customer.phone) if customer else False

    def _whatsapp_driver_phone(self):
        self.ensure_one()
        return self.driver_phone or (
            self.transport_driver_id.phone if self.transport_driver_id else False
        )

    def _delivery_common_lines(self):
        self.ensure_one()
        order = self.sale_order_id
        qty = self.quantity or 0
        tons = self.weight_tons
        weight = " (%s tons)" % ("{:.1f}".format(tons) if tons else "0")
        lines = [
            "Order No.: %s" % (order.name or "-"),
            "Product: Cement %s" % (self.cement_grade or "-"),
            "Quantity: %s bags%s" % ("{:.0f}".format(qty), weight),
            "Delivery date: %s"
            % (self.delivery_date.strftime("%Y-%m-%d") if self.delivery_date else "-"),
            "Address: %s %s" % (self.delivery_region or "", self.delivery_address or ""),
        ]
        return lines

    def action_send_whatsapp_customer(self):
        """打开 WhatsApp 网页版，给客户发送发货/运输通知。"""
        self.ensure_one()
        phone = self._whatsapp_customer_phone()
        if not phone:
            raise UserError(
                _("客户「%s」没有填写 WhatsApp/电话号码。")
                % (self.customer_id.name if self.customer_id else "-")
            )
        customer_name = (
            self.customer_id.company_name or self.customer_id.name
            if self.customer_id
            else ""
        )
        lines = ["Hello %s," % customer_name, ""]
        if self.state == "delivered":
            lines.append("Your cement order has been delivered.")
        else:
            lines.append("Your cement delivery has been scheduled.")
        lines += self._delivery_common_lines()
        if self.vehicle_number or self.driver_name:
            lines.append(
                "Vehicle: %s    Driver: %s %s"
                % (
                    self.vehicle_number or "-",
                    self.driver_name or "-",
                    self.driver_phone or "",
                )
            )
        lines += [
            "",
            "Please arrange to receive the goods. Thank you!",
            "- KCG Cement Sales",
        ]
        return self._whatsapp_action(phone, "\n".join(lines))

    def action_send_whatsapp_driver(self):
        """打开 WhatsApp 网页版，给司机发送运输任务通知。"""
        self.ensure_one()
        if self.transport_type == "customer_pickup":
            raise UserError(_("客户自提订单没有承运司机，无需发送。"))
        phone = self._whatsapp_driver_phone()
        if not phone:
            raise UserError(
                _("交付单没有司机电话，请先填写司机或选择司机档案。")
            )
        driver_name = self.driver_name or (
            self.transport_driver_id.name if self.transport_driver_id else ""
        )
        lines = [
            "Hello %s," % (driver_name or "Driver"),
            "",
            "You have a cement delivery task.",
        ]
        lines += self._delivery_common_lines()
        lines.append(
            "Vehicle: %s" % (self.vehicle_number or "-")
        )
        if self.delivery_contact or self.delivery_phone:
            lines.append(
                "Consignee: %s %s" % (self.delivery_contact or "", self.delivery_phone or "")
            )
        lines += [
            "",
            "Please load on time and deliver safely. Thank you!",
            "- KCG Cement Sales",
        ]
        return self._whatsapp_action(phone, "\n".join(lines))


class SaleOrderWhatsapp(CementWhatsappMixin, models.Model):
    _inherit = "sale.order"

    def action_send_whatsapp(self):
        """打开 WhatsApp 网页版，给水泥客户发送订单摘要。"""
        self.ensure_one()
        customer = self.cement_customer_id
        phone = (customer.whatsapp or customer.phone) if customer else False
        if not phone:
            raise UserError(_("该订单没有关联水泥客户，或客户没有电话号码。"))
        qty = sum(
            self.order_line.filtered(lambda line: not line.display_type).mapped(
                "product_uom_qty"
            )
        )
        grades = ", ".join(
            grade
            for grade in self.order_line.mapped("product_id.product_tmpl_id.cement_grade")
            if grade
        ) or "-"
        lines = [
            "Dear %s," % (customer.company_name or customer.name),
            "",
            "Thank you for your cement order. Here is the summary:",
            "Order No.: %s" % self.name,
            "Product: %s" % grades,
            "Quantity: %s" % ("{:.0f}".format(qty)),
            "Amount: %s %s" % (self.currency_id.name or "", "{:,.2f}".format(self.amount_total)),
            "Delivery: %s %s" % (self.delivery_region or "", self.delivery_address or ""),
            "",
            "We will keep you updated on the delivery. Thank you!",
            "- KCG Cement Sales",
        ]
        return self._whatsapp_action(phone, "\n".join(lines))


class ResPartnerWhatsapp(CementWhatsappMixin, models.Model):
    _inherit = "res.partner"

    def _whatsapp_partner_phone(self):
        self.ensure_one()
        # 优先手机号，其次座机；公司联系人取上级公司电话
        return self.mobile or self.phone or (self.parent_id.phone if self.parent_id else False)

    def action_send_whatsapp(self):
        """打开 WhatsApp 网页版，给该联系人发送消息。"""
        self.ensure_one()
        phone = self._whatsapp_partner_phone()
        if not phone:
            raise UserError(
                _("联系人「%s」没有填写电话或手机号。") % (self.name or "")
            )
        company_name = self.env.company.name or "KCG Cement Sales"
        lines = [
            "Hello %s," % (self.name or ""),
            "",
            "This is %s. Please feel free to contact us anytime." % company_name,
            "",
            "Thank you!",
            "- %s" % company_name,
        ]
        return self._whatsapp_action(phone, "\n".join(lines))
