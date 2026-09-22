# File: moyee_subscription_portal_manager/models/moyee_subscription_bulk_product_wizard.py
import logging
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MoyeeSubscriptionBulkProductWizard(models.TransientModel):
    _name = "moyee.subscription.bulk.product.wizard"
    _description = "Bulk Subscription Product Addition Wizard"

    # ============================================================
    # Filter Criteria
    # ============================================================
    product_ids = fields.Many2many(
        comodel_name="product.product",
        relation="moyee_bulk_wizard_product_rel",
        column1="wizard_id",
        column2="product_id",
        string="Filter by Contained Products",
        help="Select products to filter subscriptions containing them.",
    )
    product_filter_mode = fields.Selection(
        [
            ("any", "Contains Any"),
            ("all", "Contains All"),
            ("exclude", "Does Not Contain"),
        ],
        string="Product Match Mode",
        default="any",
        required=True,
    )
    price_min = fields.Float(
        string="Min Subscription Price",
        help="Filter subscriptions with recurring amount >= Min Price.",
    )
    price_max = fields.Float(
        string="Max Subscription Price",
        help="Filter subscriptions with recurring amount <= Max Price.",
    )
    country_ids = fields.Many2many(
        comodel_name="res.country",
        relation="moyee_bulk_wizard_country_rel",
        column1="wizard_id",
        column2="country_id",
        string="Customer Country Filter",
        help="Filter subscriptions by customer country.",
    )
    subscription_age = fields.Selection(
        [
            ("all", "All Subscriptions"),
            ("new", "New Ones (Last 30 Days)"),
            ("old", "Old Ones (Older than 30 Days)"),
            ("custom", "Custom Date Range"),
        ],
        string="Subscription Age / Dates",
        default="all",
        required=True,
    )
    date_from = fields.Date(string="Created On / After")
    date_to = fields.Date(string="Created On / Before")

    subscription_state = fields.Selection(
        [
            ("all", "All States"),
            ("active", "Active Subscriptions Only"),
            ("paused", "Paused Subscriptions Only"),
        ],
        string="Subscription State Filter",
        default="active",
        required=True,
    )

    # ============================================================
    # Filtered Results / Preview
    # ============================================================
    subscription_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="moyee_bulk_product_wizard_sale_order_rel",
        column1="wizard_id",
        column2="order_id",
        string="Filtered Subscriptions",
        domain=[("state", "in", ["sale", "done"])],
    )
    matched_count = fields.Integer(
        string="Matched Subscriptions",
        compute="_compute_matched_count",
    )

    # ============================================================
    # Bulk Operations Target Configuration
    # ============================================================
    operation_type = fields.Selection(
        [
            ("add", "Add Product to Subscriptions"),
            ("remove", "Remove / Delete Product from Subscriptions"),
        ],
        string="Operation Type",
        default="add",
        required=True,
    )
    add_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product to Add in Bulk",
        domain=[("sale_ok", "=", True)],
        help="Select the specific product to add to all filtered subscriptions.",
    )
    add_qty = fields.Float(
        string="Quantity to Add",
        default=1.0,
    )
    add_price_unit = fields.Float(
        string="Unit Price",
        help="Unit price for the added product. Auto-filled from product list price.",
    )

    remove_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product to Remove in Bulk",
        domain=[("sale_ok", "=", True)],
        help="Select the specific product to soft-remove from all filtered subscriptions.",
    )
    remove_reason = fields.Char(
        string="Removal Reason",
        default="Bulk Product Removal Wizard",
        help="Reason logged in subscription order chatter when soft-removing this product.",
    )

    # ============================================================
    # Onchange & Compute Helpers
    # ============================================================
    @api.onchange("product_ids")
    def _onchange_product_ids(self):
        if self.product_ids and len(self.product_ids) == 1:
            if not self.remove_product_id:
                self.remove_product_id = self.product_ids[0].id
            if not self.add_product_id:
                self.add_product_id = self.product_ids[0].id

    @api.onchange("add_product_id")
    def _onchange_add_product_id(self):
        if self.add_product_id:
            self.add_price_unit = getattr(self.add_product_id, "lst_price", 0.0) or getattr(self.add_product_id, "list_price", 0.0) or 0.0

    @api.depends("subscription_ids")
    def _compute_matched_count(self):
        for wizard in self:
            wizard.matched_count = len(wizard.subscription_ids)

    # ============================================================
    # Filter Execution Action
    # ============================================================
    def action_apply_filter(self):
        """Query subscriptions matching specified criteria and update subscription_ids."""
        self.ensure_one()

        # Find all confirmed subscription orders
        SaleOrder = self.env["sale.order"]
        domain = [("state", "in", ["sale", "done"])]
        if "is_subscription" in SaleOrder._fields:
            domain.append(("is_subscription", "=", True))
        elif "plan_id" in SaleOrder._fields:
            domain.append(("plan_id", "!=", False))
        elif "recurring_plan_id" in SaleOrder._fields:
            domain.append(("recurring_plan_id", "!=", False))

        all_orders = SaleOrder.search(domain)

        # Filter strictly for subscription orders
        orders = all_orders.filtered(lambda o: o._moyee_is_subscription_order())

        # 1. State Filter
        if self.subscription_state == "active":
            orders = orders.filtered(
                lambda o: not getattr(o, "subscription_state", False)
                or str(o.subscription_state).lower() not in ("closed", "cancel", "churned", "4_closed", "4_paused")
            )
        elif self.subscription_state == "paused":
            orders = orders.filtered(
                lambda o: getattr(o, "subscription_state", "") == "4_paused"
                or "paused" in str(getattr(o, "subscription_state", "")).lower()
            )

        # 2. Country Filter
        if self.country_ids:
            c_ids = set(self.country_ids.ids)
            orders = orders.filtered(lambda o: o.partner_id.country_id and o.partner_id.country_id.id in c_ids)

        # 3. Subscription Age / Date Range Filter
        today = fields.Date.today()
        if self.subscription_age == "new":
            limit_date = today - relativedelta(days=30)
            orders = orders.filtered(
                lambda o: (o.date_order and o.date_order.date() >= limit_date)
                or (o.create_date and o.create_date.date() >= limit_date)
            )
        elif self.subscription_age == "old":
            limit_date = today - relativedelta(days=30)
            orders = orders.filtered(
                lambda o: (o.date_order and o.date_order.date() < limit_date)
                or (o.create_date and o.create_date.date() < limit_date)
            )
        elif self.subscription_age == "custom":
            if self.date_from:
                orders = orders.filtered(
                    lambda o: (o.date_order and o.date_order.date() >= self.date_from)
                    or (o.create_date and o.create_date.date() >= self.date_from)
                )
            if self.date_to:
                orders = orders.filtered(
                    lambda o: (o.date_order and o.date_order.date() <= self.date_to)
                    or (o.create_date and o.create_date.date() <= self.date_to)
                )

        # 4. Price Min & Max Filter
        if self.price_min > 0.0:
            orders = orders.filtered(
                lambda o: (o.recurring_amount_total if "recurring_amount_total" in o._fields and o.recurring_amount_total else o.amount_total) >= self.price_min
            )
        if self.price_max > 0.0:
            orders = orders.filtered(
                lambda o: (o.recurring_amount_total if "recurring_amount_total" in o._fields and o.recurring_amount_total else o.amount_total) <= self.price_max
            )

        # 5. Contained Products Filter (Checks active non-removed subscription lines)
        if self.product_ids:
            selected_pids = set(self.product_ids.ids)
            selected_tmpl_ids = set(self.product_ids.mapped("product_tmpl_id").ids)

            def _get_order_products(order):
                lines = order._moyee_get_sub_lines() if hasattr(order, "_moyee_get_sub_lines") else order.order_line.filtered(lambda l: not getattr(l, "x_moyee_is_removed", False) and not l.display_type and l.product_id)
                pids = set()
                tmpl_ids = set()
                for l in lines:
                    if l.product_id:
                        pids.add(l.product_id.id)
                        if l.product_id.product_tmpl_id:
                            tmpl_ids.add(l.product_id.product_tmpl_id.id)
                return pids, tmpl_ids

            if self.product_filter_mode == "any":
                filtered_orders = SaleOrder.browse()
                for order in orders:
                    pids, tmpl_ids = _get_order_products(order)
                    if (pids & selected_pids) or (tmpl_ids & selected_tmpl_ids):
                        filtered_orders |= order
                orders = filtered_orders

            elif self.product_filter_mode == "all":
                filtered_orders = SaleOrder.browse()
                for order in orders:
                    pids, tmpl_ids = _get_order_products(order)
                    match_all = True
                    for sel_prod in self.product_ids:
                        if sel_prod.id not in pids and sel_prod.product_tmpl_id.id not in tmpl_ids:
                            match_all = False
                            break
                    if match_all:
                        filtered_orders |= order
                orders = filtered_orders

            elif self.product_filter_mode == "exclude":
                filtered_orders = SaleOrder.browse()
                for order in orders:
                    pids, tmpl_ids = _get_order_products(order)
                    if not ((pids & selected_pids) or (tmpl_ids & selected_tmpl_ids)):
                        filtered_orders |= order
                orders = filtered_orders

        self.subscription_ids = orders

        # Return view update action so wizard UI updates dynamically
        return {
            "name": _("Bulk Subscription Product Manager"),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    # ============================================================
    # Bulk Product Addition Action
    # ============================================================
    def action_bulk_add_product(self):
        """Add the chosen product in bulk to all filtered subscriptions."""
        self.ensure_one()

        if not self.add_product_id:
            raise UserError(_("Please select a product to add."))
        if self.add_qty <= 0.0:
            raise UserError(_("Quantity must be greater than zero."))
        if not self.subscription_ids:
            raise UserError(_("No subscriptions selected or found for bulk product addition."))

        OrderLine = self.env["sale.order.line"].sudo()
        product = self.add_product_id
        prod_name = product.display_name or product.name
        count = 0

        for order in self.subscription_ids:
            try:
                with self.env.cr.savepoint():
                    # Check if active line already exists for this product on this order
                    existing_line = order.order_line.filtered(
                        lambda l: not l.x_moyee_is_removed and not l.display_type and l.product_id and l.product_id.id == product.id
                    )

                    if existing_line:
                        # Update quantity on existing line
                        existing_line = existing_line[0]
                        new_qty = float(existing_line.product_uom_qty or 0.0) + self.add_qty
                        existing_line.write({
                            "product_uom_qty": new_qty,
                            "price_unit": self.add_price_unit if self.add_price_unit > 0.0 else existing_line.price_unit,
                        })
                    else:
                        # Create line description
                        line_name = prod_name
                        if hasattr(product, "get_product_multiline_description_sale"):
                            line_name = product.get_product_multiline_description_sale() or prod_name

                        # Create new order line
                        OrderLine.create({
                            "order_id": order.id,
                            "product_id": product.id,
                            "name": line_name,
                            "product_uom_qty": self.add_qty,
                            "price_unit": self.add_price_unit,
                        })

                    # Recompute order totals
                    order._compute_amounts()

                    # Auto recompute delivery shipping cost if applicable
                    if hasattr(order, "_moyee_auto_recompute_delivery"):
                        try:
                            order._moyee_auto_recompute_delivery()
                        except Exception as e:
                            _logger.warning("Bulk product add: delivery recompute failed for SO %s: %s", order.name, e)

                    # Log note in order chatter
                    order.message_post(
                        body=_("Moyee Bulk Operations: Added '%s' (Qty: %s, Price: %s) to subscription.") % (
                            prod_name,
                            self.add_qty,
                            self.add_price_unit,
                        ),
                        subtype_xmlid="mail.mt_note",
                    )
                    count += 1
            except Exception as e:
                _logger.exception("Bulk product add failed for subscription SO %s: %s", order.name, e)

        msg = _("Successfully added product '%s' to %d subscription(s).") % (prod_name, count)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bulk Addition Complete"),
                "message": msg,
                "type": "success",
                "sticky": False,
            },
        }

    # ============================================================
    # Bulk Product Soft-Removal Action
    # ============================================================
    def action_bulk_remove_product(self):
        """Soft-remove the chosen product in bulk from all filtered subscriptions."""
        self.ensure_one()

        if not self.remove_product_id:
            raise UserError(_("Please select a product to remove."))
        if not self.subscription_ids:
            raise UserError(_("No subscriptions selected or found for bulk product removal."))

        product = self.remove_product_id
        prod_name = product.display_name or product.name

        # Safety check: Prevent removing delivery products
        pname = prod_name.lower()
        if (
            getattr(product, "is_delivery", False)
            or getattr(product, "type", "") == "service"
            or getattr(product, "detailed_type", "") == "service"
            or any(kw in pname for kw in ("delivery", "shipping", "bezorg", "levering", "verzend", "transport", "postnl", "dhl", "ups"))
        ):
            raise UserError(_("Delivery products cannot be removed from subscriptions."))

        now = fields.Datetime.now()
        count = 0
        lines_removed_count = 0

        for order in self.subscription_ids:
            # Find active (non-removed) lines matching target product
            matching_lines = order.order_line.filtered(
                lambda l: not l.x_moyee_is_removed and not l.display_type and l.product_id and l.product_id.id == product.id
            )

            if not matching_lines:
                continue

            try:
                with self.env.cr.savepoint():
                    order_updated = False
                    for line in matching_lines:
                        vals = line._moyee_soft_remove_vals(self.env.user.id, reason=self.remove_reason, now=now)
                        line.write(vals)
                        order_updated = True
                        lines_removed_count += 1

                    if order_updated:
                        # Recompute order totals
                        order._compute_amounts()

                        # Auto recompute delivery cost if applicable
                        if hasattr(order, "_moyee_auto_recompute_delivery"):
                            try:
                                order._moyee_auto_recompute_delivery()
                            except Exception as e:
                                _logger.warning("Bulk product remove: delivery recompute failed for SO %s: %s", order.name, e)

                        # Log note in order chatter
                        order.message_post(
                            body=_(
                                "Moyee Bulk Operations: Soft-removed '%s' from subscription.\n"
                                "- By: %s\n"
                                "- When: %s\n"
                                "- Reason: %s"
                            ) % (
                                prod_name,
                                self.env.user.display_name,
                                fields.Datetime.to_string(now),
                                self.remove_reason or _("(bulk operation)"),
                            ),
                            subtype_xmlid="mail.mt_note",
                        )
                        count += 1
            except Exception as e:
                _logger.exception("Bulk product remove failed for subscription SO %s: %s", order.name, e)

        if count == 0:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Matching Products Found"),
                    "message": _("No active subscription lines found containing product '%s' among selected subscriptions.") % prod_name,
                    "type": "warning",
                    "sticky": False,
                },
            }

        msg = _("Successfully soft-removed product '%s' from %d subscription(s) (%d line(s) updated).") % (
            prod_name,
            count,
            lines_removed_count,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bulk Removal Complete"),
                "message": msg,
                "type": "success",
                "sticky": False,
            },
        }

