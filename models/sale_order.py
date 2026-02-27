# File: moyee_subscription_portal_manager/models/sale_order.py
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_subscription_order = fields.Boolean(
        string="Is Subscription Order",
        compute="_compute_is_subscription_order",
        store=False,
    )

    moyee_removed_line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="order_id",
        string="Removed Lines",
        domain=[("x_moyee_is_removed", "=", True)],
    )

    def _compute_is_subscription_order(self):
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
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda l: l.display_type or (not l.x_moyee_is_removed and l.product_uom_qty > 0))

    def _get_order_lines_to_report(self):
        """Filter portal/order report lines (server-side) to hide soft-removed items."""
        try:
            lines = super()._get_order_lines_to_report()
        except AttributeError:
            lines = self.order_line
        return lines.filtered(lambda l: l.display_type or (not l.x_moyee_is_removed and l.product_uom_qty > 0))

    # -----------------------
    # Portal security helpers
    # -----------------------
    def _moyee_portal_check_access(self, *, portal_user=None, require_subscription=True):
        self.ensure_one()
        portal_user = portal_user or self.env.user

        if portal_user.has_group("base.group_user"):
            return True

        if portal_user._is_public():
            raise AccessError(_("You must be logged in to manage subscriptions."))

        if require_subscription and not self.is_subscription_order:
            raise AccessError(_("This record is not a subscription."))

        if self.partner_id.commercial_partner_id != portal_user.partner_id.commercial_partner_id:
            raise AccessError(_("You do not have access to this subscription."))

        if self.state not in ("sale", "done"):
            raise UserError(_("This subscription is not in a confirmed state."))

        if "subscription_status" in self._fields and self.subscription_status:
            if self.subscription_status in ("closed", "cancel", "churned"):
                raise UserError(_("This subscription is closed."))

        return True

    def _moyee_get_subscription_next_date_field_name(self):
        self.ensure_one()
        for fname in ("recurring_next_date", "next_invoice_date", "next_delivery_date", "x_next_delivery_date"):
            if fname in self._fields:
                return fname
        return False

    def _moyee_get_portal_addable_products(self):
        self.ensure_one()
        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()

        domain = [("sale_ok", "=", True)]
        if "subscription_ok" in Template._fields:
            domain.append(("product_tmpl_id.subscription_ok", "=", True))
        elif "recurring_invoice" in Template._fields:
            domain.append(("product_tmpl_id.recurring_invoice", "=", True))

        if "company_id" in Product._fields and self.company_id:
            domain.append(("company_id", "in", [False, self.company_id.id]))

        return Product.search(domain, order="name, id", limit=200)

    def _moyee_portal_validate_address(self, portal_user, partner_id):
        partner = self.env["res.partner"].sudo().browse(int(partner_id)).exists()
        if not partner:
            raise ValidationError(_("Invalid address."))
        if partner.commercial_partner_id != portal_user.partner_id.commercial_partner_id:
            raise ValidationError(_("Invalid address."))
        return partner

    # -----------------------
    # Portal actions
    # -----------------------
    def moyee_portal_change_address(self, *, portal_user_id, shipping_partner_id=None, invoice_partner_id=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        vals = {}
        if shipping_partner_id:
            ship = self._moyee_portal_validate_address(portal_user, shipping_partner_id)
            vals["partner_shipping_id"] = ship.id
        if invoice_partner_id:
            inv = self._moyee_portal_validate_address(portal_user, invoice_partner_id)
            vals["partner_invoice_id"] = inv.id
        if not vals:
            raise UserError(_("Please select at least one address."))

        self.sudo().write(vals)
        self.with_user(1).message_post(
            body=_("Moyee: customer updated subscription addresses via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def moyee_portal_push_next_date(self, *, portal_user_id, next_date):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        field_name = self._moyee_get_subscription_next_date_field_name()
        if not field_name:
            raise UserError(_("No 'next date' field was found on this subscription."))

        next_date = (next_date or "").strip()
        if not next_date:
            raise ValidationError(_("Please provide a date."))

        field = self._fields[field_name]
        if isinstance(field, fields.Date):
            value = fields.Date.from_string(next_date)
            if not value:
                raise ValidationError(_("Invalid date format."))
            if value < fields.Date.today():
                raise ValidationError(_("The next date cannot be in the past."))
        else:
            value = fields.Datetime.from_string(next_date)
            if not value:
                raise ValidationError(_("Invalid date/time format."))
            if value < fields.Datetime.now():
                raise ValidationError(_("The next date cannot be in the past."))

        self.sudo().write({field_name: value})
        self.with_user(1).message_post(
            body=_("Moyee: customer updated the next date via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def moyee_portal_add_product(self, *, portal_user_id, product_id, qty):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        if qty <= 0:
            raise ValidationError(_("Quantity must be greater than 0."))

        product = self.env["product.product"].sudo().browse(int(product_id)).exists()
        if not product:
            raise ValidationError(_("Invalid product."))

        allowed = self._moyee_get_portal_addable_products()
        if product not in allowed:
            raise AccessError(_("This product cannot be added to your subscription."))

        existing = self.order_line.filtered(
            lambda l: (not l.display_type) and (not l.x_moyee_is_removed) and l.product_id == product
        )
        if existing:
            line = existing[0]
            line.sudo().write({"product_uom_qty": line.product_uom_qty + qty})
            self.with_user(1).message_post(
                body=_("Moyee: customer increased quantity for %s via portal.") % product.display_name,
                subtype_xmlid="mail.mt_note",
                author_id=portal_user.partner_id.id,
            )
            return True

        SaleOrderLine = self.env["sale.order.line"].sudo()
        new_line = SaleOrderLine.new(
            {"order_id": self.id, "product_id": product.id, "product_uom_qty": qty}
        )
        new_line._onchange_product_id()
        new_line.product_uom_qty = qty
        if hasattr(new_line, "_onchange_product_uom_qty"):
            new_line._onchange_product_uom_qty()

        vals = new_line._convert_to_write(new_line._cache)
        vals.update(
            {
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "x_moyee_is_removed": False,
                "x_moyee_removed_on": False,
                "x_moyee_removed_by": False,
                "x_moyee_remove_reason": False,
            }
        )
        SaleOrderLine.create(vals)

        self.with_user(1).message_post(
            body=_("Moyee: customer added %s (qty %s) via portal.") % (product.display_name, qty),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def _moyee_set_subscription_paused_state(self, paused=True):
        self.ensure_one()

        if paused:
            for method_name in ("action_pause", "action_suspend"):
                if hasattr(self, method_name):
                    getattr(self.sudo(), method_name)()
                    return True
        else:
            for method_name in ("action_resume", "action_reactivate"):
                if hasattr(self, method_name):
                    getattr(self.sudo(), method_name)()
                    return True

        if "subscription_status" in self._fields:
            self.sudo().write({"subscription_status": "paused" if paused else "in_progress"})
            return True

        raise UserError(_("Pause/resume is not available for this subscription implementation."))

    def moyee_portal_pause(self, *, portal_user_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)
        self._moyee_set_subscription_paused_state(paused=True)

        self.with_user(1).message_post(
            body=_("Moyee: customer paused the subscription via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def moyee_portal_resume(self, *, portal_user_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)
        self._moyee_set_subscription_paused_state(paused=False)

        self.with_user(1).message_post(
            body=_("Moyee: customer resumed the subscription via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True
