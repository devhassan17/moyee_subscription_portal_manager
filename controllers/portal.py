# File: moyee_subscription_portal_manager/controllers/portal.py
import logging
from urllib.parse import urlencode

from odoo import _, http, fields
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
        next_date_field = False
        next_date_value = False
        current_plan_display = ""
        current_plan_id = False
        is_paused = False
        available_plans = SaleOrder.browse()
        available_products = request.env["product.product"].browse()
        countries = request.env["res.country"].browse()
        min_price = 0.0
        max_price = 0.0

        current_website = getattr(request, "website", False)
        current_company_id = current_website and current_website.company_id.id or False

        # Find the user's active subscription order
        sub_domain = [
            ("partner_id.commercial_partner_id", "=", commercial.id),
            ("state", "in", ("sale", "done")),
        ]
        if current_company_id:
            sub_domain.append(("company_id", "=", current_company_id))
        # Odoo 18: subscription_state in active states
        if "subscription_state" in SaleOrder._fields:
            sub_domain.append(("subscription_state", "in", ("3_progress", "4_paused", "2_renewal")))
        elif "is_subscription" in SaleOrder._fields:
            sub_domain.append(("is_subscription", "=", True))

        subscriptions = SaleOrder.search(sub_domain, order="id desc")
        if subscriptions:
            sub_id = kw.get("sub_id")
            if sub_id:
                try:
                    requested_sub = subscriptions.filtered(lambda s: s.id == int(sub_id))
                    if requested_sub:
                        active_subscription = requested_sub[0]
                    else:
                        active_subscription = subscriptions[0]
                except Exception:
                    active_subscription = subscriptions[0]
            else:
                active_subscription = subscriptions[0]
            has_subscription = True

            # Visible lines (include active lines with quantity > 0)
            visible_lines = active_subscription.order_line.filtered(
                lambda l: (
                    l.display_type
                    or (not l.x_moyee_is_removed and float(l.product_uom_qty or 0.0) > 0.0)
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

            # Hard fallback for plans
            if not available_plans and plan_field_name and plan_field_name in active_subscription._fields:
                try:
                    plan_model = active_subscription._fields[plan_field_name].comodel_name
                    Plan = request.env[plan_model].sudo()
                    company_ids = request.env["res.company"].sudo().search([]).ids
                    Plan = Plan.with_context(allowed_company_ids=company_ids, active_test=False)
                    domain = []
                    if "company_id" in Plan._fields and getattr(active_subscription, "company_id", False):
                        domain = [("company_id", "in", [False, active_subscription.company_id.id])]
                    order_by = "sequence, name, id" if "sequence" in Plan._fields else "name, id"
                    available_plans = Plan.search(domain, order=order_by)
                except Exception:
                    pass

            # Paused state
            if "subscription_state" in active_subscription._fields and active_subscription.subscription_state == "4_paused":
                is_paused = True
            else:
                PAUSED_STATES = {"paused", "pause", "suspended", "suspend", "hold", "2_paused", "on_hold"}
                for sfield in ("subscription_state", "subscription_status"):
                    if sfield in active_subscription._fields and active_subscription[sfield]:
                        sval = str(active_subscription[sfield]).lower()
                        if sval in PAUSED_STATES or any(p in sval for p in ("pause", "suspend", "hold")):
                            is_paused = True
                            break

            # Available products (for "Add product" popup)
            try:
                available_products = active_subscription._moyee_get_portal_addable_products()
            except Exception:
                pass

            # Countries (for "Change address" popup)
            countries = request.env["res.country"].sudo().search([], order="name, id")

            # Price filters
            if available_products:
                prices = available_products.mapped("lst_price") or [0.0]
                min_price = min(prices)
                max_price = max(prices)

        # ── Recent orders ──
        order_domain = [
            ("partner_id.commercial_partner_id", "=", commercial.id),
            ("state", "in", ("sale", "done", "cancel")),
        ]
        if current_company_id:
            order_domain.append(("company_id", "=", current_company_id))
        recent_orders = SaleOrder.search(order_domain, order="date_order desc, id desc")

        # ── Recent invoices ──
        AccountMove = request.env["account.move"].sudo()
        inv_domain = [
            ("partner_id.commercial_partner_id", "=", commercial.id),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
        ]
        if current_company_id:
            inv_domain.append(("company_id", "=", current_company_id))
        recent_invoices = AccountMove.search(inv_domain, order="invoice_date desc, id desc")

        # ── Portal FAQs ──
        PortalFaq = request.env["moyee.portal.faq"].sudo()
        faqs = PortalFaq.search([("is_active", "=", True)])

        # ── Portal Brew Guides ──
        PortalBrewGuide = request.env["moyee.portal.brew.guide"].sudo()
        brew_guides = PortalBrewGuide.search([("is_active", "=", True)])

        # ── Flash messages from redirect ──
        moyee_home_message = kw.get("moyee_message", "")
        moyee_home_error = kw.get("moyee_error", "")

        # Fetch configuration parameters
        ICP = request.env["ir.config_parameter"].sudo()

        def _get_bool(param_name, default=True):
            val = ICP.get_param(param_name, str(default))
            return val.lower() in ("true", "1", "yes")

        moyee_config = {
            "primary_color": ICP.get_param("moyee_subscription_portal_manager.primary_color", "#E91E8C"),
            "secondary_color": ICP.get_param("moyee_subscription_portal_manager.secondary_color", "#FCE4F3"),
            "font_family": ICP.get_param("moyee_subscription_portal_manager.font_family", "system-ui"),
            "show_subscription": _get_bool("moyee_subscription_portal_manager.show_subscription", True),
            "show_overview": _get_bool("moyee_subscription_portal_manager.show_overview", True),
            "show_orders": _get_bool("moyee_subscription_portal_manager.show_orders", True),
            "show_invoices": _get_bool("moyee_subscription_portal_manager.show_invoices", True),
            "show_faq": _get_bool("moyee_subscription_portal_manager.show_faq", True),
            "show_inspire": _get_bool("moyee_subscription_portal_manager.show_inspire", True),
            "show_taf": _get_bool("moyee_subscription_portal_manager.show_taf", True),
            "show_brew_guides": _get_bool("moyee_subscription_portal_manager.show_brew_guides", True),
            "brew_guides_all_url": ICP.get_param("moyee_subscription_portal_manager.brew_guides_all_url", "/shop"),
            "show_sidebar_profile": _get_bool("moyee_subscription_portal_manager.show_sidebar_profile", True),
            "show_sidebar_upsell": _get_bool("moyee_subscription_portal_manager.show_sidebar_upsell", True),
            "show_sidebar_support": _get_bool("moyee_subscription_portal_manager.show_sidebar_support", True),
            "upsell_cta_url": ICP.get_param("moyee_subscription_portal_manager.upsell_cta_url", "/shop"),
            "support_email": ICP.get_param("moyee_subscription_portal_manager.support_email", "hello@moyeecoffee.com"),
            "inspire_eyebrow": ICP.get_param("moyee_subscription_portal_manager.inspire_eyebrow", "Do you know where your coffee comes from?"),
            "inspire_title": ICP.get_param("moyee_subscription_portal_manager.inspire_title", "Your coffee comes from Ethiopia"),
            "inspire_body": ICP.get_param("moyee_subscription_portal_manager.inspire_body", "Your Moyee coffee comes from small farmers in the Kaffa forest in Ethiopia. They receive a fair price — thanks to you."),
            "inspire_btn1_text": ICP.get_param("moyee_subscription_portal_manager.inspire_btn1_text", "Read the story"),
            "inspire_btn1_url": ICP.get_param("moyee_subscription_portal_manager.inspire_btn1_url", "/radical-impact-coffee"),
            "inspire_btn2_text": ICP.get_param("moyee_subscription_portal_manager.inspire_btn2_text", "Browse our coffee"),
            "inspire_btn2_url": ICP.get_param("moyee_subscription_portal_manager.inspire_btn2_url", "/shop"),
        }

        # Variant map for front-end cascading selections
        import json
        variant_map = []
        if active_subscription:
            try:
                # Include both available_products and any products currently on the subscription lines
                existing_products = active_subscription.order_line.filtered(lambda l: not l.x_moyee_is_removed).mapped("product_id")
                all_possible_products = available_products | existing_products
                for p in all_possible_products:
                    grind, weight = active_subscription._moyee_extract_product_metadata(p)
                    tmpl_name = p.product_tmpl_id.name or ''
                    tmpl_name = tmpl_name.replace('(Subscription)', '').replace('(subscription)', '').replace('(SUBSCRIPTION)', '')
                    import re
                    tmpl_name = re.sub(r'(?i)\b(1\s*kg|250\s*g(ram)?|25\s*caps(ules)?)\b', '', tmpl_name).strip()
                    variant_map.append({
                        "id": p.id,
                        "tmpl_id": p.product_tmpl_id.id,
                        "tmpl_name": tmpl_name,
                        "grind": grind,
                        "weight": weight,
                    })
            except Exception:
                pass
        variant_map_json = json.dumps(variant_map)
        # Precompute pause options resume dates
        pause_options = []
        base_date = next_date_value or fields.Date.today()
        if base_date:
            from dateutil.relativedelta import relativedelta
            for months in [1, 2, 3, 6]:
                resume_date = base_date + relativedelta(months=months)
                day = resume_date.day
                month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
                formatted_date = f"{day} {month_names[resume_date.month - 1]} {resume_date.year}"
                pause_options.append({
                    "months": months,
                    "date_str": resume_date.strftime('%Y-%m-%d'),
                    "display": f"{months} month{'s' if months > 1 else ''} (resumes {formatted_date})"
                })

        values.update({
            "partner": partner,
            "has_subscription": has_subscription,
            "active_subscription": active_subscription,
            "visible_lines": visible_lines,
            "next_date_field": next_date_field,
            "next_date_value": next_date_value,
            "current_plan_display": current_plan_display,
            "current_plan_id": current_plan_id,
            "is_paused": is_paused,
            "available_plans": available_plans,
            "available_products": available_products,
            "countries": countries,
            "min_price": min_price,
            "max_price": max_price,
            "recent_orders": recent_orders,
            "recent_invoices": recent_invoices,
            "subscriptions": subscriptions,
            "faqs": faqs,
            "brew_guides": brew_guides,
            "moyee_home_message": moyee_home_message,
            "moyee_home_error": moyee_home_error,
            "moyee_config": moyee_config,
            "variant_map_json": variant_map_json,
            "pause_options": pause_options,
        })
        return values

    @http.route(["/my", "/my/home"], type="http", auth="user", website=True)
    def home(self, **kw):
        # Check if custom redesign is enabled for the current company
        company = getattr(request, "website", None) and request.website.company_id or request.env.company
        enable_redesign = company.moyee_enable_portal_redesign if "moyee_enable_portal_redesign" in company._fields else True
        if not enable_redesign:
            return super().home(**kw)

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
        if access_token:
            params["access_token"] = access_token
        # Redirect back to /my/home instead of the manage page
        return request.redirect("/my/home?" + urlencode(params))

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
            "/my/subscriptions/<int:order_id>/line/<int:line_id>/edit_product",
            "/my/subscription/<int:order_id>/line/<int:line_id>/edit_product",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_edit_line_product(self, order_id, line_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            template_id = int(post.get("coffee_type") or 0)
            grind = (post.get("grind") or "").strip()
            weight = (post.get("weight") or "").strip()
            order.moyee_portal_edit_line_product(
                portal_user_id=request.env.user.id,
                line_id=line_id,
                template_id=template_id,
                grind=grind,
                weight=weight,
            )
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Product updated successfully."), access_token=access_token)

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
            pause_until_date = post.get("pause_until_date")
            order.moyee_portal_pause(portal_user_id=request.env.user.id, pause_until_date=pause_until_date)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Subscription paused successfully."), access_token=access_token)

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/skip_delivery",
            "/my/subscription/<int:order_id>/skip_delivery",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_skip_delivery(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            order.moyee_portal_skip_delivery(portal_user_id=request.env.user.id)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Subscription delivery skipped successfully."), access_token=access_token)

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

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/cancel",
            "/my/subscription/<int:order_id>/cancel",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_cancel_subscription(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token, require_subscription=True)
        try:
            reason = post.get("reason")
            order.moyee_portal_close(portal_user_id=request.env.user.id, reason=reason)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e), access_token=access_token)
        return self._moyee_redirect_back(order, message=_("Subscription cancelled successfully."), access_token=access_token)

    @http.route(
        [
            "/my/orders/<int:order_id>/reorder",
        ],
        type="http",
        auth="public",
        website=True,
        methods=["POST", "GET"],
        csrf=True,
    )
    def moyee_order_reorder(self, order_id, access_token=None, **post):
        order = self._moyee_get_order_sudo(order_id, access_token=access_token)
        if not order:
            return request.redirect("/my/home")
        
        # Safe ecommerce cart lookup/create
        if hasattr(request.website, "sale_get_order"):
            cart = request.website.sale_get_order(force_create=True)
            for line in order.order_line.filtered(lambda l: not l.display_type and l.product_id.sale_ok):
                cart._cart_update(
                    product_id=line.product_id.id,
                    add_qty=line.product_uom_qty,
                )
            return request.redirect("/shop/checkout")
        
        return request.redirect("/my/home")