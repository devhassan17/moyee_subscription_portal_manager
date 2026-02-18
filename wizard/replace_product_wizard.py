# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MoyeeReplaceProductWizard(models.TransientModel):
    _name = "moyee.subscription.replace.product.wizard"
    _description = "Replace Product on Subscription (Moyee)"

    subscription_id = fields.Many2one("sale.subscription", required=True)
    old_line_id = fields.Many2one("sale.subscription.line", string="Old Line", required=True)
    new_product_id = fields.Many2one("product.product", string="New Product", required=True)
    quantity = fields.Float(default=1.0)
    effective_date = fields.Date(default=fields.Date.context_today)
    note = fields.Char()

    @api.onchange("subscription_id")
    def _onchange_subscription_id(self):
        if self.subscription_id:
            return {"domain": {"old_line_id": [("id", "in", self.subscription_id.recurring_invoice_line_ids.ids)]}}
        return {"domain": {"old_line_id": []}}

    def action_apply(self):
        self.ensure_one()
        sub = self.subscription_id
        if not sub:
            raise UserError(_("Subscription is required."))
        # End old line
        self.old_line_id.moyee_end_line(end_date=self.effective_date, note=self.note, source="backend")
        # Create new line
        self.env["sale.subscription.line"].create({
            "subscription_id": sub.id,
            "product_id": self.new_product_id.id,
            "quantity": self.quantity,
            "is_active_for_billing": True,
            "start_date": self.effective_date,
            "change_source": "backend",
            "change_note": self.note,
        })
        sub.message_post(body=_("Product replaced via Moyee wizard."))
        return {"type": "ir.actions.act_window_close"}
