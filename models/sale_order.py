from odoo import models, fields
from odoo.exceptions import AccessError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Compatibility flags referenced by existing DB views/customizations
    allow_portal_product_change = fields.Boolean(default=False)
    allow_portal_add_product = fields.Boolean(default=False)
    allow_portal_change_address = fields.Boolean(default=False)
    allow_portal_push_delivery_date = fields.Boolean(default=False)
    allow_portal_pause = fields.Boolean(default=False)
    allow_portal_stop = fields.Boolean(default=False)
    allow_portal_change_frequency = fields.Boolean(default=False)
    allow_portal_delete_product = fields.Boolean(default=False)
    allow_portal_qty_change = fields.Boolean(default=False)

    def _check_portal_access(self):
        self.ensure_one()
        partner = self.env.user.partner_id.commercial_partner_id
        if self.partner_id.commercial_partner_id != partner:
            raise AccessError("Not allowed.")

    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final)
        return lines.filtered(lambda l: not l.x_moyee_is_removed and l.product_uom_qty > 0)