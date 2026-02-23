from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError


class MoyeeSubscriptionPortal(http.Controller):

    def _get_order(self, order_id):
        order = request.env["sale.order"].sudo().browse(order_id)
        if not order.exists():
            raise AccessError("Subscription not found.")
        order._check_portal_access()
        return order

    @http.route(
        "/my/subscription/<int:order_id>/line/<int:line_id>/remove",
        type="http", auth="user", website=True
    )
    def remove_line(self, order_id, line_id, **post):
        order = self._get_order(order_id)
        line = request.env["sale.order.line"].sudo().browse(line_id)
        if line.order_id != order:
            raise AccessError("Invalid line.")

        line.action_moyee_soft_remove(
            reason=post.get("reason")
        )
        return request.redirect(f"/my/subscription/{order_id}")

    @http.route(
        "/my/subscription/<int:order_id>/line/<int:line_id>/update_qty",
        type="http", auth="user", website=True, methods=["POST"]
    )
    def update_qty(self, order_id, line_id, **post):
        order = self._get_order(order_id)
        line = request.env["sale.order.line"].sudo().browse(line_id)
        qty = float(post.get("quantity", 1))
        if qty <= 0:
            line.action_moyee_soft_remove()
        else:
            line.write({"product_uom_qty": qty})
        return request.redirect(f"/my/subscription/{order_id}")