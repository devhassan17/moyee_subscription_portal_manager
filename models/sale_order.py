from odoo import models, fields
from odoo.exceptions import AccessError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Compatibility field: some existing views in your DB reference this
    allow_portal_product_change = fields.Boolean(
        string="Allow Portal Product Change",
        default=False,
        help="Technical/compatibility field used by customized Sale Order views to control portal subscription edits."
    )

    def _check_portal_access(self):
        self.ensure_one()
        partner = self.env.user.partner_id.commercial_partner_id
        if self.partner_id.commercial_partner_id != partner:
            raise AccessError("Not allowed.")

    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final)
        return lines.filtered(lambda l: not l.x_moyee_is_removed and l.product_uom_qty > 0)