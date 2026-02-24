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
        """
        Allow any INTERNAL user (dashboard access).
        - Internal users are in base.group_user.
        - Portal/public users are NOT in this group.
        """
        if self.env.is_superuser():
            return
        if self.env.user.has_group("base.group_user"):
            return
        raise AccessError(_("You do not have access to manage subscription removals."))

    def action_moyee_soft_remove(self, reason=None):
        """
        Soft remove a subscription product line:
        - product_uom_qty = 0
        - x_moyee_is_removed = True
        - track who/when/why
        - post a chatter note on the sale order
        """
        self._moyee_check_manager_rights()

        for line in self:
            if line.display_type:
                continue

            if not getattr(line.order_id, "is_subscription_order", False):
                raise UserError(_("This action is only available on subscription sale orders."))

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

        return True

    def unlink(self):
        """
        If user clicks the default trash icon on confirmed subscription lines,
        convert unlink() into soft-remove (qty=0 + removed flag) instead of showing "Oh snap!".
        """
        to_soft_remove = self.filtered(lambda l: (
            not l.display_type
            and l.order_id
            and getattr(l.order_id, "is_subscription_order", False)
            and l.order_id.state in ("sale", "done")
        ))

        if to_soft_remove:
            self._moyee_check_manager_rights()

            now = fields.Datetime.now()
            for line in to_soft_remove:
                if line.x_moyee_is_removed and line.product_uom_qty == 0:
                    continue

                line.write({
                    "product_uom_qty": 0.0,
                    "x_moyee_is_removed": True,
                    "x_moyee_removed_on": now,
                    "x_moyee_removed_by": self.env.user.id,
                    "x_moyee_remove_reason": line.x_moyee_remove_reason
                        or _("Removed via line delete (auto converted to soft remove)."),
                })

                product_label = line.product_id.display_name if line.product_id else (line.name or _("(no product)"))
                line.order_id.message_post(
                    body=_("Moyee: '%s' was removed (delete action converted to soft remove).") % product_label,
                    subtype_xmlid="mail.mt_note",
                )

        remaining = self - to_soft_remove
        if remaining:
            return super(SaleOrderLine, remaining).unlink()

        return True