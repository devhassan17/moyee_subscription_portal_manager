# Moyee Subscription Portal Manager

Advanced portal management for Moyee Coffee subscriptions.

## Features

- **Soft Remove**: Move sale order lines to a 'removed' state with metadata instead of hard deleting.
- **Backend Visibility**: Removed lines are hidden from standard views but accessible to administrators.
- **Invoice Integration**: Automatically excludes zero-quantity or removed lines from invoices and PDF reports.
- **Portal Self-Service**:
    - Update delivery and billing addresses.
    - Postpone next delivery dates.
    - Add or remove products from active subscriptions.
    - Pause and resume subscriptions.

## Technical Details

- **Author**: Managemyweb.co
- **Maintainer**: ali@moyeecoffee.com
- **License**: LGPL-3
- **Odoo Version**: 18.0

## Installation

1. Install the module from the Odoo Apps menu.
2. Ensure dependencies (`sale_subscription`, `portal`, `website`) are installed.
3. Portal users will see a "Manage Subscription" section in their account.

---
© 2024 Managemyweb.co
