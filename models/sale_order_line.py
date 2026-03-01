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
    x_moyee_removed_on = fields.Datetime(string="Removed On", copy=False)
    x_moyee_removed_by = fields.Many2one("res.users", string="Removed By", copy=False)
    x_moyee_remove_reason = fields.Text(string="Remove Reason", copy=False)

    def _moyee_check_manager_rights(self):
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

    def action_moyee_soft_remove_portal(self, portal_user_id, reason=None):
        """Portal-safe soft remove.

        Called by portal controllers in sudo() mode.
        Performs explicit ownership checks on the subscription order.
        """

        # ✅ BLOCK DELIVERY PRODUCTS (server-side security)
        for line in self:
            pname = (line.product_id.display_name or line.name or "").lower()
            if "delivery" in pname:
                raise UserError(_("You can not delete delivery product."))

        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        for line in self:
            if not line.order_id:
                raise UserError(_("Invalid subscription line."))
            line.order_id._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        now = fields.Datetime.now()
        for line in self:
            if line.display_type:
                continue
            if line.x_moyee_is_removed and line.product_uom_qty == 0:
                continue

            vals = {
                "product_uom_qty": 0.0,
                "x_moyee_is_removed": True,
                "x_moyee_removed_on": now,
                "x_moyee_removed_by": portal_user.id,
            }
            if reason:
                vals["x_moyee_remove_reason"] = reason

            line.sudo().write(vals)

            product_label = line.product_id.display_name if line.product_id else (line.name or _("(no product)"))
            body = _(
                "Moyee soft removal applied via portal.\n"
                "- Item: %s\n"
                "- By: %s\n"
                "- When: %s\n"
                "- Reason: %s"
            ) % (
                product_label,
                portal_user.display_name,
                fields.Datetime.to_string(now),
                reason or _("(no reason provided)"),
            )

            line.order_id.with_user(1).message_post(
                body=body,
                subtype_xmlid="mail.mt_note",
                author_id=portal_user.partner_id.id,
            )

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