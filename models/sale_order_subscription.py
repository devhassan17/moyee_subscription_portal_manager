# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import AccessError

class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Portal action toggles per subscription order
    allow_portal_product_change = fields.Boolean(string="Allow Portal: Change Product", default=True)
    allow_portal_add_product = fields.Boolean(string="Allow Portal: Add Product", default=True)
    allow_portal_remove_product = fields.Boolean(string="Allow Portal: Remove Product", default=True)
    allow_portal_pause = fields.Boolean(string="Allow Portal: Pause Subscription", default=True)
    allow_portal_frequency_change = fields.Boolean(string="Allow Portal: Change Frequency", default=True)
    allow_portal_address_change = fields.Boolean(string="Allow Portal: Change Address", default=True)
    allow_portal_push_delivery = fields.Boolean(string="Allow Portal: Push Delivery Date", default=True)

    def moyee_check_portal_access(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group("base.group_user"):
            return True
        if self.partner_id != user.partner_id:
            raise AccessError(_("You do not have access to this subscription."))
        return True

    def moyee_get_active_lines_for_billing(self, invoice_date=None):
        self.ensure_one()
        invoice_date = invoice_date or fields.Date.context_today(self)
        lines = self.order_line
        return lines.filtered(lambda l:
            getattr(l, "is_active_for_billing", True)
            and (not l.start_date or l.start_date <= invoice_date)
            and (not l.end_date or invoice_date < l.end_date)
        )
