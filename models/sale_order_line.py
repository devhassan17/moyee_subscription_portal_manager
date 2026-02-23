from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_moyee_is_removed = fields.Boolean(string="Removed on Portal", default=False)