# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

class MoyeeReplaceProductWizard(models.TransientModel):
    _name = "moyee.subscription.replace.product.wizard"
    _description = "Replace Product on Subscription (Moyee)"

    order_id = fields.Many2one("sale.order", required=True, string="Subscription Order")
    old_line_id = fields.Many2one("sale.order.line", string="Old Line", required=True)
    new_product_id = fields.Many2one("product.product", string="New Product", required=True)
    quantity = fields.Float(default=1.0)
    effective_date = fields.Date(default=fields.Date.context_today)
    note = fields.Char()

    @api.onchange("order_id")
    def _onchange_order_id(self):
        if self.order_id:
            return {"domain": {"old_line_id": [("id", "in", self.order_id.order_line.ids)]}}
        return {"domain": {"old_line_id": []}}

    def action_apply(self):
        self.ensure_one()
        order = self.order_id
        if not order:
            raise UserError(_("Subscription order is required."))

        # End old line (soft remove)
        self.old_line_id.moyee_end_line(end_date=self.effective_date, note=self.note, source="backend")

        # Create new line
        self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.new_product_id.id,
            "product_uom_qty": self.quantity,
            "is_active_for_billing": True,
            "start_date": self.effective_date,
            "change_source": "backend",
            "change_note": self.note or "Backend product replace",
        })
        order.message_post(body=_("Product replaced via Moyee wizard."))
        return {"type": "ir.actions.act_window_close"}
