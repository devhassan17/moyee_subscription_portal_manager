# File: moyee_subscription_portal_manager/controllers/portal.py
import logging
from urllib.parse import urlencode

from odoo import _, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from werkzeug.exceptions import NotFound

_logger = logging.getLogger(__name__)


# ============================================================
# My Account page (/my/home) data provider
# ============================================================
class MoyeePortalHome(CustomerPortal):
    """Extend /my/home to provide subscription, orders, invoices, partner data."""

    def _prepare_home_portal_values(self, counters=None, **kw):
        if counters is None:
            counters = set()
        values = super()._prepare_home_portal_values(counters)

        partner = request.env.user.partner_id
        commercial = partner.commercial_partner_id

        # ── Active subscription ──
        SaleOrder = request.env["sale.order"].sudo()
        active_subscription = False
        has_subscription = False
        visible_lines = False
        next_date_value = False
        current_plan_display = ""
        current_plan_id = False
        is_paused = False
        available_plans = SaleOrder.browse()

        # Find the user's active subscription order
        sub_domain = [
            ("partner_id.commercial_partner_id", "=", commercial.id),
            ("state", "in", ("sale", "done")),
        ]
        # Odoo 18: subscription_state in active states
        if "subscription_state" in SaleOrder._fields:
            sub_domain.append(("subscription_state", "in", ("3_progress", "4_paused", "2_renewal")))
        elif "is_subscription" in SaleOrder._fields:
            sub_domain.append(("is_subscription", "=", True))

        subscriptions = SaleOrder.search(sub_domain, order="id desc", limit=5)
        if subscriptions:
            active_subscription = subscriptions[0]
            has_subscription = True

            # Visible lines (exclude removed & delivery)
            visible_lines = active_subscription.order_line.filtered(
                lambda l: (
                    l.display_type
                    or (
                        not l.x_moyee_is_removed
                        and float(l.product_uom_qty or 0.0) > 0.0
                    )
                )
            )

            # Next date
            next_date_field = active_subscription._moyee_get_subscription_next_date_field_name()
            if next_date_field:
                next_date_value = active_subscription[next_date_field]

            # Plan info
            plan_field_name = False
            if hasattr(active_subscription, "_moyee_get_recurring_plan_field_name"):
                plan_field_name = active_subscription._moyee_get_recurring_plan_field_name()
            if plan_field_name and plan_field_name in active_subscription._fields and active_subscription[plan_field_name]:
                current_plan_id = active_subscription[plan_field_name].id
                current_plan_display = active_subscription[plan_field_name].display_name

            # Available plans
            try:
                available_plans = active_subscription._moyee_get_portal_changeable_plans()
            except Exception:
                available_plans = SaleOrder.browse()

            # Paused state
            if "subscription_state" in active_subscription._fields and active_subscription.subscription_state == "4_paused":
                is_paused = True

        # ── Recent orders ──
        order_domain = [
            ("partner_id.commercial_partner_id", "=", commercial.id),
            ("state", "in", ("sale", "done", "cancel")),
        ]
        recent_orders = SaleOrder.search(order_domain, order="date_order desc, id desc", limit=15)

        # ── Recent invoices ──
        AccountMove = request.env["account.move"].sudo()
        inv_domain = [
            ("partner_id.commercial_partner_id", "=", commercial.id),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
        ]
        recent_invoices = AccountMove.search(inv_domain, order="invoice_date desc, id desc", limit=10)

        # ── Flash messages from redirect ──
        moyee_home_message = kw.get("moyee_message", "")
        moyee_home_error = kw.get("moyee_error", "")

        values.update({
            "partner": partner,
            "has_subscription": has_subscription,
            "active_subscription": active_subscription,
            "visible_lines": visible_lines,
            "next_date_value": next_date_value,
            "current_plan_display": current_plan_display,
            "current_plan_id": current_plan_id,
            "is_paused": is_paused,
            "available_plans": available_plans,
            "recent_orders": recent_orders,
            "recent_invoices": recent_invoices,
            "moyee_home_message": moyee_home_message,
            "moyee_home_error": moyee_home_error,
        })
        return values

    @http.route(["/my", "/my/home"], type="http", auth="user", website=True)
    def home(self, **kw):
        values = self._prepare_portal_layout_values()
        home_values = self._prepare_home_portal_values(counters=set(), **kw)
        values.update(home_values)
        return request.render("moyee_subscription_portal_manager.portal_my_home_moyee", values)


class MoyeeSubscriptionPortal(http.Controller):
    """Portal-side subscription management (secure write-through controllers)."""

    # ------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------
    def _moyee_get_order_sudo(self, order_id, *, access_token=None, require_subscription=True):
        order = request.env["sale.order"].sudo().browse(int(order_id)).exists()
        if not order:
            raise NotFound()

        try:
            order._moyee_portal_check_access(access_token=access_token, require_subscription=require_subscription)
        except AccessError:
            raise NotFound()
        return order

    def _moyee_get_line_sudo(self, order, line_id):
        line = request.env["sale.order.line"].sudo().browse(int(line_id)).exists()
        if not line or line.order_id.id != order.id:
            raise NotFound()
        return line

    def _moyee_manage_url(self, order, params=None, access_token=None):
        base = f"/my/subscriptions/{order.id}/moyee/manage"
        if not params:
            params = {}
        if access_token:
            params["access_token"] = access_token
        if params:
            return base + "?" + urlencode(params)
        return base

    def _moyee_redirect_back(self, order, *, message=None, error=None, access_token=None):
        params = {}
        if message:
            params["moyee_message"] = message
        if error:
            params["moyee_error"] = error
        return request.redirect(self._moyee_manage_url(order, params=params or None, access_token=access_token))

    # ------------------------------------------------------------
    # Helpers (Plans) - UNIVERSAL + PORTAL SAFE
    # ------------------------------------------------------------
    def _moyee_get_all_plans_portal_safe(self, order):
        """
        Universal fallback:
        - Detect which plan field exists on sale.order (your DB uses plan_id)
        - Search plan model with portal-safe context (all companies, include inactive)
        """
        plan_field = False
        if hasattr(order, "_moyee_get_recurring_plan_field_name"):
            plan_field = order._moyee_get_recurring_plan_field_name()

        if not plan_field or plan_field not in order._fields:
            return request.env["ir.model"].browse([])

        plan_model = order._fields[plan_field].comodel_name
        Plan = request.env[plan_model].sudo()

        # portal-safe context
        company_ids = request.env["res.company"].sudo().search([]).ids
        Plan = Plan.with_context(allowed_company_ids=company_ids, active_test=False)

        # ✅ IMPORTANT: for sale.subscription.plan, company_id may exist (depends on build/customizations)
        # Default: global + order company
        domain = []
        if "company_id" in Plan._fields and getattr(order, "company_id", False):
            domain = [("company_id", "in", [False, order.company_id.id])]

        order_by = "sequence, name, id" if "sequence" in Plan._fields else "name, id"
        return Plan.search(domain, order=order_by)

    # ------------------------------------------------------------
    # Page
    # ------------------------------------------------------------
    @http.route(
        [
            "/my/subscriptions/<int:order_id>/moyee/manage",
            "/my/subscription/<int:order_id>/moyee/manage",
        ],
        type="http",
        auth="public",
        website=True,
    )
    def moyee_subscription_manage(self, order_id, access_token=None, **kw):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)

        next_date_field = order._moyee_get_subscription_next_date_field_name()
        next_date_value = order[next_date_field] if next_date_field else False

        available_products = order._moyee_get_portal_addable_products()

        # Try model-level logic first
        available_plans = order._moyee_get_portal_changeable_plans()

        # Hard fallback
        if not available_plans:
            available_plans = self._moyee_get_all_plans_portal_safe(order)

        # template-friendly plan info
        plan_field_name = False
        current_plan_id = False
        if hasattr(order, "_moyee_get_recurring_plan_field_name"):
            plan_field_name = order._moyee_get_recurring_plan_field_name()
        if plan_field_name and plan_field_name in order._fields and order[plan_field_name]:
            current_plan_id = order[plan_field_name].id

        _logger.info(
            "MOYEE portal manage: order=%s id=%s plan_field=%s current_plan_id=%s plans_count=%s",
            order.name,
            order.id,
            plan_field_name,
            current_plan_id,
            len(available_plans),
        )

        visible_lines = order.order_line.filtered(
            lambda l: l.display_type or (not l.x_moyee_is_removed and float(l.product_uom_qty or 0.0) > 0.0)
        )

        countries = request.env["res.country"].sudo().search([], order="name, id")

        # Detect paused state — Odoo 18 uses subscription_state = '4_paused'
        is_paused = False
        if "subscription_state" in order._fields and order.subscription_state == "4_paused":
            is_paused = True
        else:
            PAUSED_STATES = {"paused", "pause", "suspended", "suspend", "hold", "2_paused", "on_hold"}
            for sfield in ("subscription_state", "subscription_status"):
                if sfield in order._fields and order[sfield]:
                    sval = str(order[sfield]).lower()
                    if sval in PAUSED_STATES or any(p in sval for p in ("pause", "suspend", "hold")):
                        is_paused = True
                        break

        # Price filters
        prices = available_products.mapped("lst_price") or [0.0]
        min_price = min(prices)
        max_price = max(prices)

        values = {
            "sale_order": order,
            "order": order,
            "next_date_field": next_date_field,
            "next_date_value": next_date_value,
            "available_products": available_products,
            "available_plans": available_plans,
            "plan_field_name": plan_field_name,
            "current_plan_id": current_plan_id,
            "visible_lines": visible_lines,
            "countries": countries,
            "is_paused": is_paused,
            "min_price": min_price,
            "max_price": max_price,
            "moyee_message": kw.get("moyee_message"),
            "moyee_error": kw.get("moyee_error"),
        }
        return request.render("moyee_subscription_portal_manager.portal_subscription_manage", values)

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------
    @http.route(
        [
            "/my/subscriptions/<int:order_id>/change_interval",
            "/my/subscription/<int:order_id>/change_interval",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_change_interval(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            plan_id = int(post.get("plan_id") or 0)
            order.moyee_portal_change_interval(portal_user_id=request.env.user.id, plan_id=plan_id)
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Subscription interval updated successfully."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/change_address",
            "/my/subscription/<int:order_id>/change_address",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_change_address(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            shipping_vals = {
                "name": (post.get("ship_name") or "").strip(),
                "phone": (post.get("ship_phone") or "").strip(),
                "street": (post.get("ship_street") or "").strip(),
                "street2": (post.get("ship_street2") or "").strip(),
                "city": (post.get("ship_city") or "").strip(),
                "zip": (post.get("ship_zip") or "").strip(),
                "country_id": int(post.get("ship_country_id") or 0) or False,
            }

            # If "same as shipping" is checked, copy shipping vals to invoice vals
            same_as_shipping = post.get("same_as_shipping") == "1"
            if same_as_shipping:
                invoice_vals = dict(shipping_vals)
            else:
                invoice_vals = {
                    "name": (post.get("inv_name") or "").strip(),
                    "phone": (post.get("inv_phone") or "").strip(),
                    "street": (post.get("inv_street") or "").strip(),
                    "street2": (post.get("inv_street2") or "").strip(),
                    "city": (post.get("inv_city") or "").strip(),
                    "zip": (post.get("inv_zip") or "").strip(),
                    "country_id": int(post.get("inv_country_id") or 0) or False,
                }

            order.moyee_portal_change_address_full(
                portal_user_id=request.env.user.id,
                shipping_vals=shipping_vals,
                invoice_vals=invoice_vals,
            )
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Address updated successfully."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/push_delivery_date",
            "/my/subscription/<int:order_id>/push_delivery_date",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_push_delivery_date(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            new_date = (post.get("next_date") or "").strip()
            order.moyee_portal_push_next_date(portal_user_id=request.env.user.id, next_date=new_date)
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Next date updated successfully."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/add_product",
            "/my/subscription/<int:order_id>/add_product",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_add_product(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            product_id = int(post.get("product_id") or 0)
            qty = float(post.get("qty") or 0.0)
            order.moyee_portal_add_product(
                portal_user_id=request.env.user.id,
                product_id=product_id,
                qty=qty,
            )
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Product added successfully."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/line/<int:line_id>/remove",
            "/my/subscription/<int:order_id>/line/<int:line_id>/remove",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_remove_line(self, order_id, line_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        line = self._moyee_get_line_sudo(order, line_id)
        try:
            reason = (post.get("reason") or "").strip() or None
            line.action_moyee_soft_remove_portal(portal_user_id=request.env.user.id, reason=reason)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Product removed from subscription."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/line/<int:line_id>/update_qty",
            "/my/subscription/<int:order_id>/line/<int:line_id>/update_qty",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_update_line_qty(self, order_id, line_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            qty = float(post.get("qty") or 0.0)
            order.moyee_portal_update_line_qty(
                portal_user_id=request.env.user.id,
                line_id=line_id,
                qty=qty,
            )
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Quantity updated successfully."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/pause",
            "/my/subscription/<int:order_id>/pause",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_pause_subscription(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            order.moyee_portal_pause(portal_user_id=request.env.user.id)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Subscription paused successfully."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/resume",
            "/my/subscription/<int:order_id>/resume",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_resume_subscription(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            order.moyee_portal_resume(portal_user_id=request.env.user.id)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Subscription resumed successfully."), access_token=access_token)