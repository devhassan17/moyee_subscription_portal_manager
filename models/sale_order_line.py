from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_moyee_is_removed = fields.Boolean(default=False, index=True)
    x_moyee_removed_on = fields.Datetime()
    x_moyee_removed_by = fields.Many2one("res.users")
    x_moyee_remove_reason = fields.Text()

    def action_moyee_soft_remove(self, reason=None):
        for line in self:
            if line.x_moyee_is_removed:
                continue

            line.write({
                "product_uom_qty": 0,
                "x_moyee_is_removed": True,
                "x_moyee_removed_on": fields.Datetime.now(),
                "x_moyee_removed_by": self.env.user.id,
                "x_moyee_remove_reason": reason or False,
            })

            # Cancel open stock moves
            moves = self.env["stock.move"].search([
                ("sale_line_id", "=", line.id),
                ("state", "not in", ["done", "cancel"])
            ])
            moves._action_cancel()

            line.order_id.message_post(
                body=_(
                    "Product %s removed from subscription by %s.<br/>Reason: %s"
                ) % (
                    line.product_id.display_name,
                    self.env.user.name,
                    reason or "-"
                )
            )