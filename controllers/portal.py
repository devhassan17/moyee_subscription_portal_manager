# File: moyee_subscription_portal_manager/controllers/portal.py
import logging
from urllib.parse import urlencode

from odoo import _, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from werkzeug.exceptions import NotFound


_logger = logging.getLogger(__name__)


class MoyeeSubscriptionPortal(http.Controller):
    """Portal-side subscription management (secure write-through controllers)."""

    # ------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------
    def _moyee_get_order_sudo(self, order_id, *, require_subscription=True):
        """Return the sale.order in sudo() or raise 404."""
        order = request.env["sale.order"].sudo().browse(int(order_id)).exists()
        if not order:
            raise NotFound()

        # Explicit ownership checks (DO NOT rely on sudo() alone).
        try:
            order._moyee_portal_check_access(require_subscription=require_subscription)
        except AccessError:
            raise NotFound()
        return order

    def _moyee_get_line_sudo(self, order, line_id):
        line = request.env["sale.order.line"].sudo().browse(int(line_id)).exists()
        if not line or line.order_id.id != order.id:
            raise NotFound()
        return line

    def _moyee_manage_url(self, order, params=None):
        base = f"/my/subscriptions/{order.id}/moyee/manage"
        if params:
            return base + "?" + urlencode(params)
        return base

    def _moyee_redirect_back(self, order, *, message=None, error=None):
        params = {}
        if message:
            params["moyee_message"] = message
        if error:
            params["moyee_error"] = error
        return request.redirect(self._moyee_manage_url(order, params=params or None))

    # ------------------------------------------------------------
    # Page
    # ------------------------------------------------------------
    @http.route(
        [
            "/my/subscriptions/<int:order_id>/moyee/manage",
            "/my/subscription/<int:order_id>/moyee/manage",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def moyee_subscription_manage(self, order_id, **kw):
        order = self._moyee_get_order_sudo(order_id, require_subscription=True)

        user = request.env.user
        partner = user.partner_id.commercial_partner_id

        addresses = request.env["res.partner"].sudo().search(
            [("id", "child_of", [partner.id])],
            order="type, name, id",
        )

        next_date_field = order._moyee_get_subscription_next_date_field_name()
        next_date_value = order[next_date_field] if next_date_field else False

        available_products = order._moyee_get_portal_addable_products()

        # Visible lines are filtered server-side
        visible_lines = order.order_line.filtered(
            lambda l: l.display_type or (not l.x_moyee_is_removed and l.product_uom_qty > 0)
        )

        values = {
            "sale_order": order,  # keep 'sale_order' naming for consistency with base portal templates
            "order": order,
            "addresses": addresses,
            "next_date_field": next_date_field,
            "next_date_value": next_date_value,
            "available_products": available_products,
            "visible_lines": visible_lines,
            "moyee_message": kw.get("moyee_message"),
            "moyee_error": kw.get("moyee_error"),
        }
        return request.render("moyee_subscription_portal_manager.portal_subscription_manage", values)

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------
    @http.route(
        [
            "/my/subscriptions/<int:order_id>/change_address",
            "/my/subscription/<int:order_id>/change_address",
        ],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_change_address(self, order_id, **post):
        order = self._moyee_get_order_sudo(order_id, require_subscription=True)
        try:
            shipping_id = int(post.get("shipping_partner_id") or 0) or False
            invoice_id = int(post.get("invoice_partner_id") or 0) or False
            order.moyee_portal_change_address(
                portal_user_id=request.env.user.id,
                shipping_partner_id=shipping_id,
                invoice_partner_id=invoice_id,
            )
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e))
        return self._moyee_redirect_back(order, message=_("Address updated successfully."))

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/push_delivery_date",
            "/my/subscription/<int:order_id>/push_delivery_date",
        ],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_push_delivery_date(self, order_id, **post):
        order = self._moyee_get_order_sudo(order_id, require_subscription=True)
        try:
            new_date = (post.get("next_date") or "").strip()
            order.moyee_portal_push_next_date(portal_user_id=request.env.user.id, next_date=new_date)
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e))
        return self._moyee_redirect_back(order, message=_("Next date updated successfully."))

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/add_product",
            "/my/subscription/<int:order_id>/add_product",
        ],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_add_product(self, order_id, **post):
        order = self._moyee_get_order_sudo(order_id, require_subscription=True)
        try:
            product_id = int(post.get("product_id") or 0)
            qty = float(post.get("qty") or 0.0)
            order.moyee_portal_add_product(
                portal_user_id=request.env.user.id,
                product_id=product_id,
                qty=qty,
            )
        except (AccessError, UserError, ValidationError, ValueError) as e:
            return self._moyee_redirect_back(order, error=str(e))
        return self._moyee_redirect_back(order, message=_("Product added successfully."))

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/line/<int:line_id>/remove",
            "/my/subscription/<int:order_id>/line/<int:line_id>/remove",
        ],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_remove_line(self, order_id, line_id, **post):
        order = self._moyee_get_order_sudo(order_id, require_subscription=True)
        line = self._moyee_get_line_sudo(order, line_id)

        try:
            reason = (post.get("reason") or "").strip() or None
            line.action_moyee_soft_remove_portal(portal_user_id=request.env.user.id, reason=reason)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e))

        return self._moyee_redirect_back(order, message=_("Product removed from subscription."))

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/pause",
            "/my/subscription/<int:order_id>/pause",
        ],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_pause_subscription(self, order_id, **post):
        order = self._moyee_get_order_sudo(order_id, require_subscription=True)
        try:
            order.moyee_portal_pause(portal_user_id=request.env.user.id)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e))
        return self._moyee_redirect_back(order, message=_("Subscription paused successfully."))

    @http.route(
        [
            "/my/subscriptions/<int:order_id>/resume",
            "/my/subscription/<int:order_id>/resume",
        ],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def moyee_resume_subscription(self, order_id, **post):
        order = self._moyee_get_order_sudo(order_id, require_subscription=True)
        try:
            order.moyee_portal_resume(portal_user_id=request.env.user.id)
        except (AccessError, UserError, ValidationError) as e:
            return self._moyee_redirect_back(order, error=str(e))
        return self._moyee_redirect_back(order, message=_("Subscription resumed successfully."))
