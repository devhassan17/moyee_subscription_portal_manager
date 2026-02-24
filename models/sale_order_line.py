# File: moyee_subscription_portal_manager/models/sale_order_line.py
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_moyee_is_removed = fields.Boolean(
        string="Removed from Subscription",
        default=False,
        index=True,
        copy=False,
        help="If enabled, the line is considered soft-removed: it is hidden in the backend "
             "subscription UI, excluded from future invoices, and (optionally) filtered from PDFs.",
    )
    x_moyee_removed_on = fields.Datetime(
        string="Removed on",
        copy=False,
        readonly=True,
    )
    x_moyee_removed_by = fields.Many2one(
        comodel_name="res.users",
        string="Removed by",
        copy=False,
        readonly=True,
    )
    x_moyee_remove_reason = fields.Text(
        string="Remove reason",
        copy=False,
        readonly=True,
    )

    def _moyee_check_manager_rights(self):
        """Manager-only guard. Do not rely purely on view-level groups."""
        if self.env.is_superuser():
            return
        if not self.env.user.has_group("moyee_subscription_portal_manager.group_moyee_subscription_manager"):
            raise AccessError(_("You do not have the required rights to manage subscription removals."))

    def action_moyee_soft_remove(self, reason=None):
        """
        Soft remove a subscription product line:
        - product_uom_qty = 0
        - x_moyee_is_removed = True
        - track who/when/why
        - post a chatter note on the sale order

        This method is intentionally idempotent.
        """
        self._moyee_check_manager_rights()

        for line in self:
            # Never soft-remove section/note lines (keep UI structure clean).
            if line.display_type:
                continue

            # Restrict to subscription orders (manager-only build).
            if not getattr(line.order_id, "is_subscription_order", False):
                raise UserError(_("This action is only available on subscription sale orders."))

            # Already removed => idempotent
            if line.x_moyee_is_removed and line.product_uom_qty == 0:
                continue

            vals = {
                "product_uom_qty": 0.0,
                "x_moyee_is_removed": True,
                "x_moyee_removed_on": fields.Datetime.now(),
                "x_moyee_removed_by": self.env.user.id,
            }
            if reason:
                vals["x_moyee_remove_reason"] = reason

            line.write(vals)

            # Chatter note on the order (audit trail).
            product_label = line.product_id.display_name if line.product_id else (line.name or _("(no product)"))
            body = _(
                "Moyee soft removal applied.\n"
                "- Item: %s\n"
                "- Action: quantity set to 0, line marked as removed\n"
                "- By: %s\n"
                "- When: %s\n"
                "- Reason: %s"
            ) % (
                product_label,
                self.env.user.display_name,
                fields.Datetime.to_string(vals["x_moyee_removed_on"]),
                reason or _("(no reason provided)"),
            )
            line.order_id.message_post(body=body, subtype_xmlid="mail.mt_note")
