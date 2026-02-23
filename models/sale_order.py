from odoo import models, fields, api
from odoo.exceptions import AccessError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_subscription_order = fields.Boolean(
        compute="_compute_is_subscription",
        store=False
    )

    def _compute_is_subscription(self):
        for order in self:
            order.is_subscription_order = bool(order.subscription_id)

    # 🔒 Portal ownership validation
    def _check_portal_access(self):
        self.ensure_one()
        partner = self.env.user.partner_id.commercial_partner_id
        if self.partner_id.commercial_partner_id != partner:
            raise AccessError("Not allowed.")

    # 💰 Prevent removed lines from invoicing
    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final)
        return lines.filtered(
            lambda l: not l.x_moyee_is_removed and l.product_uom_qty > 0
        )