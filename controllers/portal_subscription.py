from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError


class PortalSubscriptionController(http.Controller):

    @http.route(
        ["/my/subscription/<int:order_id>/line/<int:line_id>/remove"],
        type="http",
        auth="public",
        website=True,
        csrf=False,
    )
    def portal_subscription_line_remove(self, order_id, line_id, access_token=None, **kwargs):
        order_sudo = request.env["sale.order"].sudo().browse(order_id)
        if not order_sudo.exists():
            return request.not_found()

        # Portal access check (token or logged-in owner)
        try:
            order_sudo._document_check_access("read", access_token=access_token)
        except (AccessError, Exception):
            return request.redirect("/my")

        line_sudo = request.env["sale.order.line"].sudo().browse(line_id)
        if not line_sudo.exists() or line_sudo.order_id.id != order_sudo.id:
            return request.redirect(order_sudo.get_portal_url(access_token=access_token))

        # Mark as removed + set qty 0
        line_sudo.write({
            "x_moyee_is_removed": True,
            "product_uom_qty": 0.0,
        })

        return request.redirect(order_sudo.get_portal_url(access_token=access_token))