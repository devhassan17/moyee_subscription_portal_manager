# File: moyee_subscription_portal_manager/models/sale_order.py
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_subscription_order = fields.Boolean(
        string="Is Subscription Order",
        compute="_compute_is_subscription_order",
        store=False,
    )

    # ✅ NEW: dedicated one2many for removed lines (so we don't reuse order_line in the tab)
    moyee_removed_line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="order_id",
        string="Removed Lines",
        domain=[("x_moyee_is_removed", "=", True)],
        readonly=True,
    )

    def _compute_is_subscription_order(self):
        """
        Enterprise subscriptions add fields on sale.order; field names can vary,
        so we detect defensively.
        """
        for order in self:
            is_sub = False
            if "subscription_status" in order._fields and order.subscription_status:
                is_sub = True
            elif "recurring_plan_id" in order._fields and order.recurring_plan_id:
                is_sub = True
            elif "is_subscription" in order._fields and order.is_subscription:
                is_sub = True
            order.is_subscription_order = is_sub

    def _get_invoiceable_lines(self, final=False):
        """
        Most important hook:
        Ensure removed/zero lines do NOT get invoiced (including recurring invoices).
        """
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda l: l.display_type or (not l.x_moyee_is_removed and l.product_uom_qty > 0))