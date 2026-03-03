# File: moyee_subscription_portal_manager/models/sale_order.py
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

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

    def _compute_is_subscription_order(self):
        for order in self:
            is_sub = False
            # Odoo 16+ merged subscriptions into sale.order; implementations differ a bit per edition.
            # We detect subscription orders by checking the most common fields.
            if "is_subscription" in order._fields and order.is_subscription:
                is_sub = True
            elif "recurring_plan_id" in order._fields and order.recurring_plan_id:
                is_sub = True
            elif "subscription_state" in order._fields and order.subscription_state:
                is_sub = True
            elif "subscription_status" in order._fields and order.subscription_status:
                is_sub = True
            order.is_subscription_order = is_sub

    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda l: l.display_type or (not l.x_moyee_is_removed and l.product_uom_qty > 0))

    def _get_order_lines_to_report(self):
        try:
            lines = super()._get_order_lines_to_report()
        except AttributeError:
            lines = self.order_line
        return lines.filtered(lambda l: l.display_type or (not l.x_moyee_is_removed and l.product_uom_qty > 0))

    # -----------------------
    # Portal security helpers
    # -----------------------
    def _moyee_portal_check_access(self, *, portal_user=None, require_subscription=True):
        self.ensure_one()
        portal_user = portal_user or self.env.user

        if portal_user.has_group("base.group_user"):
            return True

        if portal_user._is_public():
            raise AccessError(_("You must be logged in to manage subscriptions."))

        if require_subscription and not self.is_subscription_order:
            raise AccessError(_("This record is not a subscription."))

        if self.partner_id.commercial_partner_id != portal_user.partner_id.commercial_partner_id:
            raise AccessError(_("You do not have access to this subscription."))

        if self.state not in ("sale", "done"):
            raise UserError(_("This subscription is not in a confirmed state."))

        if "subscription_status" in self._fields and self.subscription_status:
            if self.subscription_status in ("closed", "cancel", "churned"):
                raise UserError(_("This subscription is closed."))

        return True

    def _moyee_get_subscription_next_date_field_name(self):
        self.ensure_one()
        for fname in ("recurring_next_date", "next_invoice_date", "next_delivery_date", "x_next_delivery_date"):
            if fname in self._fields:
                return fname
        return False

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

        return Product.search(domain, order="name, id", limit=200)

    # -----------------------
    # ✅ Interval/Plan (Portal) - FIXED
    # -----------------------
    def _moyee_get_portal_changeable_plans(self):
        """
        Return the subscription plans the customer can choose from.

        FIX:
        - Prefer current plan's "Optional Plans" (if configured).
        - Otherwise fall back to ALL plans (avoid empty dropdown from company filters).
        """
        self.ensure_one()

        if "recurring_plan_id" not in self._fields:
            return self.env["ir.model"].browse([])

        plan_model = self._fields["recurring_plan_id"].comodel_name
        Plan = self.env[plan_model].sudo()

        # 1) Prefer Odoo's "Optional Plans" configuration if present on the current plan.
        current_plan = self.recurring_plan_id
        if current_plan:
            for fname in (
                "optional_plans",  # common name
                "optional_plan_ids",
                "optional_recurring_plan_ids",
                "optional_recurring_plans",
            ):
                if fname in current_plan._fields:
                    optional = current_plan[fname]
                    if optional:
                        return optional.sudo()

        # 2) Otherwise fall back to *all* recurring plans.
        order_by = "sequence, name, id" if "sequence" in Plan._fields else "name, id"
        plans = Plan.search([], order=order_by)

        def _interval_value(p):
            for f in ("recurring_interval", "recurrence_interval", "recurring_rule_count", "billing_period"):
                if f in p._fields and p[f]:
                    try:
                        return int(p[f])
                    except Exception:
                        return None
            return None

        def _looks_monthly(p):
            if "recurring_rule_type" in p._fields and p.recurring_rule_type:
                if str(p.recurring_rule_type).lower() not in ("month", "monthly", "months"):
                    return False
            name = (p.display_name or p.name or "").lower()
            if "month" in name or "monthly" in name:
                return True
            if "recurring_rule_type" in p._fields and p.recurring_rule_type:
                return True
            return False

        preferred = plans.filtered(lambda p: _looks_monthly(p) and (_interval_value(p) in (None, 1, 2, 3)))
        return preferred if preferred else plans

    def moyee_portal_change_interval(self, *, portal_user_id, plan_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)

        if "recurring_plan_id" not in self._fields:
            raise UserError(_("This subscription does not support interval change."))

        plan_id = int(plan_id or 0)
        if not plan_id:
            raise ValidationError(_("Please select an interval."))

        allowed_plans = self._moyee_get_portal_changeable_plans()
        if not allowed_plans.filtered(lambda p: p.id == plan_id):
            raise AccessError(_("Selected interval is not allowed."))

        self.sudo().write({"recurring_plan_id": plan_id})
        self.with_user(1).message_post(
            body=_("Moyee: customer changed subscription interval via portal."),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # -----------------------
    # ✅ Pause / Resume - ROBUST (Odoo 18 compatible)
    # -----------------------
    def _moyee_set_subscription_paused_state(self, paused=True):
        """
        Tries multiple implementations (Odoo editions/customizations differ):
        1) Known methods (action_pause/action_resume/etc)
        2) Stage-based transitions (stage_id / subscription_stage_id)
        3) Selection field transitions (subscription_state / subscription_status)
        """
        self.ensure_one()

        # 1) method-based
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

        # 2) stage-based
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
                # substring match for keys like '3_paused'
                for cand in candidates:
                    for k in keys:
                        if cand in str(k).lower():
                            return k
                return None

            if paused:
                key = _pick(("paused", "pause", "suspended", "suspend", "hold"))
            else:
                key = _pick(("in_progress", "progress", "running", "active", "open"))

            if key:
                self.sudo().write({field_name: key})
                return True
            return False

        if _set_selection("subscription_state"):
            return True
        if _set_selection("subscription_status"):
            return True

        raise UserError(_("Pause/resume is not available for this subscription implementation."))

    def moyee_portal_pause(self, *, portal_user_id):
        self.ensure_one()
        portal_user = self.env["res.users"].browse(int(portal_user_id)).exists()
        if not portal_user:
            raise AccessError(_("Invalid user."))

        self._moyee_portal_check_access(portal_user=portal_user, require_subscription=True)
        self._moyee_set_subscription_paused_state(paused=True)

        self.with_user(1).message_post(
            body=_("Moyee: customer paused the subscription via portal."),
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

    # -----------------------
    # Push next date (portal)
    # -----------------------
    def moyee_portal_push_next_date(self, *, portal_user_id, next_date):
        """Update the next recurring date on the subscription order."""
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

    # -----------------------
    # Add product (portal)
    # -----------------------
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
            line[:1].sudo().write({"product_uom_qty": line[:1].product_uom_qty + qty})
        else:
            self.env["sale.order.line"].sudo().create({
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "name": product.display_name,
            })

        self.with_user(1).message_post(
            body=_("Moyee: customer added product via portal (%s x %s).") % (product.display_name, qty),
            subtype_xmlid="mail.mt_note",
            author_id=portal_user.partner_id.id,
        )
        return True

    # -----------------------
    # FULL ADDRESS (create/update child contact safely)
    # -----------------------
    def _moyee_portal_upsert_child_address(self, portal_user, vals, addr_type):
        """Create or update a child address under the commercial partner."""
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