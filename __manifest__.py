# File: moyee_subscription_portal_manager/__manifest__.py
{
    "name": "Moyee Subscription Portal Manager",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "summary": "Soft-remove subscription sale order lines and prevent future recurring invoicing.",
    "description": """
Manager-only build:
- Soft remove subscription products (qty=0 + metadata)
- Hide removed lines in backend UI (server-side domains)
- Exclude removed lines from invoice creation
- Filter invoice PDF lines for safety
""",
    "author": "Moyee",
    "license": "LGPL-3",
    "depends": [
        "sale_management",
        "sale_subscription",  # Enterprise app: subscription sale orders
        "account",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
        "reports/report_invoice.xml",
    ],
    "installable": True,
    "application": False,
    'assets': {
    'web.assets_backend': [
        'moyee_subscription_portal_manager/static/src/js/hide_zero_qty_lines.js',
        'moyee_subscription_portal_manager/static/src/css/hide_zero_qty_lines.css',
    ],
},
}
