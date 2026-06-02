# File: moyee_subscription_portal_manager/models/sale_order.py
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


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

    moyee_removed_line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="order_id",
        string="Removed Lines",
        domain=[("x_moyee_is_removed", "=", True)],
    )

    # ============================================================
    # Subscription detection (robust across Odoo builds)
    # ============================================================
    def _compute_is_subscription_order(self):
        for order in self:
            is_sub = False
            # Odoo 18 in your DB uses: is_subscription + plan_id + subscription_state
            for fname in (
                "is_subscription",
                "plan_id",  # ✅ IMPORTANT (your DB)
                "subscription_state",
                "subscription_status",
                # Other builds / customizations
                "recurring_plan_id",
                "subscription_pricing_id",
                "subscription_plan_id",
                "recurring_pricing_id",
            ):
                if fname in order._fields and getattr(order, fname, False):
                    is_sub = True
                    break
            order.is_subscription_order = is_sub

    # ============================================================
    # Hide removed lines in invoices / reports / PDFs
    # ============================================================
    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(
            lambda l: l.display_type or (not l.x_moyee_is_removed and float(l.product_uom_qty or 0.0) > 0.0)
        )

    def _get_order_lines_to_report(self):
        try:
            lines = super()._get_order_lines_to_report()
        except AttributeError:
            # Some builds don't have this method
            lines = self.order_line
        return lines.filtered(
            lambda l: l.display_type or (not l.x_moyee_is_removed and float(l.product_uom_qty or 0.0) > 0.0)
        )

    # ============================================================
    # Portal security helpers
    # ============================================================
    def _moyee_portal_check_access(self, *, portal_user=None, access_token=None, require_subscription=True):
        self.ensure_one()
        portal_user = portal_user or self.env.user

        # 1. Token-based access (shared links)
        if access_token and self.access_token and access_token == self.access_token:
            return True

        # Employees are allowed
        if portal_user.has_group("base.group_user"):
            return True

        if portal_user._is_public():
            # If public and token failed/missing, they must login
            raise AccessError(_("You must be logged in to manage subscriptions."))

        if require_subscription and not self.is_subscription_order:
            raise AccessError(_("This record is not a subscription."))

        if self.partner_id.commercial_partner_id != portal_user.partner_id.commercial_partner_id:
            raise AccessError(_("You do not have access to this subscription."))

        if self.state not in ("sale", "done"):
            raise UserError(_("This subscription is not in a confirmed state."))

        # In your DB: subscription_state looks like "3_progress"
        if "subscription_state" in self._fields and self.subscription_state:
            state_val = str(self.subscription_state).lower()
            if state_val in ("closed", "cancel", "churned", "4_closed") or "closed" in state_val:
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
    def _moyee_get_portal_addable_products(self):
        self.ensure_one()
        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()

        domain = [("sale_ok", "=", True)]
        if "subscription_ok" in Template._fields:
            domain.append(("product_tmpl_id.subscription_ok", "=", True))
        elif "recurring_invoice" in Template._fields:
            domain.append(("product_tmpl_id.recurring_invoice", "=", True))

        if "company_id" in Product._fields and self.company_id:
            domain.append(("company_id", "in", [False, self.company_id.id]))

        # Filter by 'Subscription' tag if tag_ids field exists on product.template
        if "tag_ids" in Template._fields:
            domain.append(("product_tmpl_id.tag_ids.name", "ilike", "Subscription"))

        # Exclude internal/delivery/non-coffee products
        domain.append(("name", "not ilike", "delivery"))
        domain.append(("name", "not ilike", "rent"))

        products = Product.search(domain, order="name, id", limit=200)

        # Enhance products with filter metadata (Grind, Weight)
        # We store this in a list of dicts for the portal template if needed,
        # but Odoo templates prefer objects. We'll add a helper method to products
        # or just pre-process them here.
        return products

    def _moyee_extract_product_metadata(self, product):
        """
        Extract Grind and Weight from product attributes or name.
        Returns (grind, weight)
        """
        grind = "other"
        weight = "other"

        # 1. Check attributes
        attr_values = product.product_template_attribute_value_ids
        for av in attr_values:
            attr_name = (av.attribute_id.name or "").lower()
            val_name = (av.name or "").lower()

            if "grind" in attr_name or "maling" in attr_name:
                if "whole" in val_name: grind = "whole"
                elif "filter" in val_name: grind = "filter"
                elif "espresso" in val_name: grind = "espresso"
                elif "capsule" in val_name: grind = "capsules"
            
            if "weight" in attr_name or "size" in attr_name:
                if "1kg" in val_name.replace(" ", "") or "1 kg" in val_name: weight = "1kg"
                elif "250" in val_name: weight = "250g"
                elif "25" in val_name and "capsule" in val_name: weight = "25caps"

        # 2. Fallback to name scanning if still 'other'
        name = (product.display_name or "").lower()
        if grind == "other":
            if "whole bean" in name: grind = "whole"
            elif "filter grind" in name: grind = "filter"
            elif "espresso grind" in name: grind = "espresso"
            elif "capsule" in name: grind = "capsules"

        if weight == "other":
            if "1kg" in name.replace(" ", "") or "1 kg" in name: weight = "1kg"
            elif "250g" in name or "250 g" in name: weight = "250g"
            elif "25 capsule" in name: weight = "25caps"

        return grind, weight

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
        ✅ Includes inactive plans (active_test=False) to avoid empty list
        ✅ Multi-company safe context for SaaS
        """
        self.ensure_one()

        plan_field, Plan = self._moyee_get_plan_model()
        if not plan_field:
            return self.env["ir.model"].browse([])

        # Portal-safe context (VERY IMPORTANT on SaaS)
        company_ids = self.env["res.company"].sudo().search([]).ids
        Plan = Plan.with_context(allowed_company_ids=company_ids, active_test=False)

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
                    optional = current_plan[fname]
                    if optional:
                        return optional.with_context(active_test=False).sudo()

        # Fallback: return all plans
        domain = []
        if "company_id" in Plan._fields and self.company_id:
            # ✅ safest default: order company + global (company_id False)
            domain = [("company_id", "in", [False, self.company_id.id])]

        order_by = "sequence, name, id" if "sequence" in Plan._fields else "name, id"
        return Plan.search(domain, order=order_by)

    # ============================================================
    # ✅ Change interval (write to correct field)
    # ============================================================
    def moyee_portal_change_interval(self, *, portal_user_id, plan_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

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
        self.sudo().write({plan_field: plan_id})

        self.with_user(1).message_post(
            body=_("Moyee: customer changed subscription interval via portal."),
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

    def moyee_portal_pause(self, *, portal_user_id, pause_until_date=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)
        self._moyee_set_subscription_paused_state(paused=True)

        if pause_until_date:
            field_name = self._moyee_get_subscription_next_date_field_name()
            if field_name:
                try:
                    parsed_date = fields.Date.from_string(pause_until_date)
                    if parsed_date:
                        self.sudo().write({field_name: parsed_date})
                except Exception:
                    pass

        self.with_user(1).message_post(
            body=_("Moyee: customer paused the subscription via portal. Next resume date: %s") % (pause_until_date or 'No change'),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # ✅ Skip delivery (portal)
    # ============================================================
    def moyee_portal_skip_delivery(self, *, portal_user_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        field_name = self._moyee_get_subscription_next_date_field_name()
        if not field_name:
            raise UserError(_("This subscription does not expose a next date field."))

        current_date = self[field_name] or fields.Date.today()
        
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

        from dateutil.relativedelta import relativedelta
        new_date = current_date + relativedelta(months=months, weeks=weeks, days=days)

        self.sudo().write({field_name: new_date})
        self.with_user(1).message_post(
            body=_("Moyee: customer skipped next delivery via portal. Next date: %s") % new_date,
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def moyee_portal_resume(self, *, portal_user_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)
        self._moyee_set_subscription_paused_state(paused=False)

        self.with_user(1).message_post(
            body=_("Moyee: customer resumed the subscription via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # ✅ Cancel / Close (robust)
    # ============================================================
    def _moyee_set_subscription_closed_state(self):
        self.ensure_one()

        # 1) Try standard methods first
        for m in ("action_close", "action_cancel", "action_subscription_close", "action_set_to_close"):
            if hasattr(self, m):
                try:
                    getattr(self.sudo(), m)()
                    return True
                except Exception:
                    pass

        # 2) Generic selection field fallback for subscription_state
        if "subscription_state" in self._fields:
            selection = self._fields["subscription_state"].selection or []
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
            key = _pick(("5_churn", "6_churn", "4_closed", "closed", "cancel", "churned", "churn", "close"))
            if key:
                self.sudo().write({"subscription_state": key})
                return True

        # 3) stage-based fallback
        for stage_field in ("subscription_stage_id", "stage_id"):
            if stage_field in self._fields:
                Stage = self.env[self._fields[stage_field].comodel_name].sudo()
                target = (
                    Stage.search([("name", "ilike", "closed")], limit=1)
                    or Stage.search([("name", "ilike", "cancel")], limit=1)
                    or Stage.search([("name", "ilike", "churn")], limit=1)
                )
                if target:
                    self.sudo().write({stage_field: target.id})
                    return True

        # 4) generic selection field fallback for subscription_status
        if "subscription_status" in self._fields:
            selection = self._fields["subscription_status"].selection or []
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
            key = _pick(("closed", "cancel", "churned", "churn", "close"))
            if key:
                self.sudo().write({"subscription_status": key})
                return True

        # 5) standard sale.order cancel if nothing else worked
        if hasattr(self, "action_cancel"):
            try:
                self.sudo().action_cancel()
                return True
            except Exception:
                pass

        raise UserError(_("Close/cancel is not available for this subscription implementation."))

    def moyee_portal_close(self, *, portal_user_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)
        self._moyee_set_subscription_closed_state()

        self.with_user(1).message_post(
            body=_("Moyee: customer cancelled/closed the subscription via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True


    # ============================================================
    # Push next date (portal)
    # ============================================================
    def moyee_portal_push_next_date(self, *, portal_user_id, next_date):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        field_name = self._moyee_get_subscription_next_date_field_name()
        if not field_name:
            raise UserError(_("This subscription does not expose a next date field."))

        try:
            value = fields.Date.from_string(next_date)
        except Exception:
            raise ValidationError(_("Invalid date."))

        if not value:
            raise ValidationError(_("Please select a date."))

        self.sudo().write({field_name: value})
        self.with_user(1).message_post(
            body=_("Moyee: customer updated next date via portal (%s).") % field_name,
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # Add product (portal)
    # ============================================================
    def moyee_portal_add_product(self, *, portal_user_id, product_id, qty=1.0):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        product = self.env["product.product"].sudo().browse(int(product_id)).exists()
        if not product:
            raise ValidationError(_("Invalid product."))

        try:
            qty = float(qty or 0.0)
        except Exception:
            qty = 0.0
        if qty <= 0:
            raise ValidationError(_("Quantity must be greater than 0."))

        line = self.order_line.filtered(
            lambda l: (not l.display_type) and l.product_id.id == product.id and not l.x_moyee_is_removed
        )
        if line:
            line[:1].sudo().write({"product_uom_qty": float(line[:1].product_uom_qty or 0.0) + qty})
        else:
            self.env["sale.order.line"].sudo().create(
                {
                    "order_id": self.id,
                    "product_id": product.id,
                    "product_uom_qty": qty,
                    "name": product.display_name,
                }
            )

        self.with_user(1).message_post(
            body=_("Moyee: customer added product via portal (%s x %s).") % (product.display_name, qty),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # FULL ADDRESS (create/update child contact safely)
    # ============================================================
    def _moyee_portal_upsert_child_address(self, portal_user, vals, addr_type):
        self.ensure_one()
        commercial = portal_user.partner_id.commercial_partner_id

        clean = {k: v for k, v in (vals or {}).items() if v not in (None, "", False)}
        if not clean:
            return False

        clean.update({"parent_id": commercial.id, "type": addr_type})

        current = self.partner_shipping_id if addr_type == "delivery" else self.partner_invoice_id
        if current and current.parent_id == commercial:
            current.sudo().write(clean)
            return current

        return self.env["res.partner"].sudo().create(clean)

    def moyee_portal_change_address_full(self, *, portal_user_id, shipping_vals=None, invoice_vals=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

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
        self.with_user(1).message_post(
            body=_("Moyee: customer updated full addresses via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # Update line quantity (portal)
    # ============================================================
    def moyee_portal_update_line_qty(self, *, portal_user_id, line_id, qty):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        line = self.env["sale.order.line"].sudo().browse(int(line_id)).exists()
        if not line or line.order_id.id != self.id:
            raise ValidationError(_("Invalid subscription line."))

        if line.display_type or line.x_moyee_is_removed:
            raise UserError(_("This line cannot be updated."))

        try:
            qty = float(qty or 0.0)
        except Exception:
            qty = 0.0
        if qty <= 0:
            raise ValidationError(_("Quantity must be greater than 0."))

        # Respect delivery constraint: never go below delivered qty
        delivered = float(line.qty_delivered or 0.0)
        if qty < delivered:
            raise UserError(
                _("Quantity cannot be less than the already delivered amount (%s).") % delivered
            )

        old_qty = line.product_uom_qty
        line.sudo().write({"product_uom_qty": qty})

        product_label = line.product_id.display_name if line.product_id else (line.name or _("(no product)"))
        self.with_user(1).message_post(
            body=_("Moyee: customer changed quantity via portal — %s: %s → %s.") % (
                product_label, old_qty, qty
            ),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # Edit line product (portal)
    # ============================================================
    def moyee_portal_edit_line_product(self, *, portal_user_id, line_id, template_id, grind, weight):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        line = self.env["sale.order.line"].sudo().browse(int(line_id)).exists()
        if not line or line.order_id.id != self.id:
            raise ValidationError(_("Invalid subscription line."))

        if line.display_type or line.x_moyee_is_removed:
            raise UserError(_("This line cannot be edited."))

        template = self.env["product.template"].sudo().browse(int(template_id)).exists()
        if not template:
            raise ValidationError(_("Invalid coffee type selected."))

        variants = self.env["product.product"].sudo().search([
            ("product_tmpl_id", "=", template.id),
            ("sale_ok", "=", True),
        ])

        target_product = False
        for var in variants:
            v_grind, v_weight = self._moyee_extract_product_metadata(var)
            if v_grind == grind and v_weight == weight:
                target_product = var
                break

        if not target_product:
            raise ValidationError(
                _("The selected combination of %s (%s, %s) is not available.") % (template.name, grind, weight)
            )

        old_product = line.product_id
        if old_product.id != target_product.id:
            # Check if this product is already in the subscription (to prevent duplicates)
            existing_line = self.order_line.filtered(
                lambda l: (not l.display_type) and l.product_id.id == target_product.id and not l.x_moyee_is_removed and l.id != line.id
            )
            if existing_line:
                # Merge quantities
                existing_line[:1].sudo().write({"product_uom_qty": existing_line[:1].product_uom_qty + line.product_uom_qty})
                # Soft remove the current line
                line.sudo().write({"x_moyee_is_removed": True, "product_uom_qty": 0.0})
            else:
                line.sudo().write({
                    "product_id": target_product.id,
                    "name": target_product.with_context(display_default_code=False).display_name or target_product.display_name,
                    "product_uom": target_product.uom_id.id,
                })
                if hasattr(line, "_compute_pricelist_item_id"):
                    line.sudo()._compute_pricelist_item_id()
                elif hasattr(line, "_compute_price_unit"):
                    line.sudo()._compute_price_unit()

        self.with_user(1).message_post(
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
        for fname in ("x_monta_tracking_url", "x_tracking_url", "x_track_trace", "carrier_tracking_url", "monta_track_trace"):
            if fname in self._fields and getattr(self, fname, False):
                return getattr(self, fname)
        return False