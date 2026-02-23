{
    "name": "Moyee Subscription Portal Manager",
    "version": "18.0.1.1.0",
    "category": "Sales/Subscriptions",
    "author" : "Managemyweb.co",
    "summary": "Soft delete and portal management for subscriptions",
    "depends": [
        "sale_management",
        "sale_subscription",
        "account",
        "portal",
        "stock",
    ],
    "data": [
        "security/subscription_security.xml",
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
        "views/portal_templates.xml",
        "reports/invoice_report.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "moyee_subscription_portal_manager/static/src/js/portal_subscription.js",
        ],
    },
    "installable": True,
    "application": True,
    
    "license": "LGPL-3",
}