# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

class SaleSubscription(models.Model):
    _inherit = "sale.subscription"

    # Portal action toggles (can also be moved to res.config.settings)
    allow_portal_product_change = fields.Boolean(string="Allow Portal: Change Product", default=True)
    allow_portal_add_product = fields.Boolean(string="Allow Portal: Add Product", default=True)
    allow_portal_remove_product = fields.Boolean(string="Allow Portal: Remove Product", default=True)
    allow_portal_pause = fields.Boolean(string="Allow Portal: Pause Subscription", default=True)
    allow_portal_frequency_change = fields.Boolean(string="Allow Portal: Change Frequency", default=True)
    allow_portal_address_change = fields.Boolean(string="Allow Portal: Change Address", default=True)
    allow_portal_push_delivery = fields.Boolean(string="Allow Portal: Push Delivery Date", default=True)

    def moyee_check_portal_access(self):
        """Ensure the current user is allowed to operate on this subscription from portal."""
        self.ensure_one()
        user = self.env.user
        if user.has_group("base.group_user"):
            return True  # backend staff
        # portal user: must own the subscription
        if self.partner_id != user.partner_id:
            raise AccessError(_("You do not have access to this subscription."))
        return True

    def moyee_get_active_lines_for_billing(self, invoice_date=None):
        """Return subscription lines that should be billed for the provided invoice_date."""
        self.ensure_one()
        invoice_date = invoice_date or fields.Date.context_today(self)
        lines = self.recurring_invoice_line_ids
        return lines.filtered(lambda l:
            l.is_active_for_billing
            and (not l.start_date or l.start_date <= invoice_date)
            and (not l.end_date or invoice_date < l.end_date)
        )

    # NOTE: Invoicing internals can vary by Odoo version and enterprise modules.
    # This override is intentionally defensive and minimal in the base module.
    # You can extend it later to exclude inactive lines during invoice creation.
    def _recurring_create_invoice(self, *args, **kwargs):
        """Base hook: calls super and returns created invoice(s).
        TODO (project-specific): ensure inactive lines are not copied to invoice lines.
        """
        sup = super(SaleSubscription, self)
        fn = getattr(sup, "_recurring_create_invoice", None)
        if not fn:
            # Fallback for possible alternate method names
            fn = getattr(sup, "_create_recurring_invoice", None)
        if not fn:
            raise UserError(_("Recurring invoice method not found to extend in this Odoo build."))
        return fn(*args, **kwargs)
