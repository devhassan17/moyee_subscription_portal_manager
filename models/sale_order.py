# File: moyee_subscription_portal_manager/models/sale_order.py
import logging
import re
import json
from dateutil.relativedelta import relativedelta
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

    moyee_removed_line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="order_id",
        string="Removed Lines",
        domain=[("x_moyee_is_removed", "=", True)],
    )

    # ============================================================
    # Subscription detection (robust across Odoo builds)
    # ============================================================
    def _moyee_is_subscription_order(self):
        self.ensure_one()
        for fname in (
            "is_subscription",
            "plan_id",
            "subscription_state",
            "subscription_status",
            "recurring_plan_id",
            "subscription_pricing_id",
            "subscription_plan_id",
            "recurring_pricing_id",
        ):
            if fname in self._fields and getattr(self, fname, False):
                return True
        return False

    def _compute_is_subscription_order(self):
        for order in self:
            order.is_subscription_order = order._moyee_is_subscription_order()

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

    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'order_line.price_total', 'order_line.x_moyee_is_removed')
    def _compute_amounts(self):
        super()._compute_amounts()
        for order in self:
            if order._moyee_is_subscription_order():
                order_lines = order.order_line.filtered(lambda x: not x.display_type and not x.x_moyee_is_removed)
                
                # Check company rounding method (global vs per-line)
                round_globally = getattr(order.company_id, 'tax_calculation_rounding_method', False) == 'round_globally'
                if round_globally:
                    try:
                        tax_results = self.env['account.tax']._compute_taxes([
                            line._convert_to_tax_base_line_dict() for line in order_lines
                        ])
                        totals = tax_results.get('totals', {})
                        order.amount_untaxed = totals.get(order.currency_id, {}).get('amount_untaxed', 0.0)
                        order.amount_tax = totals.get(order.currency_id, {}).get('amount_tax', 0.0)
                        order.amount_total = order.amount_untaxed + order.amount_tax
                    except Exception:
                        _logger.exception("Moyee: Failed to compute taxes round globally on order %s, falling back to sums.", order.name)
                        order.amount_untaxed = sum(order_lines.mapped('price_subtotal'))
                        order.amount_tax = sum(order_lines.mapped('price_tax'))
                        order.amount_total = sum(order_lines.mapped('price_total'))
                else:
                    order.amount_untaxed = sum(order_lines.mapped('price_subtotal'))
                    order.amount_tax = sum(order_lines.mapped('price_tax'))
                    order.amount_total = sum(order_lines.mapped('price_total'))

                # Update standard Odoo subscription fields if present (e.g. Recurring Amount / MRR)
                for fname in ("recurring_amount_untaxed", "recurring_amount_tax", "recurring_amount_total"):
                    if fname in order._fields:
                        active_sub_lines = order_lines.filtered(lambda l: l._moyee_is_subscription_line() if hasattr(l, "_moyee_is_subscription_line") else True)
                        if fname == "recurring_amount_untaxed":
                            order[fname] = sum(active_sub_lines.mapped('price_subtotal'))
                        elif fname == "recurring_amount_tax":
                            order[fname] = sum(active_sub_lines.mapped('price_tax'))
                        elif fname == "recurring_amount_total":
                            order[fname] = sum(active_sub_lines.mapped('price_total'))

                for fname in ("non_recurring_amount_untaxed", "non_recurring_amount_tax", "non_recurring_amount_total"):
                    if fname in order._fields:
                        one_time_lines = order_lines.filtered(lambda l: not l._moyee_is_subscription_line() if hasattr(l, "_moyee_is_subscription_line") else False)
                        if fname == "non_recurring_amount_untaxed":
                            order[fname] = sum(one_time_lines.mapped('price_subtotal'))
                        elif fname == "non_recurring_amount_tax":
                            order[fname] = sum(one_time_lines.mapped('price_tax'))
                        elif fname == "non_recurring_amount_total":
                            order[fname] = sum(one_time_lines.mapped('price_total'))

    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'order_line.price_total', 'order_line.x_moyee_is_removed')
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for order in self:
            if order._moyee_is_subscription_order():
                order_lines = order.order_line.filtered(lambda x: not x.display_type and not x.x_moyee_is_removed)
                try:
                    if hasattr(self.env['sale.order.line'], '_convert_to_tax_base_line_dict'):
                        tax_base_lines = [line._convert_to_tax_base_line_dict() for line in order_lines]
                    else:
                        tax_base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
                    order.tax_totals = self.env['account.tax']._prepare_tax_totals(
                        tax_base_lines,
                        order.currency_id or order.company_id.currency_id,
                    )
                except Exception:
                    _logger.exception("Moyee: Failed to compute tax totals on order %s.", order.name)

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
        if self.env.user.has_group("base.group_user"):
            return True

        if portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

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

        # Exclude internal/delivery/non-coffee products (only allow physical products: storable/consumable)
        if "detailed_type" in Product._fields:
            domain.append(("detailed_type", "in", ["consu", "product"]))
        elif "type" in Product._fields:
            domain.append(("type", "in", ["consu", "product"]))

        products = Product.search(domain, order="name, id", limit=200)

        # Enhance products with filter metadata (Grind, Weight)
        # We store this in a list of dicts for the portal template if needed,
        # but Odoo templates prefer objects. We'll add a helper method to products
        # or just pre-process them here.
        return products

    def moyee_extract_product_metadata(self, product):
        """
        Extract Grind and Weight from product attributes or name.
        Returns (grind, weight)
        """
        grind = "other"
        weight = "other"

        # 1. Check attributes
        attr_values = product.product_template_attribute_value_ids
        for av in attr_values:
            if grind != "other":
                break
            attr_name = (av.attribute_id.name or "").lower()
            val_name = (av.name or "").lower()

            if "grind" in attr_name or "maling" in attr_name:
                if "whole" in val_name or "boon" in val_name or "bonen" in val_name:
                    grind = "whole"
                elif "filter" in val_name:
                    grind = "filter"
                elif "espresso" in val_name:
                    grind = "espresso"
                elif "capsule" in val_name or "cup" in val_name:
                    grind = "capsules"

        for av in attr_values:
            if weight != "other":
                break
            attr_name = (av.attribute_id.name or "").lower()
            val_name = (av.name or "").lower()
            if "weight" in attr_name or "size" in attr_name or "gewicht" in attr_name:
                v_clean = val_name.replace(" ", "")
                if "1kg" in v_clean or "1.0kg" in v_clean or "1000g" in v_clean or "1000 g" in val_name:
                    weight = "1kg"
                elif "250g" in v_clean or "250" in v_clean or "0.25kg" in v_clean or "0.25 kg" in val_name:
                    weight = "250g"
                elif "25caps" in v_clean or v_clean == "25" or "capsules" in v_clean or "capsule" in v_clean or "cups" in v_clean:
                    weight = "25caps"

        # 2. Fallback to name scanning if still 'other'
        name = (product.display_name or "").lower()
        if grind == "other":
            if "whole" in name or "boon" in name or "bonen" in name:
                grind = "whole"
            elif "filter grind" in name or "filtergrind" in name or "filter" in name:
                grind = "filter"
            elif "espresso grind" in name or "espressogrind" in name or "espresso" in name:
                grind = "espresso"
            elif "capsule" in name or "cup" in name:
                grind = "capsules"

        if weight == "other":
            name_clean = name.replace(" ", "")
            if "1kg" in name_clean or "1000g" in name_clean or "1.0kg" in name_clean:
                weight = "1kg"
            elif "250g" in name_clean or "0.25kg" in name_clean or "250" in name_clean:
                weight = "250g"
            elif any(x in name_clean for x in ("25caps", "25capsule", "25cups")) or "25 capsule" in name or "25 cups" in name or re.search(r'\b25\b', name):
                weight = "25caps"

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
                    parsed_date = fields.Date.from_string(pause_until_date)
                    if parsed_date:
                        if parsed_date < fields.Date.today():
                            raise ValidationError(_("The pause date cannot be in the past."))
                        self.sudo().write({field_name: parsed_date})
                except Exception as e:
                    if isinstance(e, ValidationError):
                        raise
                    _logger.exception("Moyee: Failed to pause subscription next date update.")

        self.with_user(1).message_post(
            body=_("Moyee: customer paused the subscription via portal. Next resume date: %s") % (pause_until_date or 'No change'),
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

        new_date = current_date + relativedelta(months=months, weeks=weeks, days=days)

        self.sudo().write({field_name: new_date})
        self.with_user(1).message_post(
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

        self.with_user(1).message_post(
            body=_("Moyee: customer resumed the subscription via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # ============================================================
    # ✅ Cancel / Close (robust)
    # ============================================================
    def _moyee_set_subscription_closed_state(self, reason=None):
        self.ensure_one()

        # Odoo 18 close reason handling
        if "close_reason_id" in self._fields:
            close_reason = False
            comodel_name = self._fields["close_reason_id"].comodel_name
            CloseReasonModel = self.env[comodel_name].sudo()
            if reason:
                # Try ID lookup first if numeric
                if isinstance(reason, int) or (isinstance(reason, str) and reason.isdigit()):
                    close_reason = CloseReasonModel.browse(int(reason)).exists()
                if not close_reason:
                    # 1. Search for existing close reason matching the selected reason
                    close_reason = CloseReasonModel.search([("name", "ilike", reason)], limit=1)
            
            # If still no close_reason and we have the field, let's grab the first one as fallback
            if not close_reason:
                close_reason = CloseReasonModel.search([], limit=1)
            
            if close_reason:
                try:
                    self.sudo().write({"close_reason_id": close_reason.id})
                except Exception as e:
                    _logger.debug("Moyee: Failed to write close_reason_id: %s", str(e))

        # 1) Try native field writes for subscription_state first (to bypass dummy action_close)
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
            key = _pick(("6_churn", "5_churn", "4_closed", "closed", "cancel", "churned", "churn", "close"))
            if key:
                try:
                    self.sudo().write({"subscription_state": key})
                    return True
                except Exception as e:
                    _logger.debug("Moyee: Failed to write subscription_state: %s", str(e))

        # 2) Try standard methods, but verify they don't just return a wizard action dict
        for m in ("action_close", "action_cancel", "action_subscription_close", "action_set_to_close"):
            if hasattr(self, m):
                try:
                    res = getattr(self.sudo(), m)()
                    if res and isinstance(res, dict):
                        continue
                    return True
                except Exception as e:
                    _logger.debug("Moyee: Failed calling %s: %s", m, str(e))

        # 3) Generic selection field fallback for subscription_status
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
                try:
                    self.sudo().write({"subscription_status": key})
                    return True
                except Exception as e:
                    _logger.debug("Moyee: Failed writing subscription_status: %s", str(e))

        # 4) stage-based fallback
        for stage_field in ("subscription_stage_id", "stage_id"):
            if stage_field in self._fields:
                Stage = self.env[self._fields[stage_field].comodel_name].sudo()
                target = (
                    Stage.search([("name", "ilike", "closed")], limit=1)
                    or Stage.search([("name", "ilike", "cancel")], limit=1)
                    or Stage.search([("name", "ilike", "churn")], limit=1)
                )
                if target:
                    try:
                        self.sudo().write({stage_field: target.id})
                        return True
                    except Exception as e:
                        _logger.debug("Moyee: Failed writing stage_field %s: %s", stage_field, str(e))

        # 5) standard sale.order cancel if nothing else worked
        if hasattr(self, "action_cancel"):
            try:
                self.sudo().action_cancel()
                return True
            except Exception as e:
                _logger.debug("Moyee: Failed action_cancel call: %s", str(e))

        raise UserError(_("Close/cancel is not available for this subscription implementation."))

    def moyee_portal_close(self, *, portal_user_id, reason=None, access_token=None):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))
        if not self.env.user.has_group("base.group_user") and portal_user.id != self.env.user.id:
            raise AccessError(_("You cannot perform actions on behalf of another user."))

        self._moyee_portal_check_access(portal_user=portal_user, access_token=access_token, require_subscription=True)
        self._moyee_set_subscription_closed_state(reason=reason)

        body_msg = _("Moyee: customer cancelled/closed the subscription via portal.")
        if reason:
            body_msg += _("<br/>Reason: %s") % reason

        self.with_user(1).message_post(
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

        self.sudo().write({field_name: value})
        self.with_user(1).message_post(
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

        # 5. Fix tax-included price if applicable
        if price and hasattr(self.env["account.tax"], "_fix_tax_included_price_company"):
            try:
                price = self.env["account.tax"]._fix_tax_included_price_company(
                    price, line.product_id.taxes_id, line.tax_id, line.company_id
                )
            except Exception as e:
                _logger.debug("Moyee: Tax inclusion fix failed: %s", str(e))

        if not price or float(price) <= 0.0:
            raise ValidationError(_("The product '%s' does not have a valid price configured. Action aborted.") % line.product_id.display_name)

        line.write({"price_unit": price})

    # ============================================================
    # Add product (portal)
    # ============================================================
    def moyee_portal_add_product(self, *, portal_user_id, product_id, qty=1.0, access_token=None):
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
            line_to_update = line[:1].sudo()
            line_to_update.write({"product_uom_qty": float(line_to_update.product_uom_qty or 0.0) + qty})
            self._moyee_recompute_line_price(line_to_update)
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

        self.with_user(1).message_post(
            body=_("Moyee: customer added product via portal (%s x %s).") % (product.display_name, qty),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    def _moyee_portal_upsert_child_address(self, portal_user, vals, addr_type):
        self.ensure_one()
        commercial = portal_user.partner_id.commercial_partner_id

        clean = {k: v for k, v in (vals or {}).items() if v not in (None, "", False)}
        if not clean:
            return False

        current = self.partner_shipping_id if addr_type == "delivery" else self.partner_invoice_id
        if addr_type == "invoice" and current == commercial:
            commercial.sudo().write(clean)
            return commercial

        clean.update({"parent_id": commercial.id, "type": addr_type})

        if not (current and current.parent_id == commercial):
            existing_children = commercial.child_ids.filtered(lambda p: p.type == addr_type)
            if existing_children:
                current = existing_children[0]
            else:
                current = False

        if current:
            current.sudo().write(clean)
            return current

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
        self.with_user(1).message_post(
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
        line_to_update = line.sudo()
        line_to_update.write({"product_uom_qty": qty})
        self._moyee_recompute_line_price(line_to_update)

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
    def moyee_portal_edit_line_product(self, *, portal_user_id, line_id, template_id, grind, weight, access_token=None):
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

        variants = self.env["product.product"].sudo().search([
            ("product_tmpl_id", "=", template.id),
            ("sale_ok", "=", True),
        ])

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

        old_product = line.product_id
        if old_product.id != target_product.id:
            # Check if this product is already in the subscription (to prevent duplicates)
            existing_line = self.order_line.filtered(
                lambda l: (not l.display_type) and l.product_id.id == target_product.id and not l.x_moyee_is_removed and l.id != line.id
            )
            if existing_line:
                # Merge quantities
                existing_line_sudo = existing_line[:1].sudo()
                existing_line_sudo.write({"product_uom_qty": existing_line_sudo.product_uom_qty + line.product_uom_qty})
                # Soft remove the current line
                line.sudo().write({"x_moyee_is_removed": True, "product_uom_qty": 0.0})
                self._moyee_recompute_line_price(existing_line_sudo)
            else:
                line_sudo = line.sudo()
                line_sudo.write({
                    "product_id": target_product.id,
                    "name": target_product.with_context(display_default_code=False).display_name or target_product.display_name,
                    "product_uom": target_product.uom_id.id,
                })
                self._moyee_recompute_line_price(line_sudo)

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