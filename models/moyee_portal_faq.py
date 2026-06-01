# File: moyee_subscription_portal_manager/models/moyee_portal_faq.py
from odoo import fields, models


class MoyeePortalFaq(models.Model):
    _name = "moyee.portal.faq"
    _description = "Moyee Portal FAQ"
    _order = "sequence, id"

    sequence = fields.Integer(string="Sequence", default=10)
    question = fields.Char(string="Question", required=True, translate=True)
    answer = fields.Text(string="Answer", required=True, translate=True)
    is_active = fields.Boolean(string="Active", default=True)
