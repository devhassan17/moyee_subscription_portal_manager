# File: moyee_subscription_portal_manager/models/moyee_frontend_code_settings.py
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MoyeeFrontendCodeSettings(models.TransientModel):
    _name = "moyee.frontend.code.settings"
    _description = "Frontend Tracking and Data Layer Code Settings"

    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="moyee_frontend_code_settings_company_rel",
        column1="wizard_id",
        column2="company_id",
        string="Active Companies",
        required=True,
        help="Select one or more companies where these frontend tracking and data layer scripts will be active.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Primary Company",
        default=lambda self: self.env.company,
    )
    moyee_enable_frontend_scripts = fields.Boolean(
        string="Enable Tracking Scripts for Selected Companies",
        default=True,
        help="If checked, custom tracking scripts will be active and injected for all selected companies.",
    )
    moyee_frontend_header_code = fields.Html(
        string="Header Code (JS / Tracking / Data Layers)",
        sanitize=False,
        help="JavaScript or tracking code (e.g. Google Tag Manager, DataLayers) to inject into the <head> of frontend website and portal pages.",
    )
    moyee_frontend_body_code = fields.Html(
        string="Body Code (JS / Tracking / Noscript)",
        sanitize=False,
        help="JavaScript or tracking code (e.g. Google Tag Manager noscript, body data layers) to inject inside the <body> of frontend website and portal pages.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Load companies that currently have frontend tracking enabled
        active_companies = self.env["res.company"].sudo().search([
            ("moyee_enable_frontend_scripts", "=", True),
        ])
        if not active_companies:
            active_companies = self.env.company

        # Pick primary company from active set or fallback
        primary_company = self.env.company if self.env.company in active_companies else active_companies[:1]

        res.update(
            {
                "company_id": primary_company.id if primary_company else False,
                "company_ids": [(6, 0, active_companies.ids)],
                "moyee_enable_frontend_scripts": getattr(primary_company, "moyee_enable_frontend_scripts", True),
                "moyee_frontend_header_code": primary_company.moyee_frontend_header_code or "",
                "moyee_frontend_body_code": primary_company.moyee_frontend_body_code or "",
            }
        )
        return res

    @api.onchange("company_ids")
    def _onchange_company_ids(self):
        if self.company_ids and not self.moyee_frontend_header_code and not self.moyee_frontend_body_code:
            first_company = self.company_ids[0]
            self.moyee_frontend_header_code = first_company.moyee_frontend_header_code or ""
            self.moyee_frontend_body_code = first_company.moyee_frontend_body_code or ""
            self.moyee_enable_frontend_scripts = getattr(first_company, "moyee_enable_frontend_scripts", True)

    def action_save(self):
        self.ensure_one()
        if not self.company_ids:
            raise UserError(_("Please select at least one company."))

        header_code = self.moyee_frontend_header_code or ""
        body_code = self.moyee_frontend_body_code or ""

        # If raw JS without tags, wrap nicely
        if header_code and not ("<script" in str(header_code).lower() or "<noscript" in str(header_code).lower() or "<!--" in str(header_code) or "<" in str(header_code)):
            header_code = f"<script type=\"text/javascript\">\n{header_code}\n</script>"
        if body_code and not ("<script" in str(body_code).lower() or "<noscript" in str(body_code).lower() or "<!--" in str(body_code) or "<" in str(body_code)):
            body_code = f"<script type=\"text/javascript\">\n{body_code}\n</script>"

        # Apply settings and code to all selected companies
        self.company_ids.sudo().write(
            {
                "moyee_enable_frontend_scripts": self.moyee_enable_frontend_scripts,
                "moyee_frontend_header_code": header_code or False,
                "moyee_frontend_body_code": body_code or False,
            }
        )

        # Disable scripts on any companies that were unselected
        unselected_companies = self.env["res.company"].sudo().search([
            ("id", "not in", self.company_ids.ids),
            ("moyee_enable_frontend_scripts", "=", True),
        ])
        if unselected_companies:
            unselected_companies.write({"moyee_enable_frontend_scripts": False})

        count = len(self.company_ids)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Saved Successfully"),
                "message": _("Frontend tracking scripts updated for %s selected company(ies).") % count,
                "type": "success",
                "sticky": False,
            },
        }
