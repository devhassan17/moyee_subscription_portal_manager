# File: moyee_subscription_portal_manager/models/moyee_portal_brew_guide.py
from odoo import fields, models


class MoyeePortalBrewGuide(models.Model):
    _name = "moyee.portal.brew.guide"
    _description = "Moyee Portal Brew Guide Block"
    _order = "sequence, id"

    sequence = fields.Integer(string="Sequence", default=10)
    name = fields.Char(string="Method Name", required=True, translate=True)
    sub_info = fields.Char(string="Details (e.g. 3 min · 1:16)", required=True, translate=True)
    url = fields.Char(string="Guide Link URL", default="/shop")
    is_active = fields.Boolean(string="Active", default=True)
