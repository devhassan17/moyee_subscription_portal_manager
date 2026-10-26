# Moyee Subscription Portal Manager
## Comprehensive Business Guide & Odoo 20 Migration Roadmap

---

# Part 1: Business & Feature Overview Document
*(For Clients, Managers, and Non-Technical Stakeholders)*

---

## 1. Executive Summary

The **Moyee Subscription Portal Manager** is a complete, custom-built e-commerce and operations management solution designed specifically for Moyee Coffee. It connects customer self-service on the website directly with Odoo’s backend ERP operations.

The system addresses two essential business goals:
1. **Empowers Customers:** Provides coffee subscribers with an intuitive self-service portal to manage their coffee deliveries (changing beans, adjusting grind or weight, postponing delivery dates, updating addresses, pausing or resuming) without needing to contact customer support.
2. **Protects Financial & Billing Integrity:** Introduces a smart "soft-remove" mechanism that prevents billing discrepancies. Discontinued, paused, or customer-cancelled items never appear on automated recurring invoices or customer PDF statements, while maintaining complete historical audit records for operations and accounting teams.

---

## 2. Customer Self-Service Experience (`/my/home`)

Customers have access to a branded dashboard that makes managing their coffee deliveries seamless:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CUSTOMER ACCOUNT PORTAL                         │
├───────────────────────────────────┬────────────────────────────────────┤
│           COFFEE CHOICES          │         DELIVERY CONTROLS          │
│  • Change Coffee Blends & Single  │  • Pick Next Delivery Date         │
│    Origins                        │  • Skip Next Shipment              │
│  • Switch Grind (Beans, Filter,   │  • Pause / Resume Subscription     │
│    Espresso, Capsules)            │  • Update Shipping & Billing       │
│  • Adjust Package Weights         │    Addresses Independently         │
│  • Add Extra Products & Bags      │  • 1-Click Reorder for Past Orders │
└───────────────────────────────────┴────────────────────────────────────┘
```

* **Instant Coffee Variant Swaps:** Customers can switch between whole beans, filter grind, espresso grind, or capsules, and select their preferred package weight (250g, 1kg, 25 capsules) without needing to cancel and re-create their subscription.
* **Pause, Resume, or Skip a Delivery:** Customers going on vacation or with surplus coffee can pause their subscription with a single click, choose a specific resume date, or simply skip the upcoming shipment.
* **Flexible Delivery Rescheduling:** Customers can select any future shipment date using a calendar date-picker.
* **Separate Shipping & Billing Address Management:** Customers can update their delivery address independently from their billing address without corrupting past orders or historical invoices.
* **One-Click Reorder for Past Orders:** Customers can re-order past purchases straight into their website shopping cart with a single click.
* **Interactive Coffee Education & Engagement:**
  * **"Brew Like a Pro" Guides:** Step-by-step coffee preparation guides (Aeropress, French Press, Pour Over, Espresso) displayed directly inside the account.
  * **Interactive FAQ Section:** Clear answers to common questions regarding delivery timing, bean origin, roast profiles, and billing.
  * **Brand Impact Story & Referrals:** Highlights Moyee's FairChain coffee farmers in Ethiopia, with a "Tell a Friend" referral card.

---

## 3. Financial & Invoicing Protection

In standard systems, deleting a subscription item can corrupt historical records, or worse, cause deleted products to appear on customer invoices with zero or incorrect amounts.

* **Smart "Soft-Removal":** When a subscription line is modified to zero quantity or removed (either by the customer on the web portal or by internal staff in the backend), it is marked as "soft-removed" rather than permanently erased.
* **Clean Invoices & Reports:** Automated recurring invoices and PDF printouts filter out removed or zero-quantity products. Customers never receive an invoice containing zero-euro lines or confusing crossed-out items.
* **Accidental Deletion Protection:** Staff members cannot accidentally delete shipping lines or delivery fees, preventing shipping revenue losses.
* **Complete Internal Audit Log:** Odoo's internal sales order form includes a dedicated "Removed Lines" tab that logs exactly who removed an item, when it was removed, and the reason.

---

## 4. Administration, Marketing, & Operational Tools

The module provides tools in Odoo’s backend settings that can be controlled without technical assistance:

* **Bulk Subscription Management Wizard:**
  * Add a new seasonal coffee or gift product across hundreds of active subscriptions in seconds.
  * Filter subscriptions by customer country, active/paused status, subscription age, or current products.
  * Bulk-remove retired or out-of-stock products with automatic logging.
* **Branding & Visual Customization:**
  * Adjust brand colors (Moyee Signature Pink and accent colors).
  * Choose preferred typography (Inter, Roboto, Outfit, Montserrat, Open Sans).
  * Toggle sections ON or OFF (e.g., show/hide FAQ, Brew Guides, or Upsell cards).
* **Controlled Rollout (A/B Testing):**
  * Activate the new customer portal for a selected pilot group before releasing it to all customers.
* **Product Catalog Filtering:**
  * Hide internal or non-subscriber products so only eligible coffees appear in the customer portal.

---

## 5. Summary of Business Impact

| Key Problem Solved | Tangible Business Benefit |
| :--- | :--- |
| **High Customer Support Workload** | Routine changes (address updates, bean swaps, date changes) are handled directly by customers, reducing support volume. |
| **Billing Inaccuracies & Inquiries** | Zero-quantity and removed items are filtered from invoices and PDFs, preventing customer disputes. |
| **Operational Bottlenecks on Seasonal Changes** | Operations can update hundreds of subscriptions simultaneously via the Bulk Wizard. |
| **Customer Retention & Churn Prevention** | Giving customers the flexibility to pause or skip deliveries prevents outright cancellations. |

---

# Part 2: Odoo 20 Upgrade Roadmap
*(Technical Specification for Migrating from Odoo 18 to Odoo 20)*

Migrating from Odoo 18 to Odoo 20 spans two major release cycles (Odoo 18 ➔ Odoo 19 ➔ Odoo 20). Below is the structured roadmap and checklist required to make the module fully compatible with Odoo 20.

---

## 1. Module Manifest & Dependency Alignment

- [ ] **Manifest Versioning:** Update `__manifest__.py` version string from `18.0.x.x` to `20.0.1.0.0`.
- [ ] **Core Dependencies Audit:** Verify dependencies in `__manifest__.py`:
  - `sale_management`
  - `sale_subscription`
  - `account`
  - `portal`
  - `website`
- [ ] **Asset Bundles Definition:** Confirm bundle syntax under `assets` (`web.assets_backend` and `web.assets_frontend`) conforms to Odoo 20 asset bundling standards.

---

## 2. Core Subscription Architecture & ORM Compatibility

Odoo frequently refines the `sale.order` subscription engine between major releases. The module already incorporates dynamic resolvers, but these core areas require verification:

- [ ] **Subscription State Machine:** Check native state field values in Odoo 20:
  - Verify subscription statuses (`subscription_state`: e.g., `3_progress`, `4_paused`, `churned`).
  - Verify pause/resume mechanics (`action_pause`, `action_resume`).
- [ ] **Recurring Plan Reference:** Confirm field naming convention for recurring plans (`plan_id` vs `recurring_plan_id`).
- [ ] **Next Invoice / Delivery Date Computation:** Validate field references for next shipment calculation (`recurring_next_date`, `next_invoice_date`).
- [ ] **Invoiceable Line Generation (`_get_invoiceable_lines`):** Check the method signature and hook in Odoo 20 to ensure soft-removed lines are omitted from recurring invoice creation.
- [ ] **Delivery Line Recognition:** Verify delivery product detection (`is_delivery` flag or `_is_delivery()` helper) on `sale.order.line`.
- [ ] **Python Version Support:** Ensure full compatibility with Python 3.12 / 3.13 (standard runtimes for Odoo 20).

---

## 3. Frontend & Backend JavaScript (OWL & DOM Helpers)

- [ ] **Backend OWL List Views (`hide_zero_qty_lines.js`):**
  - Odoo continues to upgrade its OWL (Odoo Web Library) component architecture.
  - Test the list renderer on sales order lines to confirm DOM selectors and classes remain valid, or update the script to use an OWL field patch.
- [ ] **Frontend Controllers & Security:**
  - Verify CSRF protection compliance on all portal POST routes (`csrf=True`).
  - Validate that `request.website.sale_get_order()` handles cart generation cleanly in Odoo 20 e-commerce.

---

## 4. QWeb Templates & XPath Verification

All template inheritance points must be validated against the base views of Odoo 20:

- [ ] **Invoice PDF Report (`reports/report_invoice.xml`):**
  - Verify template inheritance on `account.report_invoice_document`.
  - Validate that XPath `//table[@name='invoice_line_table']//t[@t-foreach='lines']` matches Odoo 20's invoice report structure.
- [ ] **Backend Sale Order View (`views/sale_order_views.xml`):**
  - Confirm notebook and page layout targets for displaying the "Removed Subscription Lines" tab.
- [ ] **Customer Portal Templates:**
  - Verify that `portal.portal_layout` and base `/my` portal controllers maintain identical routing patterns.
  - Since the module utilizes dedicated standalone sub-templates (`portal_my_account_sub_templates.xml`), compatibility risks with core portal templates are minimal.

---

## 5. Database Schema & Data Migration Strategy

When upgrading an existing production database:

- [ ] **Custom Field Preservation:** Confirm custom fields (`x_moyee_is_removed`, `x_moyee_removed_on`, `x_moyee_removed_by`, `x_moyee_remove_reason`) are recognized by the Odoo Upgrade Service.
- [ ] **Configuration Parameters:** Ensure system parameters (`ir.config_parameter`) for portal styling, colors, and toggle settings persist across the upgrade.
- [ ] **Migration Scripts:** Create a `migrations/20.0.1.0.0/` folder with `pre-migrate.py` or `post-migrate.py` if table schema adjustments are needed.

---

## 6. Testing & Deployment Checklist

1. **Local Test Environment:** Set up a clean Odoo 20 testing database.
2. **Installation Verification:** Run the module installation with unit tests enabled:
   ```bash
   odoo -d odoo20_staging -i moyee_subscription_portal_manager --test-enable --stop-after-init
   ```
3. **Billing Cycle Validation:** Create a subscription with active and soft-removed lines, trigger the automated billing cron, and confirm the generated invoice only bills active lines.
4. **Portal Verification:** Test user interactions on desktop and mobile:
   - Coffee selection, grind, and weight edits
   - Pause, skip, and resume actions
   - Address updates
   - 1-click reorder checkout flow
