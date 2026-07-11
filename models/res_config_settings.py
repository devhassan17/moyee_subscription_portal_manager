# File: moyee_subscription_portal_manager/models/res_config_settings.py
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    moyee_enable_portal_redesign = fields.Boolean(
        string="Enable Moyee Custom Portal Redesign",
        default=True,
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Master Toggle (Company Dependent)
    moyee_enable_portal_redesign = fields.Boolean(
        related="company_id.moyee_enable_portal_redesign",
        readonly=False,
        string="Enable Moyee Custom Portal Redesign",
    )

    # Styling Overrides
    moyee_primary_color = fields.Char(
        string="Primary Color",
        config_parameter="moyee_subscription_portal_manager.primary_color",
        default="#E91E8C",
    )
    moyee_secondary_color = fields.Char(
        string="Secondary Color (Light Accent)",
        config_parameter="moyee_subscription_portal_manager.secondary_color",
        default="#FCE4F3",
    )
    moyee_font_family = fields.Selection(
        [
            ("Inter", "Inter"),
            ("Roboto", "Roboto"),
            ("Outfit", "Outfit"),
            ("Montserrat", "Montserrat"),
            ("Open Sans", "Open Sans"),
            ("system-ui", "System Default"),
        ],
        string="Font Family",
        config_parameter="moyee_subscription_portal_manager.font_family",
        default="system-ui",
    )

    # Visibility Controls
    moyee_show_subscription = fields.Boolean(
        string="Show Subscription Section",
        config_parameter="moyee_subscription_portal_manager.show_subscription",
    )
    moyee_show_overview = fields.Boolean(
        string="Show Overview Section",
        config_parameter="moyee_subscription_portal_manager.show_overview",
    )
    moyee_show_orders = fields.Boolean(
        string="Show Orders Section",
        config_parameter="moyee_subscription_portal_manager.show_orders",
    )
    moyee_show_invoices = fields.Boolean(
        string="Show Invoices Section",
        config_parameter="moyee_subscription_portal_manager.show_invoices",
    )
    moyee_show_faq = fields.Boolean(
        string="Show FAQ Section",
        config_parameter="moyee_subscription_portal_manager.show_faq",
    )
    moyee_show_inspire = fields.Boolean(
        string="Show Inspire Section",
        config_parameter="moyee_subscription_portal_manager.show_inspire",
    )
    moyee_show_taf = fields.Boolean(
        string="Show Tell a Friend Card",
        config_parameter="moyee_subscription_portal_manager.show_taf",
    )
    moyee_show_brew_guides = fields.Boolean(
        string="Show Brew Guides Section",
        config_parameter="moyee_subscription_portal_manager.show_brew_guides",
    )

    # Sidebar Visibility Controls
    moyee_show_sidebar_profile = fields.Boolean(
        string="Show Profile Card",
        config_parameter="moyee_subscription_portal_manager.show_sidebar_profile",
    )
    moyee_show_sidebar_upsell = fields.Boolean(
        string="Show Upsell Card (Non-Subscribers)",
        config_parameter="moyee_subscription_portal_manager.show_sidebar_upsell",
    )
    moyee_show_sidebar_support = fields.Boolean(
        string="Show Support Card",
        config_parameter="moyee_subscription_portal_manager.show_sidebar_support",
    )

    # Content Overrides
    moyee_upsell_cta_url = fields.Char(
        string="Upsell CTA URL",
        config_parameter="moyee_subscription_portal_manager.upsell_cta_url",
        default="/shop",
    )
    moyee_brew_guides_all_url = fields.Char(
        string="All Brew Guides URL",
        config_parameter="moyee_subscription_portal_manager.brew_guides_all_url",
        default="/shop",
    )
    moyee_support_email = fields.Char(
        string="Support Email",
        config_parameter="moyee_subscription_portal_manager.support_email",
        default="hello@moyeecoffee.com",
    )

    # Inspire Content Overrides
    moyee_inspire_eyebrow = fields.Char(
        string="Inspire Section Eyebrow",
        config_parameter="moyee_subscription_portal_manager.inspire_eyebrow",
        default="Do you know where your coffee comes from?",
    )
    moyee_inspire_title = fields.Char(
        string="Inspire Section Title",
        config_parameter="moyee_subscription_portal_manager.inspire_title",
        default="Your coffee comes from Ethiopia",
    )
    moyee_inspire_body = fields.Char(
        string="Inspire Section Body",
        config_parameter="moyee_subscription_portal_manager.inspire_body",
        default="Your Moyee coffee comes from small farmers in the Kaffa forest in Ethiopia. They receive a fair price — thanks to you.",
    )
    moyee_inspire_btn1_text = fields.Char(
        string="Inspire Section Button 1 Text",
        config_parameter="moyee_subscription_portal_manager.inspire_btn1_text",
        default="Read the story",
    )
    moyee_inspire_btn1_url = fields.Char(
        string="Inspire Section Button 1 URL",
        config_parameter="moyee_subscription_portal_manager.inspire_btn1_url",
        default="/radical-impact-coffee",
    )
    moyee_inspire_btn2_text = fields.Char(
        string="Inspire Section Button 2 Text",
        config_parameter="moyee_subscription_portal_manager.inspire_btn2_text",
        default="Browse our coffee",
    )
    moyee_inspire_btn2_url = fields.Char(
        string="Inspire Section Button 2 URL",
        config_parameter="moyee_subscription_portal_manager.inspire_btn2_url",
        default="/shop",
    )

    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ICP = self.env["ir.config_parameter"].sudo()
        res.update(
            moyee_show_subscription=ICP.get_param("moyee_subscription_portal_manager.show_subscription", "True").lower() in ("true", "1", "yes"),
            moyee_show_overview=ICP.get_param("moyee_subscription_portal_manager.show_overview", "True").lower() in ("true", "1", "yes"),
            moyee_show_orders=ICP.get_param("moyee_subscription_portal_manager.show_orders", "True").lower() in ("true", "1", "yes"),
            moyee_show_invoices=ICP.get_param("moyee_subscription_portal_manager.show_invoices", "True").lower() in ("true", "1", "yes"),
            moyee_show_faq=ICP.get_param("moyee_subscription_portal_manager.show_faq", "True").lower() in ("true", "1", "yes"),
            moyee_show_inspire=ICP.get_param("moyee_subscription_portal_manager.show_inspire", "True").lower() in ("true", "1", "yes"),
            moyee_show_taf=ICP.get_param("moyee_subscription_portal_manager.show_taf", "True").lower() in ("true", "1", "yes"),
            moyee_show_brew_guides=ICP.get_param("moyee_subscription_portal_manager.show_brew_guides", "True").lower() in ("true", "1", "yes"),
            moyee_show_sidebar_profile=ICP.get_param("moyee_subscription_portal_manager.show_sidebar_profile", "True").lower() in ("true", "1", "yes"),
            moyee_show_sidebar_upsell=ICP.get_param("moyee_subscription_portal_manager.show_sidebar_upsell", "True").lower() in ("true", "1", "yes"),
            moyee_show_sidebar_support=ICP.get_param("moyee_subscription_portal_manager.show_sidebar_support", "True").lower() in ("true", "1", "yes"),
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("moyee_subscription_portal_manager.show_subscription", str(self.moyee_show_subscription))
        ICP.set_param("moyee_subscription_portal_manager.show_overview", str(self.moyee_show_overview))
        ICP.set_param("moyee_subscription_portal_manager.show_orders", str(self.moyee_show_orders))
        ICP.set_param("moyee_subscription_portal_manager.show_invoices", str(self.moyee_show_invoices))
        ICP.set_param("moyee_subscription_portal_manager.show_faq", str(self.moyee_show_faq))
        ICP.set_param("moyee_subscription_portal_manager.show_inspire", str(self.moyee_show_inspire))
        ICP.set_param("moyee_subscription_portal_manager.show_taf", str(self.moyee_show_taf))
        ICP.set_param("moyee_subscription_portal_manager.show_brew_guides", str(self.moyee_show_brew_guides))
        ICP.set_param("moyee_subscription_portal_manager.show_sidebar_profile", str(self.moyee_show_sidebar_profile))
        ICP.set_param("moyee_subscription_portal_manager.show_sidebar_upsell", str(self.moyee_show_sidebar_upsell))
        ICP.set_param("moyee_subscription_portal_manager.show_sidebar_support", str(self.moyee_show_sidebar_support))
