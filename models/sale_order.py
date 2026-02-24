# File: moyee_subscription_portal_manager/models/sale_order.py
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_subscription_order = fields.Boolean(
        string="Is Subscription Order",
        compute="_compute_is_subscription_order",
        store=False,
    )

    def _compute_is_subscription_order(self):
        """
        Odoo Enterprise Subscriptions adds subscription-specific fields on sale.order.
        Field technical names may vary across versions/editions, so we check the model
        field registry defensively.

        Heuristics:
        - subscription_status (common in subscription sale flows) OR
        - recurring_plan_id OR
        - is_subscription
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

        We conservatively filter out:
        - x_moyee_is_removed = True
        - product_uom_qty <= 0

        We keep display_type lines (sections/notes) intact if they are present
        in the super result.
        """
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(
            lambda l: l.display_type or (not l.x_moyee_is_removed and l.product_uom_qty > 0)
        )
