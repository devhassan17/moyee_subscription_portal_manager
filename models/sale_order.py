# File: moyee_subscription_portal_manager/models/sale_order.py
import logging
import re
import json
from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ============================================================
    # Computed helpers / fields
    # ============================================================
    is_subscription_order = fields.Boolean(
        string="Is Subscription Order",
        compute="_compute_is_subscription_order",
        store=False,
    )
    partner_country_id = fields.Many2one(
        comodel_name="res.country",
        related="partner_id.country_id",
        string="Country",
        store=False,
    )

    moyee_removed_line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="order_id",
        string="Removed Lines",
        domain=[("x_moyee_is_removed", "=", True)],
    )

    moyee_active_product_names = fields.Char(
        string="Active Products",
        compute="_compute_moyee_active_product_names",
        store=False,
    )

    # Max quantity a customer may set per line from the portal
    _MOYEE_PORTAL_MAX_QTY = 50

    def _compute_moyee_active_product_names(self):
        for order in self:
            sub_lines = order._moyee_get_sub_lines() if hasattr(order, "_moyee_get_sub_lines") else order.order_line.filtered(lambda l: not getattr(l, "x_moyee_is_removed", False) and not l.display_type and l.product_id)
            names = []
            for l in sub_lines:
                pname = l.product_id.display_name or l.product_id.name or l.name
                qty = int(l.product_uom_qty) if l.product_uom_qty.is_integer() else l.product_uom_qty
                names.append(f"{pname} (x{qty})")
            order.moyee_active_product_names = ", ".join(names) if names else "No active products"

    # ============================================================
    # Subscription detection (robust across Odoo builds)
    # ============================================================
    def _moyee_is_subscription_order(self):
        self.ensure_one()
        if "is_subscription" in self._fields:
            return bool(self.is_subscription)
        if "plan_id" in self._fields:
            return bool(self.plan_id)
        if "recurring_plan_id" in self._fields:
            return bool(self.recurring_plan_id)
        if "subscription_state" in self._fields:
            state_val = str(self.subscription_state or "").lower()
            return bool(state_val and state_val not in ("0", "false", "none", "draft", "cancel"))
        if "subscription_status" in self._fields:
            status_val = str(self.subscription_status or "").lower()
            return bool(status_val and status_val not in ("0", "false", "none", "draft", "cancel"))
        return False

    def _compute_is_subscription_order(self):
        for order in self:
            order.is_subscription_order = order._moyee_is_subscription_order()

    # ============================================================
    # Hide removed lines in invoices / reports / PDFs
    # ============================================================
    def _get_invoiceable_lines(self, final=False):
        # Keep Odoo/sale_subscription logic (qty_to_invoice, one-time vs recurring,
        # sections, down payments) and only drop soft-removed lines.
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda l: l.display_type or not l.x_moyee_is_removed)

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)
        for inv in invoices:
            to_remove = inv.invoice_line_ids.filtered(
                lambda il: il.sale_line_ids and all(sl.x_moyee_is_removed for sl in il.sale_line_ids)
            )
            if to_remove:
                to_remove.unlink()
        # Never leave empty draft invoices behind
        empty = invoices.filtered(
            lambda m: m.state == "draft" and not m.invoice_line_ids.filtered(lambda l: l.display_type == "product")
        )
        if empty:
            empty.unlink()
            invoices -= empty
        return invoices

    def _get_order_lines_to_report(self):
        try:
            lines = super()._get_order_lines_to_report()
        except AttributeError:
            # Some builds don't have this method
            lines = self.order_line
        return lines.filtered(
            lambda l: l.display_type or (not l.x_moyee_is_removed and float(l.product_uom_qty or 0.0) > 0.0)
        )

    def _moyee_get_sub_lines(self):
        """Return active, non-removed subscription product lines (excluding delivery, display, and company-hidden products)."""
        self.ensure_one()
        hidden_product_ids = set()
        if self.company_id and hasattr(self.company_id, "moyee_hidden_product_ids"):
            hidden_product_ids = set(self.company_id.moyee_hidden_product_ids.ids)
        return self.order_line.filtered(
            lambda l: not l.x_moyee_is_removed
            and not l.display_type
            and l.product_id
            and not l._moyee_is_delivery_line()
            and (not hidden_product_ids or l.product_id.id not in hidden_product_ids)
        )

    def _moyee_get_delivery_lines(self):
        """Return active, non-removed delivery lines."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: not l.x_moyee_is_removed and not l.display_type and l._moyee_is_delivery_line()
        )

    def _moyee_auto_recompute_delivery(self):
        """Recalculate the shipping cost when subscription lines change.
        Existing (possibly invoiced) delivery lines are updated in place to avoid the
        'already invoiced' error; otherwise Odoo's set_delivery_line() is used."""
        for order in self:
            carrier = getattr(order, 'carrier_id', False)
            if not carrier:
                continue
            try:
                with self.env.cr.savepoint():
                    res = carrier.rate_shipment(order)
                    if not res.get('success'):
                        continue
                    price_unit = float(res.get('price', 0.0))
                    delivery_lines = order._moyee_get_delivery_lines()
                    if delivery_lines:
                        delivery_lines.sudo().write({'price_unit': price_unit})
                    elif hasattr(order, 'set_delivery_line'):
                        order.sudo().set_delivery_line(carrier, price_unit)
                    if 'recompute_delivery_price' in order._fields:
                        order.sudo().write({'recompute_delivery_price': False})
            except Exception as e:
                _logger.warning("Moyee: Auto delivery recompute error on SO %s: %s", order.name, str(e))

    # ============================================================
    # Portal security helpers
    # ============================================================
    # Odoo 18 subscription states that must never be edited from the portal
    _MOYEE_BLOCKED_SUB_STATES = ("1_draft", "5_renewed", "6_churn", "7_upsell")

    def _moyee_portal_allowed_products(self):
        """Products a customer may add/switch to: portal-offered + already on the order."""
        self.ensure_one()
        hidden = set(self.company_id.moyee_hidden_product_ids.ids) if (
            self.company_id and hasattr(self.company_id, "moyee_hidden_product_ids")
        ) else set()
        products = self._moyee_get_portal_addable_products() | self._moyee_get_sub_lines().mapped("product_id")
        return products.filtered(lambda p: p.id not in hidden)

    def _moyee_validate_portal_qty(self, qty):
        try:
            qty = float(qty or 0.0)
        except (TypeError, ValueError):
            raise ValidationError(_("Invalid quantity."))
        if qty <= 0:
            raise ValidationError(_("Quantity must be greater than 0."))
        if not qty.is_integer():
            raise ValidationError(_("Quantity must be a whole number."))
        if qty > self._MOYEE_PORTAL_MAX_QTY:
            raise ValidationError(_("Quantity cannot exceed %s.") % self._MOYEE_PORTAL_MAX_QTY)
        return qty

    def _moyee_cancel_pending_moves(self, lines):
        """Cancel not-yet-done outgoing stock moves of the given lines (if stock is installed)."""
        if "stock.move" not in self.env or not lines:
            return
        moves = self.env["stock.move"].sudo().search([
            ("sale_line_id", "in", lines.ids),
            ("state", "not in", ("done", "cancel")),
            ("picking_code", "=", "outgoing"),
        ])
        if moves:
            moves._action_cancel()

    def _moyee_launch_stock_rule(self, lines):
        """Create/adjust deliveries for changed lines on confirmed orders (best effort)."""
        if self.state not in ("sale", "done"):
            return
        for line in lines.sudo():
            if not hasattr(line, "_action_launch_stock_rule"):
                return
            try:
                with self.env.cr.savepoint():
                    line._action_launch_stock_rule()
            except Exception:
                _logger.exception("Moyee: Failed to launch stock rule for line %s.", line.id)

    def _moyee_set_line_qty(self, line, qty):
        """
        Set qty on a subscription line. On subscriptions qty_delivered is cumulative
        over all periods, so Odoo's 'cannot decrease below delivered' rule would block
        any reduction. Try the ORM first; fall back to SQL when decreasing.
        """
        line = line.sudo()
        try:
            with self.env.cr.savepoint():
                line.write({"product_uom_qty": qty})
            return
        except UserError:
            if qty >= float(line.product_uom_qty or 0.0):
                raise
        self._moyee_cancel_pending_moves(line)
        self.env.cr.execute("UPDATE sale_order_line SET product_uom_qty = %s WHERE id = %s", (qty, line.id))
        line.invalidate_recordset(["product_uom_qty"])
        line.modified(["product_uom_qty"])

    def _moyee_portal_check_access(self, *, portal_user=None, access_token=None, require_subscription=True, check_state=True):
        self.ensure_one()
        portal_user = portal_user or self.env.user

        token_ok = bool(access_token and self.access_token and access_token == self.access_token)
        is_employee = self.env.user.has_group("base.group_user")

        # 1. Identity check (skipped for a valid share-token or employees)
        if not token_ok and not is_employee:
            if portal_user.id != self.env.user.id:
                raise AccessError(_("You cannot perform actions on behalf of another user."))
            if portal_user._is_public():
                raise AccessError(_("You must be logged in to manage subscriptions."))
            if self.partner_id.commercial_partner_id != portal_user.partner_id.commercial_partner_id:
                raise AccessError(_("You do not have access to this subscription."))

        # 2. Record checks - apply to token holders too
        if require_subscription and not self.is_subscription_order:
            raise AccessError(_("This record is not a subscription."))

        if not check_state or is_employee:
            return True

        if self.state not in ("sale", "done"):
            raise UserError(_("This subscription is not in a confirmed state."))

        # In your DB: subscription_state looks like "3_progress"
        if "subscription_state" in self._fields and self.subscription_state:
            state_val = str(self.subscription_state).lower()
            if (
                state_val in self._MOYEE_BLOCKED_SUB_STATES
                or state_val in ("closed", "cancel", "churned", "4_closed")
                or "closed" in state_val
                or "churn" in state_val
            ):
                raise UserError(_("This subscription is closed."))

        # If subscription_status exists in some builds, block closed ones
        if "subscription_status" in self._fields and self.subscription_status:
            if self.subscription_status in ("closed", "cancel", "churned"):
                raise UserError(_("This subscription is closed."))

        return True

    # ============================================================
    # Next date field resolver
    # ============================================================
    def _moyee_get_subscription_next_date_field_name(self):
        self.ensure_one()
        for fname in ("recurring_next_date", "next_invoice_date", "next_delivery_date", "x_next_delivery_date"):
            if fname in self._fields:
                return fname
        return False

    # ============================================================
    # Products allowed for portal add
    # ============================================================
    @api.model
    def _moyee_is_subscription_product(self, product):
        """
        Determine if a product is a subscription product.
        Checks for 'Subscription' (case-insensitive) in:
        1. eCommerce Tags (all_product_tag_ids / product_tag_ids / tag_ids)
        2. eCommerce Categories (public_categ_ids)
        3. subscription_ok / recurring_invoice boolean flags
        4. Product / Template name containing 'Subscription'
        """
        if not product:
            return False
        tmpl = getattr(product, "product_tmpl_id", product)

        # 1. Check boolean subscription flags if present
        if getattr(tmpl, "subscription_ok", False) or getattr(tmpl, "recurring_invoice", False):
            return True

        # 2. Check eCommerce & product tags (all_product_tag_ids, product_tag_ids, tag_ids)
        for fname in ("all_product_tag_ids", "product_tag_ids", "tag_ids"):
            if fname in tmpl._fields:
                tags = getattr(tmpl, fname, False)
                if tags and any("subscription" in (t.name or "").lower() for t in tags):
                    return True

        # 3. Check eCommerce public categories (public_categ_ids)
        if "public_categ_ids" in tmpl._fields:
            categs = getattr(tmpl, "public_categ_ids", False)
            if categs and any("subscription" in (c.name or "").lower() for c in categs):
                return True

        # 4. Fallback name check
        p_name = (getattr(product, "name", "") or getattr(tmpl, "name", "") or "").lower()
        if "subscription" in p_name:
            return True

        return False

    def _moyee_get_portal_addable_products(self):
        self.ensure_one()
        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()
        from odoo.osv import expression

        base_domain = [("sale_ok", "=", True)]
        if "company_id" in Product._fields and self.company_id:
            base_domain.append(("company_id", "in", [False, self.company_id.id]))

        # Physical products (consu/product)
        if "detailed_type" in Product._fields:
            base_domain.append(("detailed_type", "in", ["consu", "product"]))
        elif "type" in Product._fields:
            base_domain.append(("type", "in", ["consu", "product"]))

        # Build OR domain for Subscription tag / category / flag
        sub_domain_parts = []
        if "all_product_tag_ids" in Template._fields:
            sub_domain_parts.append([("product_tmpl_id.all_product_tag_ids.name", "ilike", "Subscription")])
        if "product_tag_ids" in Template._fields:
            sub_domain_parts.append([("product_tmpl_id.product_tag_ids.name", "ilike", "Subscription")])
        if "tag_ids" in Template._fields:
            sub_domain_parts.append([("product_tmpl_id.tag_ids.name", "ilike", "Subscription")])
        if "public_categ_ids" in Template._fields:
            sub_domain_parts.append([("product_tmpl_id.public_categ_ids.name", "ilike", "Subscription")])
        if "subscription_ok" in Template._fields:
            sub_domain_parts.append([("product_tmpl_id.subscription_ok", "=", True)])
        if "recurring_invoice" in Template._fields:
            sub_domain_parts.append([("product_tmpl_id.recurring_invoice", "=", True)])
        sub_domain_parts.append([("product_tmpl_id.name", "ilike", "Subscription")])

        if sub_domain_parts:
            sub_domain = expression.OR(sub_domain_parts)
            domain = expression.AND([base_domain, sub_domain])
        else:
            domain = base_domain

        products = Product.search(domain, order="name, id", limit=300)

        exclude_regex = re.compile(
            r"\b(onderhoud|service|maintenance|installatie|repair|reparatie|"
            r"schoonmaak|cleaning|reiniging|optie|support|delivery|shipping|"
            r"bezorg\w*|levering\w*|verzend\w*|transport\w*|postnl|dhl|ups|discount|promo|coupon)\b",
            re.IGNORECASE,
        )
        filtered_products = Product.browse()
        for p in products:
            if getattr(p, "is_delivery", False) or getattr(p.product_tmpl_id, "is_delivery", False):
                continue
            p_name = p.name or ""
            p_code = p.default_code or ""
            if exclude_regex.search(p_name) or exclude_regex.search(p_code):
                continue
            if self._moyee_is_subscription_product(p):
                filtered_products += p

        # Fallback if no products matched the strict subscription tag/flag domain:
        if not filtered_products:
            fallback_products = Product.search(base_domain, order="name, id", limit=300)
            for p in fallback_products:
                if getattr(p, "is_delivery", False) or getattr(p.product_tmpl_id, "is_delivery", False):
                    continue
                p_name = p.name or ""
                p_code = p.default_code or ""
                if exclude_regex.search(p_name) or exclude_regex.search(p_code):
                    continue
                filtered_products += p

        return filtered_products

    @api.model
    def moyee_extract_product_metadata(self, product=None):
        """
        Extract Grind and Weight from product attributes or name.
        Returns (grind, weight)
        """
        if not product:
            return "other", "other"

        # Always check product in base en_US context first for deterministic attribute matching
        product_en = product.sudo().with_context(lang='en_US')

        grind = "other"
        weight = "other"

        def _get_attr_values(prod_rec):
            avs = getattr(prod_rec, "product_template_attribute_value_ids", False)
            if not avs and hasattr(prod_rec, "product_variant_combination"):
                avs = prod_rec.product_variant_combination
            return avs or []

        # Helper to check attributes on product variant record
        def _scan_attributes(prod_rec):
            nonlocal grind, weight
            attr_values = _get_attr_values(prod_rec)
            if attr_values:
                for av in attr_values:
                    if grind != "other":
                        break
                    attr_name = (av.attribute_id.name or "").lower()
                    val_name_raw = getattr(av, "product_attribute_value_id", False) and av.product_attribute_value_id.name or av.name or ""
                    val_name = val_name_raw.lower()

                    is_grind_attr = any(kw in attr_name for kw in ("grind", "maling", "mahlgrad", "mahlung", "brew", "zubereitung", "hoe zet je", "how do you brew", "type", "koffie", "zetwijze"))
                    if is_grind_attr or any(kw in val_name for kw in ("whole", "boon", "bonen", "bohn", "ganz", "filter", "gemahlen", "snelfilter", "espresso", "capsule", "kapsel", "cup")):
                        if any(kw in val_name for kw in ("capsule", "kapsel", "cup")):
                            grind = "capsules"
                        elif any(kw in val_name for kw in ("whole", "boon", "bonen", "bohn", "bonen", "ganz", "ganze", "bean", "beans", "unground")):
                            grind = "whole"
                        elif any(kw in val_name for kw in ("espresso", "espressomaling", "espressomahlung")):
                            grind = "espresso"
                        elif any(kw in val_name for kw in ("filter", "gemahlen", "snelfilter", "filtermaling", "filtermahlung")):
                            grind = "filter"

                for av in attr_values:
                    if weight != "other":
                        break
                    attr_name = (av.attribute_id.name or "").lower()
                    val_name_raw = getattr(av, "product_attribute_value_id", False) and av.product_attribute_value_id.name or av.name or ""
                    val_name = val_name_raw.lower()
                    v_clean = val_name.replace(" ", "")

                    is_weight_attr = any(kw in attr_name for kw in ("weight", "size", "gewicht", "inhoud"))
                    if is_weight_attr or any(kw in v_clean for kw in ("1kg", "250g", "25caps", "kapsel")):
                        if any(kw in v_clean for kw in ("capsules", "capsule", "kapsel", "kapseln", "cups", "25caps")):
                            weight = "25caps"
                        elif any(kw in v_clean for kw in ("1kg", "1.0kg", "1000g", "1000 g")):
                            weight = "1kg"
                        elif any(kw in v_clean for kw in ("250g", "250gram", "250gramm", "0.25kg")) or "250" in v_clean:
                            weight = "250g"

        # 1. Try en_US context first, then native context if needed
        _scan_attributes(product_en)
        if grind == "other" or weight == "other":
            _scan_attributes(product)

        # 2. Fallback to name/code scanning if still 'other'
        names_to_check = [
            (getattr(product_en, "display_name", "") or getattr(product_en, "name", "") or "").lower(),
            (getattr(product, "display_name", "") or getattr(product, "name", "") or "").lower(),
            (getattr(product, "default_code", "") or "").lower(),
        ]
        for name in names_to_check:
            if not name:
                continue
            if grind == "other":
                if any(kw in name for kw in ("capsule", "kapsel", "cup")):
                    grind = "capsules"
                elif any(kw in name for kw in ("whole", "boon", "bonen", "bohn", "bonen", "ganz", "ganze", "bean", "beans", "unground")):
                    grind = "whole"
                elif any(kw in name for kw in ("espresso grind", "espressogrind", "espressomahlung", "espressomaling", "espresso")):
                    grind = "espresso"
                elif any(kw in name for kw in ("filter grind", "filtergrind", "filtermahlung", "filtermaling", "snelfilter", "filter")):
                    grind = "filter"

            if weight == "other":
                name_clean = name.replace(" ", "")
                if any(kw in name_clean for kw in ("capsule", "kapsel", "cups", "25caps", "25capsule", "25cups")):
                    weight = "25caps"
                elif any(kw in name_clean for kw in ("1kg", "1000g", "1.0kg")):
                    weight = "1kg"
                elif any(kw in name_clean for kw in ("250g", "0.25kg", "250")):
                    weight = "250g"

        if grind == "other":
            grind = "whole"  # Default fallback for coffee products
        if weight == "other":
            weight = "1kg"  # Default fallback

        return grind, weight

    @api.model
    def moyee_extract_coffee_characteristics(self, product=None):
        """
        Extract 'How Bold?' and 'Full or Fruity?' attributes.
        Returns (bold, fruity)
        Possible bold values: 'light', 'medium', 'bold', 'other'
        Possible fruity values: 'full', 'fruity', 'other'
        """
        if not product:
            return "other", "other"

        bold = "other"
        fruity = "other"

        # 1. Check variant attributes
        attr_values = getattr(product, "product_template_attribute_value_ids", False)
        if attr_values:
            for av in attr_values:
                attr_name = (av.attribute_id.name or "").lower()
                val_name = (av.name or "").lower()

                if "bold" in attr_name or "sterkte" in attr_name or "how bold" in attr_name or "strength" in attr_name:
                    if "light" in val_name or "mild" in val_name:
                        bold = "light"
                    elif "medium" in val_name:
                        bold = "medium"
                    elif "bold" in val_name or "donker" in val_name or "intens" in val_name or "dark" in val_name:
                        bold = "bold"

                if "fruity" in attr_name or "fruity?" in attr_name or "vol of fruitig" in attr_name or "full or fruity" in attr_name or "smaak" in attr_name or "flavor" in attr_name:
                    if "full" in val_name or "vol" in val_name:
                        fruity = "full"
                    elif "fruity" in val_name or "fruitig" in val_name:
                        fruity = "fruity"

        # 2. Check template attribute lines if still 'other'
        tmpl = getattr(product, "product_tmpl_id", False)
        if tmpl and (bold == "other" or fruity == "other"):
            for line in getattr(tmpl, "attribute_line_ids", []):
                attr_name = (line.attribute_id.name or "").lower()
                val_names = [v.name.lower() for v in line.value_ids if v.name]

                if bold == "other" and ("bold" in attr_name or "sterkte" in attr_name or "how bold" in attr_name or "strength" in attr_name):
                    for val_name in val_names:
                        if "light" in val_name or "mild" in val_name:
                            bold = "light"
                            break
                        elif "medium" in val_name:
                            bold = "medium"
                            break
                        elif "bold" in val_name or "donker" in val_name or "intens" in val_name or "dark" in val_name:
                            bold = "bold"
                            break

                if fruity == "other" and ("fruity" in attr_name or "fruity?" in attr_name or "vol of fruitig" in attr_name or "full or fruity" in attr_name or "smaak" in attr_name or "flavor" in attr_name):
                    for val_name in val_names:
                        if "full" in val_name or "vol" in val_name:
                            fruity = "full"
                            break
                        elif "fruity" in val_name or "fruitig" in val_name:
                            fruity = "fruity"
                            break

        # 3. Fallback to product name scan if still 'other'
        name = (getattr(product, "name", "") or getattr(product, "display_name", "") or "").lower()
        if bold == "other":
            if "light" in name or "mild" in name:
                bold = "light"
            elif "medium" in name:
                bold = "medium"
            elif "bold" in name or "intens" in name or "dark" in name or "donker" in name:
                bold = "bold"

        if fruity == "other":
            if "full" in name or "vol" in name:
                fruity = "full"
            elif "fruity" in name or "fruitig" in name:
                fruity = "fruity"

        return bold, fruity

    # ============================================================
    # ✅ UNIVERSAL: Plan field + plan model resolver (FIXED)
    # ============================================================
    def _moyee_get_recurring_plan_field_name(self):
        """
        Detect which field on sale.order holds the plan/pricing.

        ✅ Your DB uses: plan_id (sale.subscription.plan)
        """
        self.ensure_one()
        for fname in (
            "plan_id",  # ✅ IMPORTANT (your DB)
            # other builds / customizations:
            "recurring_plan_id",
            "subscription_pricing_id",
            "subscription_plan_id",
            "recurring_pricing_id",
        ):
            if fname in self._fields:
                return fname
        return False

    def _moyee_get_current_plan_record(self):
        self.ensure_one()
        plan_field = self._moyee_get_recurring_plan_field_name()
        if not plan_field:
            return False
        return self[plan_field]

    def _moyee_get_plan_model(self):
        self.ensure_one()
        plan_field = self._moyee_get_recurring_plan_field_name()
        if not plan_field:
            return False, self.env["ir.model"].browse([])
        comodel = self._fields[plan_field].comodel_name
        return plan_field, self.env[comodel].sudo()

    # ============================================================
    # ✅ Interval/Plan list for portal (works with plan_id)
    # ============================================================
    def _moyee_get_portal_changeable_plans(self):
        """
        Return plans customer can choose from.

        ✅ Works with plan_id (sale.subscription.plan) in your DB
        Only ACTIVE plans of the order's company (or shared plans) are offered.
        """
        self.ensure_one()

        plan_field, Plan = self._moyee_get_plan_model()
        if not plan_field:
            return self.env["ir.model"].browse([])

        current_plan = self[plan_field]
        if current_plan:
            # Optional plans feature: different field names across builds
            for fname in (
                "optional_plans",
                "optional_plan_ids",
                "optional_recurring_plan_ids",
                "optional_recurring_plans",
            ):
                if fname in current_plan._fields:
                    optional = current_plan[fname].sudo()
                    if "active" in optional._fields:
                        optional = optional.filtered("active")
                    if optional:
                        return optional | current_plan.sudo()

        # Fallback: active plans of the order company + shared plans
        domain = []
        if "company_id" in Plan._fields and self.company_id:
            domain = [("company_id", "in", [False, self.company_id.id])]

        order_by = "sequence, name, id" if "sequence" in Plan._fields else "name, id"
        return Plan.search(domain, order=order_by)

    # ============================================================
    # ✅ Change interval (write to correct field)
    # ============================================================
    def moyee_portal_change_interval(self, *, portal_user_id, plan_id, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        plan_field = self._moyee_get_recurring_plan_field_name()
        if not plan_field:
            raise UserError(_("This subscription does not support interval change."))

        plan_id = int(plan_id or 0)
        if not plan_id:
            raise ValidationError(_("Please select an interval."))

        allowed_plans = self._moyee_get_portal_changeable_plans()
        if not allowed_plans.filtered(lambda p: p.id == plan_id):
            raise AccessError(_("Selected interval is not allowed."))

        # ✅ Write to correct field name used by this DB (plan_id)
        old_plan = self[plan_field]
        self.sudo().write({plan_field: plan_id})

        # Prices depend on the plan (pricelist rules per plan) -> recompute them
        if old_plan.id != plan_id:
            for line in self._moyee_get_sub_lines():
                self._moyee_recompute_line_price(line)
            self._moyee_auto_recompute_delivery()

        self.sudo().message_post(
            body=_("Moyee: customer changed subscription interval via portal (%s → %s).") % (
                old_plan.display_name or "-", self[plan_field].display_name
            ),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # ✅ Pause / Resume (robust)
    # ============================================================
    def _moyee_set_subscription_paused_state(self, paused=True):
        self.ensure_one()

        # ✅ 1) PRIORITY: Direct subscription_state field write (Odoo 18 Enterprise)
        #    Odoo 18 uses: 3_progress (active), 4_paused (paused)
        if "subscription_state" in self._fields:
            current = self.subscription_state or ""
            if paused and current != "4_paused":
                self.sudo().write({"subscription_state": "4_paused"})
                return True
            elif not paused and current == "4_paused":
                self.sudo().write({"subscription_state": "3_progress"})
                return True
            elif paused and current == "4_paused":
                return True  # already paused
            elif not paused and current != "4_paused":
                return True  # already active

        # 2) method-based fallback (other Odoo builds)
        if paused:
            for m in ("action_pause", "action_suspend", "action_subscription_pause", "action_set_to_pause"):
                if hasattr(self, m):
                    getattr(self.sudo(), m)()
                    return True
        else:
            for m in ("action_resume", "action_reactivate", "action_subscription_resume", "action_set_to_progress"):
                if hasattr(self, m):
                    getattr(self.sudo(), m)()
                    return True

        # 3) stage-based fallback
        for stage_field in ("subscription_stage_id", "stage_id"):
            if stage_field in self._fields:
                Stage = self.env[self._fields[stage_field].comodel_name].sudo()

                if paused:
                    target = (
                        Stage.search([("name", "ilike", "pause")], limit=1)
                        or Stage.search([("name", "ilike", "suspend")], limit=1)
                        or Stage.search([("name", "ilike", "hold")], limit=1)
                    )
                else:
                    target = (
                        Stage.search([("name", "ilike", "progress")], limit=1)
                        or Stage.search([("name", "ilike", "in progress")], limit=1)
                        or Stage.search([("name", "ilike", "running")], limit=1)
                        or Stage.search([("name", "ilike", "active")], limit=1)
                    )

                if target:
                    self.sudo().write({stage_field: target.id})
                    return True

        # 4) generic selection field fallback
        def _set_selection(field_name):
            if field_name not in self._fields:
                return False
            selection = self._fields[field_name].selection or []
            keys = [k for k, _lbl in selection]

            def _pick(candidates):
                for cand in candidates:
                    for k in keys:
                        if k == cand:
                            return k
                for cand in candidates:
                    for k in keys:
                        if cand in str(k).lower():
                            return k
                return None

            if paused:
                key = _pick(("4_paused", "paused", "pause", "suspended", "suspend", "hold"))
            else:
                key = _pick(("3_progress", "in_progress", "progress", "running", "active", "open"))

            if key:
                self.sudo().write({field_name: key})
                return True
            return False

        if _set_selection("subscription_status"):
            return True

        raise UserError(_("Pause/resume is not available for this subscription implementation."))

    def moyee_portal_pause(self, *, portal_user_id, pause_until_date=None, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)
        self._moyee_set_subscription_paused_state(paused=True)

        if pause_until_date:
            field_name = self._moyee_get_subscription_next_date_field_name()
            if field_name:
                try:
                    target_date = fields.Date.from_string(pause_until_date)
                    if target_date and target_date > fields.Date.today():
                        self.sudo().write({field_name: target_date})
                except Exception:
                    pass

        self.sudo().message_post(
            body=_("Moyee: customer paused the subscription via portal.") + (
                _(" Target resume date: %s") % pause_until_date if pause_until_date else ""
            ),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # ✅ Skip delivery (portal)
    # ============================================================
    def moyee_portal_skip_delivery(self, *, portal_user_id, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        if "subscription_state" in self._fields and self.subscription_state == "4_paused":
            raise UserError(_("You cannot skip a delivery while the subscription is paused."))

        field_name = self._moyee_get_subscription_next_date_field_name()
        if not field_name:
            raise UserError(_("This subscription does not expose a next date field."))

        current_date = self[field_name] or fields.Date.today()
        if current_date > fields.Date.today() + relativedelta(months=6):
            raise UserError(_("Your next delivery is already more than 6 months ahead. Please pause the subscription instead."))
        
        # Calculate interval to skip
        plan = self._moyee_get_current_plan_record()
        months = 1  # default fallback
        weeks = 0
        days = 0

        if plan:
            if "billing_period_value" in plan._fields and "billing_period_unit" in plan._fields:
                val = plan.billing_period_value or 1
                unit = plan.billing_period_unit
                if unit == "month":
                    months = val
                elif unit == "week":
                    weeks = val
                    months = 0
                elif unit == "year":
                    months = val * 12
                elif unit == "day":
                    days = val
                    months = 0
            else:
                pname = (plan.display_name or plan.name or "").lower()
                if "2 weeks" in pname:
                    weeks = 2
                    months = 0
                elif "week" in pname:
                    weeks = 1
                    months = 0
                elif "2 months" in pname:
                    months = 2
                elif "3 months" in pname:
                    months = 3
                elif "6 months" in pname:
                    months = 6
                elif "month" in pname:
                    months = 1
                elif "year" in pname:
                    months = 12

        new_date = current_date + relativedelta(months=months, weeks=weeks, days=days)

        self.sudo().write({field_name: new_date})
        self.sudo().message_post(
            body=_("Moyee: customer skipped next delivery via portal. Next date: %s") % new_date,
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def moyee_portal_resume(self, *, portal_user_id, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)
        self._moyee_set_subscription_paused_state(paused=False)

        # Avoid an immediate catch-up renewal when the stored next date is in the past
        field_name = self._moyee_get_subscription_next_date_field_name()
        if field_name and (not self[field_name] or self[field_name] < fields.Date.today()):
            self.sudo().write({field_name: fields.Date.today()})

        self.sudo().message_post(
            body=_("Moyee: customer resumed the subscription via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # ✅ Cancel / Close (robust)
    # ============================================================
    def _moyee_set_subscription_closed_state(self, reason=None):
        """Close the subscription through Odoo's own flow (set_close), which takes care of
        end date, churn/MRR logs and close reason. Never cancels the sale order.
        Returns the close reason record (or False)."""
        self.ensure_one()

        close_reason = False
        if "close_reason_id" in self._fields and reason:
            CloseReason = self.env[self._fields["close_reason_id"].comodel_name].sudo()
            reason_str = str(reason).strip()
            if reason_str.isdigit():
                close_reason = CloseReason.browse(int(reason_str)).exists()
            if not close_reason:
                close_reason = CloseReason.search([("name", "=ilike", reason_str)], limit=1)

        order = self.sudo()
        if hasattr(order, "set_close"):
            try:
                order.set_close(close_reason_id=close_reason.id if close_reason else None)
            except TypeError:
                # Older signature without close_reason_id
                if close_reason:
                    order.write({"close_reason_id": close_reason.id})
                order.set_close()
            return close_reason

        if "subscription_state" in order._fields:
            vals = {"subscription_state": "6_churn"}
            if close_reason:
                vals["close_reason_id"] = close_reason.id
            order.write(vals)
            return close_reason

        raise UserError(_("Close/cancel is not available for this subscription implementation."))

    def moyee_portal_close(self, *, portal_user_id, reason=None, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)
        close_reason = self._moyee_set_subscription_closed_state(reason=reason)

        reason_label = close_reason.display_name if close_reason else (reason or "")
        body_msg = Markup("%s") % _("Moyee: customer cancelled/closed the subscription via portal.")
        if reason_label:
            body_msg += Markup("<br/>") + (_("Reason: %s") % reason_label)

        self.sudo().message_post(
            body=body_msg,
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True


    # ============================================================
    # Push next date (portal)
    # ============================================================
    def moyee_portal_push_next_date(self, *, portal_user_id, next_date, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        field_name = self._moyee_get_subscription_next_date_field_name()
        if not field_name:
            raise UserError(_("This subscription does not expose a next date field."))

        try:
            value = fields.Date.from_string(next_date)
        except Exception:
            raise ValidationError(_("Invalid date."))

        if not value:
            raise ValidationError(_("Please select a date."))

        if value < fields.Date.today():
            raise ValidationError(_("The next delivery date cannot be in the past."))
        if value > fields.Date.today() + relativedelta(months=6):
            raise ValidationError(_("The next delivery date cannot be more than 6 months ahead. Please pause the subscription instead."))

        self.sudo().write({field_name: value})
        self.sudo().message_post(
            body=_("Moyee: customer updated next date via portal (%s).") % field_name,
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def _moyee_recompute_line_price(self, line):
        """
        Recalculates and updates the price_unit on a subscription line
        based on the order's pricelist, quantity, and product.
        """
        if not line:
            return
        line = line.sudo()

        # 1. First, try executing standard Odoo compute methods
        if hasattr(line, "_compute_pricelist_item_id"):
            try:
                line._compute_pricelist_item_id()
            except Exception as e:
                _logger.debug("Moyee: _compute_pricelist_item_id failed: %s", str(e))
        if hasattr(line, "_compute_price_unit"):
            try:
                line._compute_price_unit()
            except Exception as e:
                _logger.debug("Moyee: _compute_price_unit failed: %s", str(e))

        # 2. Try fetching the display price (either with or without product arg)
        price = 0.0
        if hasattr(line, "_get_display_price"):
            try:
                price = line._get_display_price()
            except TypeError:
                try:
                    price = line._get_display_price(line.product_id)
                except Exception as e:
                    _logger.debug("Moyee: _get_display_price(product) failed: %s", str(e))
            except Exception as e:
                _logger.debug("Moyee: _get_display_price() failed: %s", str(e))

        # 3. Fallback to manual pricelist lookup
        if not price and line.order_id.pricelist_id:
            try:
                pricelist = line.order_id.pricelist_id
                product = line.product_id
                qty = line.product_uom_qty or 1.0
                partner = line.order_id.partner_id
                uom_id = (line.product_uom or product.uom_id).id

                if hasattr(pricelist, "_get_product_price"):
                    price = pricelist._get_product_price(product, qty, partner, uom_id=uom_id)
                elif hasattr(pricelist, "get_product_price"):
                    price = pricelist.get_product_price(product, qty, partner, uom_id=uom_id)
            except Exception as e:
                _logger.debug("Moyee: Pricelist lookup failed: %s", str(e))

        # 4. Fallback to product's list price
        if not price and line.product_id:
            price = getattr(line.product_id, "lst_price", 0.0) or getattr(line.product_id, "list_price", 0.0)

        # NOTE: no extra _fix_tax_included_price_company() here: _get_display_price()
        # already returns the correctly tax-adjusted price; applying it again would
        # double-convert tax-included prices.

        if not price or float(price) <= 0.0:
            raise ValidationError(_("The product '%s' does not have a valid price configured. Action aborted.") % line.product_id.display_name)

        line.write({"price_unit": price})

    # ============================================================
    # Add product (portal)
    # ============================================================
    def moyee_portal_add_product(self, *, portal_user_id, product_id, qty=1.0, mode="add", access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        product = self.env["product.product"].sudo().browse(int(product_id)).exists()
        if not product:
            raise ValidationError(_("Invalid product."))
        if product not in self._moyee_portal_allowed_products():
            raise AccessError(_("This product cannot be added to your subscription."))

        qty = self._moyee_validate_portal_qty(qty)

        existing_line = self.order_line.filtered(
            lambda l: (not l.display_type) and l.product_id.id == product.id
        )
        if existing_line:
            line_to_update = existing_line[:1].sudo()
            if line_to_update.x_moyee_is_removed:
                line_to_update.write({
                    "x_moyee_is_removed": False,
                    "x_moyee_removed_on": False,
                    "x_moyee_removed_by": False,
                    "x_moyee_remove_reason": False,
                })
                self._moyee_set_line_qty(line_to_update, qty)
            else:
                new_qty = qty if mode == "set" else float(line_to_update.product_uom_qty or 0.0) + qty
                if new_qty > self._MOYEE_PORTAL_MAX_QTY:
                    raise ValidationError(_("Quantity cannot exceed %s.") % self._MOYEE_PORTAL_MAX_QTY)
                self._moyee_set_line_qty(line_to_update, new_qty)
            self._moyee_recompute_line_price(line_to_update)
            self._moyee_launch_stock_rule(line_to_update)
        else:
            sibling = self.order_line.filtered(lambda l: not l.display_type and not l.x_moyee_is_removed)
            vals = {
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "name": product.with_context(display_default_code=False).display_name or product.display_name,
                "product_uom": product.uom_id.id,
            }
            if sibling:
                sibling_line = sibling[0]
                for fname in ("temporal_type", "pricing_id", "pricing_template_id", "billing_cycle"):
                    if fname in sibling_line._fields:
                        val = sibling_line[fname]
                        vals[fname] = val.id if hasattr(val, "id") else val
            new_line = self.env["sale.order.line"].sudo().create(vals)
            self._moyee_recompute_line_price(new_line)
            self._moyee_launch_stock_rule(new_line)

        # Automatically recalculate delivery cost for updated order weight
        self._moyee_auto_recompute_delivery()

        self.sudo().message_post(
            body=_("Moyee: customer updated product via portal (%s x %s).") % (product.display_name, qty),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def _moyee_partner_is_shared(self, partner):
        """True if the partner is referenced by other orders, posted invoices or pickings,
        i.e. editing it in place would rewrite history / other subscriptions."""
        self.ensure_one()
        pid = partner.id
        if self.env["sale.order"].sudo().search_count([
            "|", "|",
            ("partner_id", "=", pid),
            ("partner_shipping_id", "=", pid),
            ("partner_invoice_id", "=", pid),
            ("id", "!=", self.id),
        ], limit=1):
            return True
        if self.env["account.move"].sudo().search_count([
            ("partner_id", "=", pid), ("state", "=", "posted"),
        ], limit=1):
            return True
        if "stock.picking" in self.env and self.env["stock.picking"].sudo().search_count([
            ("partner_id", "=", pid),
        ], limit=1):
            return True
        return False

    def _moyee_portal_upsert_child_address(self, portal_user, vals, addr_type):
        """Return a child address of the customer for this order.
        Never touches the commercial partner and never edits an address that is
        shared with other documents: a new child address is created instead."""
        self.ensure_one()
        commercial = portal_user.partner_id.commercial_partner_id

        vals = vals or {}
        if not any(vals.get(k) for k in ("street", "city", "zip")):
            return False
        # Keep empty strings as False so customers can clear a field (e.g. street2)
        clean = {k: (v or False) for k, v in vals.items()}

        current = self.partner_shipping_id if addr_type == "delivery" else self.partner_invoice_id
        reusable = (
            current
            and current != commercial
            and current.parent_id == commercial
            and current.type == addr_type
            and not self._moyee_partner_is_shared(current)
        )
        if reusable:
            current.sudo().write(clean)
            return current

        clean.update({"parent_id": commercial.id, "type": addr_type})
        return self.env["res.partner"].sudo().create(clean)

    def moyee_portal_change_address_full(self, *, portal_user_id, shipping_vals=None, invoice_vals=None, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        ship_partner = self._moyee_portal_upsert_child_address(portal_user, shipping_vals, "delivery")
        inv_partner = self._moyee_portal_upsert_child_address(portal_user, invoice_vals, "invoice")

        vals = {}
        if ship_partner:
            vals["partner_shipping_id"] = ship_partner.id
        if inv_partner:
            vals["partner_invoice_id"] = inv_partner.id

        if not vals:
            raise UserError(_("Please fill at least one address field."))

        self.sudo().write(vals)
        self.sudo().message_post(
            body=_("Moyee: customer updated full addresses via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # Update line quantity (portal)
    # ============================================================
    def moyee_portal_update_line_qty(self, *, portal_user_id, line_id, qty, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        line = self.env["sale.order.line"].sudo().browse(int(line_id)).exists()
        if not line or line.order_id.id != self.id:
            raise ValidationError(_("Invalid subscription line."))

        if line.display_type or line.x_moyee_is_removed:
            raise UserError(_("This line cannot be updated."))

        qty = self._moyee_validate_portal_qty(qty)

        old_qty = line.product_uom_qty
        line_to_update = line.sudo()
        # NOTE: no 'qty >= qty_delivered' rule - on subscriptions qty_delivered is
        # cumulative over all periods, so it would block every reduction.
        self._moyee_set_line_qty(line_to_update, qty)
        self._moyee_recompute_line_price(line_to_update)
        if qty > old_qty:
            self._moyee_launch_stock_rule(line_to_update)

        # Automatically recalculate delivery cost for updated order weight
        self._moyee_auto_recompute_delivery()

        product_label = line.product_id.display_name if line.product_id else (line.name or _("(no product)"))
        self.sudo().message_post(
            body=_("Moyee: customer changed quantity via portal — %s: %s → %s.") % (
                product_label, old_qty, qty
            ),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def action_open_delivery_wizard(self):
        self.ensure_one()
        if self._moyee_is_subscription_order():
            has_invoiced_delivery = any(
                l._moyee_is_delivery_line() and float(l.qty_invoiced or 0.0) > 0.0
                for l in self.order_line
            )
            if has_invoiced_delivery:
                self._moyee_auto_recompute_delivery()
                return True
        try:
            return super().action_open_delivery_wizard()
        except UserError as e:
            if "already invoiced" in str(e).lower() and self._moyee_is_subscription_order():
                self._moyee_auto_recompute_delivery()
                return True
            raise

    # ============================================================
    # Edit line product (portal)
    # ============================================================
    def moyee_portal_edit_line_product(self, *, portal_user_id, line_id, template_id, grind, weight, qty=None, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)

        line = self.env["sale.order.line"].sudo().browse(int(line_id)).exists()
        if not line or line.order_id.id != self.id:
            raise ValidationError(_("Invalid subscription line."))

        if line.display_type or line.x_moyee_is_removed:
            raise UserError(_("This line cannot be edited."))

        template = self.env["product.template"].sudo().browse(int(template_id)).exists()
        if not template:
            raise ValidationError(_("Invalid coffee type selected."))
        if template not in self._moyee_portal_allowed_products().mapped("product_tmpl_id"):
            raise AccessError(_("This coffee cannot be selected for your subscription."))

        variants = self.env["product.product"].sudo().search([
            ("product_tmpl_id", "=", template.id),
            ("sale_ok", "=", True),
        ])

        if not weight and variants:
            _, t_weight = self.moyee_extract_product_metadata(variants[0])
            weight = t_weight

        target_product = False
        for var in variants:
            v_grind, v_weight = self.moyee_extract_product_metadata(var)
            if v_grind == grind and v_weight == weight:
                target_product = var
                break

        if not target_product:
            raise ValidationError(
                _("The selected combination of %s (%s, %s) is not available.") % (template.name, grind, weight)
            )

        new_qty = None
        if qty not in (None, ""):
            new_qty = self._moyee_validate_portal_qty(qty)

        old_product = line.product_id
        if old_product.id != target_product.id:
            # Check if target product is already on another subscription line (to merge)
            existing_line = self.order_line.filtered(
                lambda l: (not l.display_type) and l.product_id.id == target_product.id and not l.x_moyee_is_removed and l.id != line.id
            )
            if existing_line:
                existing_line_sudo = existing_line[:1].sudo()
                add_qty = new_qty if new_qty is not None else line.product_uom_qty
                merged_qty = existing_line_sudo.product_uom_qty + add_qty
                if merged_qty > self._MOYEE_PORTAL_MAX_QTY:
                    raise ValidationError(_("Quantity cannot exceed %s.") % self._MOYEE_PORTAL_MAX_QTY)
                self._moyee_set_line_qty(existing_line_sudo, merged_qty)
                line.sudo().write(line._moyee_soft_remove_vals(
                    portal_user.id, reason=_("Merged into another line via portal edit.")
                ))
                line.sudo()._moyee_force_zero_qty()
                self._moyee_recompute_line_price(existing_line_sudo)
                self._moyee_launch_stock_rule(existing_line_sudo)
            else:
                line_sudo = line.sudo()
                # Pending deliveries were created for the OLD product: cancel them
                # so the warehouse does not ship the wrong coffee.
                self._moyee_cancel_pending_moves(line_sudo)
                line_sudo.write({
                    "product_id": target_product.id,
                    "name": target_product.with_context(display_default_code=False).display_name or target_product.display_name,
                    "product_uom": target_product.uom_id.id,
                })
                if new_qty is not None:
                    self._moyee_set_line_qty(line_sudo, new_qty)
                self._moyee_recompute_line_price(line_sudo)
                self._moyee_launch_stock_rule(line_sudo)
        else:
            # Same product, update quantity if changed
            if new_qty is not None and new_qty != line.product_uom_qty:
                line_sudo = line.sudo()
                increased = new_qty > line_sudo.product_uom_qty
                self._moyee_set_line_qty(line_sudo, new_qty)
                self._moyee_recompute_line_price(line_sudo)
                if increased:
                    self._moyee_launch_stock_rule(line_sudo)

        self._moyee_auto_recompute_delivery()

        self.sudo().message_post(
            body=_("Moyee: customer edited line product via portal — %s → %s.") % (
                old_product.display_name, target_product.display_name
            ),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # Tracking Link Resolver (Monta Integration Safe)
    # ============================================================
    def _moyee_get_tracking_url(self):
        self.ensure_one()
        # 1. Look at associated pickings (standard delivery carrier setups + custom Monta fields)
        if "picking_ids" in self._fields:
            for picking in self.picking_ids:
                # Prioritize Monta Odoo Integration custom field: monta_track_trace
                if "monta_track_trace" in picking._fields and picking.monta_track_trace:
                    return picking.monta_track_trace
                # Fallback to standard Odoo delivery carrier tracking URL
                if "carrier_tracking_url" in picking._fields and picking.carrier_tracking_url:
                    return picking.carrier_tracking_url
        # 2. Look at custom database fields on sale.order itself
        for fname in ("postnl_track_trace_url", "x_monta_tracking_url", "x_tracking_url", "x_track_trace", "carrier_tracking_url", "monta_track_trace"):
            if fname in self._fields and getattr(self, fname, False):
                return getattr(self, fname)
        return False

    def _moyee_get_tracking_ref(self):
        self.ensure_one()
        # 1. Look at pickings
        if "picking_ids" in self._fields:
            for picking in self.picking_ids:
                if "carrier_tracking_ref" in picking._fields and picking.carrier_tracking_ref:
                    return picking.carrier_tracking_ref
        # 2. Look at custom order fields
        for fname in ("postnl_track_trace_code", "x_tracking_ref", "x_carrier_tracking_ref", "carrier_tracking_ref"):
            if fname in self._fields and getattr(self, fname, False):
                return getattr(self, fname)
        return False

    def _moyee_get_monta_delivery_date(self):
        self.ensure_one()
        # 1. Check custom field on sale.order
        if "monta_delivery_date" in self._fields and self.monta_delivery_date:
            return self.monta_delivery_date
        # 2. Check pickings
        if "picking_ids" in self._fields:
            for picking in self.picking_ids:
                if "monta_delivery_date" in picking._fields and picking.monta_delivery_date:
                    return picking.monta_delivery_date
                # Fallback to actual done/shipped date if shipped
                if picking.state == 'done' and picking.date_done:
                    return picking.date_done.date()
                # Fallback to scheduled date if not shipped yet
                if picking.state not in ('done', 'cancel') and picking.scheduled_date:
                    return picking.scheduled_date.date()
        # 3. Fallback to order standard dates
        if self.commitment_date:
            return self.commitment_date.date() if hasattr(self.commitment_date, 'date') else self.commitment_date
        if self.expected_date:
            return self.expected_date.date() if hasattr(self.expected_date, 'date') else self.expected_date
        return False

    # ============================================================
    # Portal Status Mappings
    # ============================================================
    def _get_moyee_portal_order_status(self):
        self.ensure_one()
        state = self.state or 'draft'
        if state in ('draft', 'sent'):
            return {'label': _('In progress'), 'class': 'moyee-status-processing'}
        elif state == 'sale':
            return {'label': _('In progress'), 'class': 'moyee-status-processing'}
        elif state == 'done':
            return {'label': _('Completed'), 'class': 'moyee-status-delivered'}
        elif state == 'cancel':
            return {'label': _('Cancelled'), 'class': 'moyee-status-cancelled'}
        return {'label': _('In progress'), 'class': 'moyee-status-processing'}

    def _get_moyee_portal_delivery_status(self):
        self.ensure_one()
        pickings = self.picking_ids.filtered(lambda p: p.state != 'cancel') if 'picking_ids' in self._fields else self.env['stock.picking']
        
        if not pickings:
            return {'label': _('Pending shipment'), 'class': 'moyee-status-upcoming'}
        
        if all(p.state == 'done' for p in pickings):
            state = 'done'
        elif any(p.state == 'done' for p in pickings):
            state = 'partial'
        else:
            state = 'pending'
            
        if state == 'pending':
            return {'label': _('Pending shipment'), 'class': 'moyee-status-upcoming'}
        elif state == 'partial':
            return {'label': _('On the way'), 'class': 'moyee-status-transit'}
        elif state == 'done':
            m_date = self._moyee_get_monta_delivery_date()
            t_ref = self._moyee_get_tracking_ref()
            today = fields.Date.context_today(self)
            
            if m_date:
                if m_date < today:
                    return {'label': _('Delivered'), 'class': 'moyee-status-delivered'}
                else:
                    return {'label': _('On the way'), 'class': 'moyee-status-transit'}
            else:
                if t_ref:
                    return {'label': _('On the way'), 'class': 'moyee-status-transit'}
                else:
                    return {'label': _('Delivered'), 'class': 'moyee-status-delivered'}