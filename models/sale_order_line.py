# File: moyee_subscription_portal_manager/models/sale_order_line.py
import re
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'name' in vals and vals['name']:
                vals['name'] = self._clean_subscription_name(vals['name'])
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals and vals['name']:
            vals['name'] = self._clean_subscription_name(vals['name'])
        return super().write(vals)

    def _prepare_invoice_line(self, **optional_values):
        if self.x_moyee_is_removed or float(self.product_uom_qty or 0.0) <= 0.0:
            return {}
        res = super()._prepare_invoice_line(**optional_values)
        if res and self._moyee_is_subscription_line():
            res["quantity"] = float(self.product_uom_qty or 0.0)
        return res

    def _clean_subscription_name(self, name):
        if not name:
            return name
        # Case-insensitive replacement of (subscription) or [subscription] with optional surrounding spaces
        name = re.sub(r'\s*\(\s*subscription\s*\)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\[\s*subscription\s*\]', '', name, flags=re.IGNORECASE)
        return name.strip()

    x_moyee_is_removed = fields.Boolean(
        string="Removed from Subscription",
        default=False,
        index=True,
        copy=False,
        help=(
            "If enabled, the line is considered soft-removed: it is hidden in the backend "
            "subscription UI, excluded from future invoices, and (optionally) filtered from PDFs."
        ),
    )
    x_moyee_removed_on = fields.Datetime(string="Removed On", copy=False)
    x_moyee_removed_by = fields.Many2one("res.users", string="Removed By", copy=False)
    x_moyee_remove_reason = fields.Text(string="Remove Reason", copy=False)

    # -----------------------
    # Internal helpers
    # -----------------------
    def _moyee_get_portal_weight_display(self):
        self.ensure_one()
        weight_val = self._moyee_get_portal_weight_value()
        lang = (self.env.context.get('lang') or getattr(self.env, 'lang', '') or '').lower()
        path = ''
        try:
            from odoo.http import request
            if request and hasattr(request, 'httprequest'):
                path = (request.httprequest.path or '').lower()
        except Exception:
            pass

        is_de = '/de' in path or path.startswith('/de') or lang.startswith('de')
        is_nl = '/nl' in path or path.startswith('/nl') or lang.startswith('nl')

        if weight_val == "1kg":
            return "1 kg"
        elif weight_val == "250g":
            if is_de:
                return "250 Gramm"
            elif is_nl:
                return "250 gram"
            return "250g"
        elif weight_val == "25caps":
            if is_de:
                return "25 Kapseln"
            return "25 Capsules"

        return "—"

    def _moyee_get_portal_weight_value(self):
        self.ensure_one()
        if self.order_id:
            _, weight = self.order_id.moyee_extract_product_metadata(self.product_id)
        else:
            _, weight = self.env["sale.order"].moyee_extract_product_metadata(self.product_id)

        if weight in ("1kg", "250g", "25caps"):
            return weight

        if self.product_id:
            w = float(getattr(self.product_id, 'weight', 0.0) or 0.0)
            if w == 1.0:
                return "1kg"
            elif w == 0.25:
                return "250g"

            lname = (self.product_id.display_name or self.product_id.name or self.name or "").lower()
            if "1kg" in lname.replace(" ", "") or "1 kg" in lname:
                return "1kg"
            if "250" in lname:
                return "250g"
            if "25" in lname or "capsule" in lname or "cups" in lname:
                return "25caps"
        return ""

    def _moyee_get_portal_grind_value(self):
        self.ensure_one()
        if self.order_id:
            grind, _ = self.order_id.moyee_extract_product_metadata(self.product_id)
        else:
            grind, _ = self.env["sale.order"].moyee_extract_product_metadata(self.product_id)
        return grind

    def _moyee_get_portal_grind_display(self):
        self.ensure_one()
        if self.product_id:
            # 1. Check if product variant has an explicit Grind attribute value
            avs = getattr(self.product_id, "product_template_attribute_value_ids", False)
            if not avs and hasattr(self.product_id, "product_variant_combination"):
                avs = self.product_id.product_variant_combination
            if avs:
                for av in avs:
                    attr_name = (av.attribute_id.name or "").lower()
                    val_name_raw = (getattr(av, "product_attribute_value_id", False) and av.product_attribute_value_id.name) or av.name or ""
                    if not val_name_raw:
                        continue
                    if ":" in val_name_raw:
                        val_name_raw = val_name_raw.split(":", 1)[-1].strip()
                    val_lower = val_name_raw.lower()

                    is_grind_attr = any(kw in attr_name for kw in ("grind", "maling", "mahlgrad", "mahlung", "brew", "zubereitung", "hoe zet je", "how do you brew", "type", "koffie", "zetwijze"))
                    if is_grind_attr or any(kw in val_lower for kw in ("whole", "boon", "bonen", "bohn", "ganz", "filter", "gemahlen", "snelfilter", "espresso", "capsule", "kapsel", "cup")):
                        return val_name_raw

        # 2. Standard key fallback
        val = self._moyee_get_portal_grind_value()
        if val == "whole":
            return "Whole Beans"
        elif val == "filter":
            return "Filter Grind"
        elif val == "espresso":
            return "Espresso Grind"
        elif val == "capsules":
            return "Capsules"
        elif val and val != "other":
            return val.capitalize()

        return "Whole Beans"

    def _moyee_check_manager_rights(self):
        """Backend-only: allow employees (and superuser)."""
        if self.env.is_superuser():
            return
        if self.env.user.has_group("base.group_user"):
            return
        raise AccessError(_("You do not have access to manage subscription removals."))

    def _moyee_is_subscription_line(self):
        """Robust check: treat line as subscription if its order says it is."""
        self.ensure_one()
        return self.order_id._moyee_is_subscription_order() if self.order_id else False

    def _moyee_is_delivery_line(self):
        """Check if line is a delivery, shipping, or service product line."""
        self.ensure_one()
        pname = (self.product_id.display_name or self.product_id.name or self.name or "").lower()
        return (
            getattr(self, 'is_delivery', False)
            or getattr(self.product_id, 'is_delivery', False)
            or getattr(self.product_id, 'type', '') == 'service'
            or getattr(self.product_id, 'detailed_type', '') == 'service'
            or any(kw in pname for kw in ('delivery', 'shipping', 'bezorg', 'levering', 'verzend', 'transport', 'postnl', 'dhl', 'ups'))
        )

    def _moyee_block_delivery_product(self):
        """Server-side protection: never allow 'delivery' product removal."""
        for line in self:
            if line._moyee_is_delivery_line():
                raise UserError(_("You can not delete delivery product."))

    def _moyee_soft_remove_vals(self, removed_by_user_id, reason=None, now=None):
        now = now or fields.Datetime.now()
        # Use max(qty_delivered, 0) to avoid Odoo constraint:
        # "The ordered quantity cannot be decreased below the amount already delivered."
        # The x_moyee_is_removed flag is what really controls exclusion from
        # future invoices, reports, and portal visibility.
        safe_qty = max(float(self.qty_delivered or 0.0), 0.0)
        vals = {
            "product_uom_qty": safe_qty,
            "price_unit": 0.0,
            "x_moyee_is_removed": True,
            "x_moyee_removed_on": now,
            "x_moyee_removed_by": removed_by_user_id,
        }
        if reason:
            vals["x_moyee_remove_reason"] = reason
        return vals

    # -----------------------
    # Backend action (employees)
    # -----------------------
    def action_moyee_soft_remove(self, reason=None):
        """
        Soft remove a subscription product line:
        - product_uom_qty = 0
        - x_moyee_is_removed = True
        - track who/when/why
        - post a chatter note on the sale order
        """
        self._moyee_check_manager_rights()
        self._moyee_block_delivery_product()

        now = fields.Datetime.now()
        for line in self:
            if line.display_type:
                continue

            if not line._moyee_is_subscription_line():
                raise UserError(_("This action is only available on subscription sale orders."))

            if line.x_moyee_is_removed and float(line.product_uom_qty or 0.0) == 0.0:
                continue

            vals = line._moyee_soft_remove_vals(self.env.user.id, reason=reason, now=now)
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
                fields.Datetime.to_string(now),
                reason or _("(no reason provided)"),
            )
            line.order_id.message_post(body=body, subtype_xmlid="mail.mt_note")
            line.order_id._moyee_auto_recompute_delivery()

        return True

    # -----------------------
    # Portal action (customers)
    # -----------------------
    def action_moyee_soft_remove_portal(self, portal_user_id, reason=None, access_token=None):
        """Portal-safe soft remove (called by portal controllers in sudo)."""
        self._moyee_block_delivery_product()

        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        # Ownership / access check (uses your sale.order helper)
        for line in self:
            if not line.order_id:
                raise UserError(_("Invalid subscription line."))
            line.order_id._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        now = fields.Datetime.now()
        for line in self:
            if line.display_type:
                continue
            if line.x_moyee_is_removed and float(line.product_uom_qty or 0.0) == 0.0:
                continue

            vals = line._moyee_soft_remove_vals(portal_user.id, reason=reason, now=now)
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
            line.order_id._moyee_auto_recompute_delivery()

        return True

    # -----------------------
    # Convert backend "trash" into soft remove for subscriptions
    # -----------------------
    def unlink(self):
        """
        If user clicks the default trash icon on confirmed subscription lines,
        convert unlink() into soft-remove instead of error.
        """
        # only subscription lines on confirmed orders
        to_soft_remove = self.filtered(
            lambda l: (
                not l.display_type
                and l.order_id
                and l._moyee_is_subscription_line()
                and l.order_id.state in ("sale", "done")
            )
        )

        if to_soft_remove:
            self._moyee_check_manager_rights()
            to_soft_remove._moyee_block_delivery_product()

            now = fields.Datetime.now()
            for line in to_soft_remove:
                # write as employee user
                line.write(
                    line._moyee_soft_remove_vals(
                        self.env.user.id,
                        reason=line.x_moyee_remove_reason
                        or _("Removed via line delete (auto converted to soft remove)."),
                        now=now,
                    )
                )

                product_label = line.product_id.display_name if line.product_id else (line.name or _("(no product)"))
                line.order_id.message_post(
                    body=_("Moyee: '%s' was removed (delete action converted to soft remove).") % product_label,
                    subtype_xmlid="mail.mt_note",
                )

        remaining = self - to_soft_remove
        if remaining:
            return super(SaleOrderLine, remaining).unlink()

        return True