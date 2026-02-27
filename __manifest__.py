# File: moyee_subscription_portal_manager/__manifest__.py
{
    "name": "Moyee Subscription Portal Manager",
    "version": "18.0.2.1.0",
    "category": "Sales",
    "summary": "Soft-remove subscription sale order lines and allow secure portal self-service actions.",
    "description": """\
Portal + backend build:
- Soft remove subscription products (qty=0 + metadata)
- Hide removed lines in backend UI (server-side domains)
- Exclude removed lines from invoice creation
- Filter invoice PDF lines for safety
- Portal self-service: change address, push next date, add/remove products, pause/resume
""",
    "author": "Moyee",
    "license": "LGPL-3",
    "depends": [
        "sale_management",
        "sale_subscription",
        "account",
        "portal",
        "website",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
        "views/portal_subscription_templates.xml",
        "reports/report_invoice.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "moyee_subscription_portal_manager/static/src/js/hide_zero_qty_lines.js",
            "moyee_subscription_portal_manager/static/src/css/hide_zero_qty_lines.css",
        ],
    },
    "installable": True,
    "application": False,
}
