# File: moyee_subscription_portal_manager/models/moyee_frontend_code_settings.py
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class MoyeeFrontendCodeSettings(models.TransientModel):
    _name = "moyee.frontend.code.settings"
    _description = "Frontend Tracking and Data Layer Code Settings"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Active Company",
        required=True,
        default=lambda self: self.env.company,
        help="Select the company for which to configure frontend tracking and data layer scripts.",
    )
    moyee_enable_frontend_scripts = fields.Boolean(
        string="Enable Tracking Scripts for this Company",
        default=True,
        help="If checked, custom tracking scripts will be active and injected for this specific company.",
    )
    moyee_frontend_header_code = fields.Text(
        string="Header Code (JS / Tracking / Data Layers)",
        help="JavaScript or tracking code (e.g. Google Tag Manager, DataLayers) to inject into the <head> of frontend website and portal pages.",
    )
    moyee_frontend_body_code = fields.Text(
        string="Body Code (JS / Tracking / Noscript)",
        help="JavaScript or tracking code (e.g. Google Tag Manager noscript, body data layers) to inject inside the <body> of frontend website and portal pages.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        res.update(
            {
                "company_id": company.id,
                "moyee_enable_frontend_scripts": getattr(company, "moyee_enable_frontend_scripts", True),
                "moyee_frontend_header_code": company.moyee_frontend_header_code or "",
                "moyee_frontend_body_code": company.moyee_frontend_body_code or "",
            }
        )
        return res

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id:
            self.moyee_enable_frontend_scripts = getattr(self.company_id, "moyee_enable_frontend_scripts", True)
            self.moyee_frontend_header_code = self.company_id.moyee_frontend_header_code or ""
            self.moyee_frontend_body_code = self.company_id.moyee_frontend_body_code or ""

    def action_save(self):
        self.ensure_one()
        if self.company_id:
            self.company_id.sudo().write(
                {
                    "moyee_enable_frontend_scripts": self.moyee_enable_frontend_scripts,
                    "moyee_frontend_header_code": self.moyee_frontend_header_code or False,
                    "moyee_frontend_body_code": self.moyee_frontend_body_code or False,
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Saved Successfully"),
                "message": _("Frontend tracking scripts and company settings successfully updated."),
                "type": "success",
                "sticky": False,
            },
        }
