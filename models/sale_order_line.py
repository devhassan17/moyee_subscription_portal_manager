# -*- coding: utf-8 -*-
from odoo import fields, models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_active_for_billing = fields.Boolean(
        string="Active for Billing",
        default=True,
        help="If disabled, this line will be ignored for future recurring invoices.",
        tracking=True,
    )
    start_date = fields.Date(string="Start Date", tracking=True)
    end_date = fields.Date(string="End Date", tracking=True)

    change_source = fields.Selection(
        [("portal", "Portal"), ("backend", "Backend")],
        string="Change Source",
        default="backend",
        tracking=True,
    )
    change_date = fields.Datetime(string="Change Date", default=fields.Datetime.now, tracking=True)
    changed_by = fields.Many2one("res.users", string="Changed By", default=lambda self: self.env.user, tracking=True)
    change_note = fields.Text(string="Change Note", tracking=True)

    def moyee_end_line(self, end_date=False, note=False, source="backend"):
        for line in self:
            vals = {
                "is_active_for_billing": False,
                "end_date": end_date or fields.Date.context_today(self),
                "change_source": source,
                "change_date": fields.Datetime.now(),
                "changed_by": self.env.user.id,
            }
            if note:
                vals["change_note"] = note
            line.write(vals)

    def moyee_activate_line(self, start_date=False, note=False, source="backend"):
        for line in self:
            vals = {
                "is_active_for_billing": True,
                "start_date": start_date or fields.Date.context_today(self),
                "end_date": False,
                "change_source": source,
                "change_date": fields.Datetime.now(),
                "changed_by": self.env.user.id,
            }
            if note:
                vals["change_note"] = note
            line.write(vals)
