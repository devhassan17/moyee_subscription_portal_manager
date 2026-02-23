{
    "name": "Moyee - Subscription Portal Manager",
    "version": "18.0.1.0.0",
    "category": "Website",
    "summary": "Manage subscription portal actions & hide removed lines",
    "depends": [
        "sale",
        "sale_subscription",
        "account",
        "portal",
        "website",
    ],
    "data": [
        "views/portal_templates.xml",
        "views/sale_order_views.xml",
        "reports/report_invoice_hide_removed_lines.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}