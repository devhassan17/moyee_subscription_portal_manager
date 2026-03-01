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
            if "subscription_status" in order._fields and order.subscription_status:
                is_sub = True
            elif "recurring_plan_id" in order._fields and order.recurring_plan_id:
                is_sub = True
            elif "is_subscription" in order._fields and order.is_subscription:
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

        IMPORTANT FIX:
        Your system clearly uses recurring_plan_id (Monthly / 2 Monthly / 3 Monthly),
        but earlier logic could return empty due to field mismatches.
        So we:
        - fetch plans from recurring_plan_id comodel
        - company-filter if possible
        - prefer "month/monthly" plans with interval 1/2/3 if detectable
        - otherwise return all plans (never wrongly empty)
        """
        self.ensure_one()

        if "recurring_plan_id" not in self._fields:
            return self.env["ir.model"].browse()

        plan_model = self._fields["recurring_plan_id"].comodel_name
        Plan = self.env[plan_model].sudo()

        domain = []
        if "company_id" in Plan._fields and self.company_id:
            domain.append(("company_id", "in", [False, self.company_id.id]))

        order_by = "sequence, name, id" if "sequence" in Plan._fields else "name, id"
        plans = Plan.search(domain, order=order_by)

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
    # ✅ Pause / Resume - ROBUST
    # -----------------------
    def _moyee_set_subscription_paused_state(self, paused=True):
        """
        Tries multiple implementations:
        1) known methods (action_pause/action_resume/etc)
        2) stage_id (common in subscriptions)
        3) subscription_status selections
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

        # 2) stage-based (most common)
        if "stage_id" in self._fields:
            Stage = self.env[self._fields["stage_id"].comodel_name].sudo()

            if paused:
                target = Stage.search([("name", "ilike", "pause")], limit=1) or Stage.search(
                    [("name", "ilike", "suspend")], limit=1
                )
            else:
                target = Stage.search([("name", "ilike", "progress")], limit=1) or Stage.search(
                    [("name", "ilike", "in progress")], limit=1
                )

            if target:
                self.sudo().write({"stage_id": target.id})
                return True

        # 3) subscription_status selection-based
        if "subscription_status" in self._fields:
            selection = self._fields["subscription_status"].selection or []
            keys = {k for k, _lbl in selection}

            if paused:
                for k in ("paused", "pause", "suspended", "hold"):
                    if k in keys:
                        self.sudo().write({"subscription_status": k})
                        return True
            else:
                for k in ("in_progress", "progress", "running", "active"):
                    if k in keys:
                        self.sudo().write({"subscription_status": k})
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