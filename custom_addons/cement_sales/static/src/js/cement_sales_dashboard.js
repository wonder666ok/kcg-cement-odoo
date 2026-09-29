/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class CementSalesDashboard extends Component {
    static template = "cement_sales.CementSalesDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            period: "month",
            data: null,
            loading: true,
            error: null,
        });
        onWillStart(() => this.loadDashboard());
    }

    async loadDashboard() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call(
                "sale.order",
                "get_cement_sales_dashboard_data",
                [this.state.period]
            );
        } catch (error) {
            this.state.error = error.message || "\u4eea\u8868\u76d8\u6570\u636e\u52a0\u8f7d\u5931\u8d25";
        } finally {
            this.state.loading = false;
        }
    }

    onPeriodChange(event) {
        this.state.period = event.target.value;
        return this.loadDashboard();
    }

    get kpiRows() {
        if (!this.state.data) {
            return [];
        }
        const { kpis, has_accounting_access: canSeeAccounts } = this.state.data;
        const accountValue = (value) => canSeeAccounts ? value : null;
        return [
            [
                { key: "customers", label: "\u5ba2\u6237\u603b\u6570", value: kpis.customer_count },
                { key: "active_customers", label: "\u6d3b\u8dc3\u5ba2\u6237", value: kpis.active_customer_count },
                { key: "followup_today", label: "\u4eca\u65e5\u5f85\u8ddf\u8fdb", value: kpis.today_followup_count },
                { key: "followup_overdue", label: "\u5df2\u903e\u671f\u8ddf\u8fdb", value: kpis.overdue_followup_count },
            ],
            [
                { key: "quotations", label: this.state.data.period_label + "\u62a5\u4ef7\u6570\u91cf", value: kpis.quotation_count },
                { key: "orders", label: this.state.data.period_label + "\u786e\u8ba4\u8ba2\u5355", value: kpis.confirmed_order_count },
                { key: "sales_bags", label: this.state.data.period_label + "\u9500\u552e\u888b\u6570", value: kpis.sales_bags },
                { key: "sales", label: this.state.data.period_label + "\u9500\u552e\u91d1\u989d", value: kpis.sales_amount, money: true },
            ],
            [
                { key: "delivery", label: "\u5f85\u4ea4\u4ed8\u5355\u636e", value: kpis.pending_delivery_count },
                { key: "delivered_bags", label: this.state.data.period_label + "\u5df2\u4ea4\u4ed8\u888b\u6570", value: kpis.delivered_bags },
                { key: "invoices", label: this.state.data.period_label + "\u53d1\u7968\u91d1\u989d", value: accountValue(kpis.invoice_amount), money: true },
                { key: "payments", label: this.state.data.period_label + "\u56de\u6b3e\u91d1\u989d", value: kpis.payment_amount, money: true },
                { key: "reconciled_payments", label: "\u4f1a\u8ba1\u5df2\u6838\u9500\u91d1\u989d", value: accountValue(kpis.reconciled_payment_amount), money: true },
            ],
            [
                { key: "receivable", label: "\u5f53\u524d\u5e94\u6536", value: accountValue(kpis.receivable_amount), money: true },
                { key: "overdue_receivable", label: "\u903e\u671f\u5e94\u6536", value: accountValue(kpis.overdue_receivable_amount), money: true },
                { key: "month_sales", label: "\u672c\u6708\u9500\u552e\u989d", value: kpis.month_sales_amount, money: true },
                { key: "month_bags", label: "\u672c\u6708\u9500\u552e\u888b\u6570", value: kpis.month_sales_bags },
            ],
        ];
    }

    formatNumber(value) {
        return Number(value || 0).toLocaleString(undefined, {
            maximumFractionDigits: 2,
        });
    }

    formatCard(card) {
        if (card.value === null) {
            return "\u6682\u65e0\u6743\u9650";
        }
        if (card.money) {
            return this.formatMoney(card.value);
        }
        return card.text ? card.value : this.formatNumber(card.value);
    }

    formatMoney(value) {
        const currency = this.state.data.currency;
        const amount = Number(value || 0).toLocaleString(undefined, {
            minimumFractionDigits: currency.decimal_places,
            maximumFractionDigits: currency.decimal_places,
        });
        return currency.symbol + " " + amount;
    }

    formatDate(value) {
        return value || "\u2014";
    }

    formatInvoiceMoney(row, field) {
        const decimals = row.currency_decimals ?? 2;
        const amount = Number(row[field] || 0).toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
        return row.currency + " " + amount;
    }

    async openAction(model, domain, name) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    onKpiClick(key) {
        if (
            ["invoices", "reconciled_payments", "receivable", "overdue_receivable"].includes(key)
            && !this.state.data.has_accounting_access
        ) {
            return Promise.resolve();
        }
        const companyDomain = [["company_id", "=", this.state.data.company_id]];
        const orderDates = [
            ["date_order", ">=", this.state.data.date_from_datetime],
            ["date_order", "<", this.state.data.date_to_datetime],
        ];
        const linkedInvoices = [["id", "in", this.state.data.linked_invoice_ids || []]];
        if (key === "customers" || key === "active_customers") {
            return this.openAction("cement.customer", key === "active_customers" ? [["active", "=", true], ["customer_status", "=", "active"]] : [], "\u5ba2\u6237");
        }
        if (key === "followup_today") {
            return this.openAction("cement.followup", [["state", "=", "pending"], ["next_followup_date", "=", this.state.data.today]], "\u4eca\u65e5\u5f85\u8ddf\u8fdb");
        }
        if (key === "followup_overdue") {
            return this.openAction("cement.followup", [["state", "=", "pending"], ["next_followup_date", "<", this.state.data.today]], "\u5df2\u903e\u671f\u8ddf\u8fdb");
        }
        if (["quotations", "orders", "sales", "sales_bags", "month_sales", "month_bags"].includes(key)) {
            const dateDomain = ["month_sales", "month_bags"].includes(key)
                ? [
                    ["date_order", ">=", this.state.data.month_start_datetime],
                    ["date_order", "<", this.state.data.next_month_start_datetime],
                ]
                : orderDates;
            const domain = [...companyDomain, ...dateDomain];
            if (key === "quotations") domain.push(["state", "in", ["draft", "sent"]]);
            else domain.push(["state", "in", ["sale", "done"]]);
            return this.openAction("sale.order", domain, "\u9500\u552e\u8ba2\u5355");
        }
        if (key === "delivery" || key === "delivered_bags") {
            const domain = key === "delivery"
                ? [["state", "in", ["draft", "scheduled", "in_transit"]], ["sale_order_id.company_id", "=", this.state.data.company_id]]
                : [["state", "=", "delivered"], ["sale_order_id.company_id", "=", this.state.data.company_id], ["delivery_date", ">=", this.state.data.date_from], ["delivery_date", "<", this.state.data.date_to_exclusive]];
            return this.openAction("cement.delivery", domain, "\u4ea4\u4ed8\u7ba1\u7406");
        }
        if (key === "invoices") {
            return this.openAction("account.move", linkedInvoices, "\u5ba2\u6237\u53d1\u7968");
        }
        if (key === "reconciled_payments") {
            return this.openAction("account.move", linkedInvoices, "\u5df2\u6838\u9500\u5ba2\u6237\u53d1\u7968");
        }
        if (key === "receivable" || key === "overdue_receivable") {
            const domain = [...linkedInvoices, ["amount_residual_signed", ">", 0]];
            if (key === "overdue_receivable") domain.push(["invoice_date_due", "<", this.state.data.today]);
            return this.openAction("account.move", domain, "\u5e94\u6536\u53d1\u7968");
        }
        if (key === "payments") {
            return this.openAction("cement.payment", [["id", "in", this.state.data.linked_payment_ids || []]], "\u56de\u6b3e\u8bb0\u5f55");
        }
        return Promise.resolve();
    }

    openCustomer(id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "cement.customer", views: [[false, "form"]], res_id: id, target: "current" });
    }

    openFollowup(id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "cement.followup", views: [[false, "form"]], res_id: id, target: "current" });
    }

    openDelivery(id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "cement.delivery", views: [[false, "form"]], res_id: id, target: "current" });
    }

    openInvoice(id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "account.move", views: [[false, "form"]], res_id: id, target: "current" });
    }
}

registry.category("actions").add("cement_sales_dashboard", CementSalesDashboard);
