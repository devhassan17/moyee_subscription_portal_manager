# File: moyee_subscription_portal_manager/controllers/website_sale.py
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale


class MoyeeWebsiteSale(WebsiteSale):

    def _prepare_address_form_values(self, *args, **kwargs):
        values = super()._prepare_address_form_values(*args, **kwargs)
        company = request.website.company_id or request.env.company
        if company and "moyee_checkout_country_ids" in company._fields and company.moyee_checkout_country_ids:
            if "countries" in values:
                values["countries"] = values["countries"] & company.moyee_checkout_country_ids
        return values

    def checkout_values(self, *args, **kwargs):
        values = super().checkout_values(*args, **kwargs)
        company = request.website.company_id or request.env.company
        if company and "moyee_checkout_country_ids" in company._fields and company.moyee_checkout_country_ids:
            if "countries" in values:
                values["countries"] = values["countries"] & company.moyee_checkout_country_ids
        return values
