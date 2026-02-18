# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request

class MoyeeSubscriptionPortal(http.Controller):

    def _get_order_or_404(self, order_id):
        order = request.env["sale.order"].sudo().browse(int(order_id))
        if not order.exists():
            return None
        # check portal ownership (or backend)
        try:
            order.with_user(request.env.user).moyee_check_portal_access()
        except Exception:
            return None
        return order

    @http.route(["/my/subscriptions/<int:order_id>/moyee/change_product"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def moyee_portal_change_product(self, order_id, **post):
        order = self._get_order_or_404(order_id)
        if not order:
            return request.not_found()

        if not order.allow_portal_product_change:
            return request.render("moyee_subscription_portal_manager.moyee_portal_error", {
                "error": _("Product change is not allowed for this subscription."),
            })

        if request.httprequest.method == "POST":
            old_line_id = int(post.get("old_line_id"))
            new_product_id = int(post.get("new_product_id"))
            effective_date = post.get("effective_date") or False

            old_line = request.env["sale.order.line"].sudo().browse(old_line_id)
            if not old_line.exists() or old_line.order_id.id != order.id:
                return request.not_found()

            old_line.moyee_end_line(note="Portal product change", source="portal")
            request.env["sale.order.line"].sudo().create({
                "order_id": order.id,
                "product_id": new_product_id,
                "product_uom_qty": old_line.product_uom_qty or 1.0,
                "is_active_for_billing": True,
                "start_date": effective_date,
                "change_source": "portal",
                "change_note": "Portal product change",
            })
            order.sudo().message_post(body=_("Customer changed product from portal."))
            return request.redirect(f"/my/subscriptions/{order.id}")

        products = request.env["product.product"].sudo().search([("sale_ok", "=", True)], limit=100)
        return request.render("moyee_subscription_portal_manager.moyee_portal_change_product", {
            "order": order,
            "lines": order.order_line,
            "products": products,
        })
