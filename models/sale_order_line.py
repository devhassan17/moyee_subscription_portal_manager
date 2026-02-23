from odoo import fields, models, _
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_moyee_is_removed = fields.Boolean(string="Removed (Moyee)", default=False, copy=False)

    def action_moyee_soft_remove(self):
        for line in self:
            if not line.order_id.is_subscription:
                raise UserError(_("This action is only allowed on subscription orders."))

            if line.qty_delivered and line.qty_delivered > 0:
                raise UserError(_("You cannot remove a delivered line."))

            line.write({
                "x_moyee_is_removed": True,
                "product_uom_qty": 0.0,
            })
        return True
