{
    "name": "Moyee Subscription Portal Manager",
    "version": "18.0.1.0.1",
    "summary": "Advanced Subscription Management & Portal Control (Base Module)",
    "description": "Odoo 18 base module: manage subscription products from portal/backend using sale.order subscription engine.",
    "author": "Moyee",
    "license": "LGPL-3",
    "category": "Sales/Subscriptions",
    "depends": ["sale_subscription", "portal", "sale_management", "website"],
    "data": [
        "security/security_rules.xml",
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
        "views/wizard_views.xml",
        "views/portal_templates.xml"
    ],
    "installable": True,
    "application": True
}
