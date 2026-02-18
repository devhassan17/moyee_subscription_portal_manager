# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError

class MoyeeSubscriptionPortal(http.Controller):

    def _get_subscription_or_404(self, subscription_id):
        sub = request.env["sale.subscription"].sudo().browse(int(subscription_id))
        if not sub.exists():
            return None
        # Access check: portal user must own it (or backend user)
        try:
            sub.with_user(request.env.user).moyee_check_portal_access()
        except Exception:
            return None
        return sub

    @http.route(["/my/subscriptions/<int:subscription_id>/moyee/change_product"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def moyee_portal_change_product(self, subscription_id, **post):
        sub = self._get_subscription_or_404(subscription_id)
        if not sub:
            return request.not_found()

        if not sub.allow_portal_product_change:
            return request.render("moyee_subscription_portal_manager.moyee_portal_error", {
                "error": _("Product change is not allowed for this subscription."),
            })

        if request.httprequest.method == "POST":
            old_line_id = int(post.get("old_line_id"))
            new_product_id = int(post.get("new_product_id"))
            effective_date = post.get("effective_date")

            old_line = request.env["sale.subscription.line"].sudo().browse(old_line_id)
            if not old_line.exists() or old_line.subscription_id.id != sub.id:
                return request.not_found()

            # End old line and add new line (direct action model)
            old_line.moyee_end_line(note="Portal product change", source="portal")
            request.env["sale.subscription.line"].sudo().create({
                "subscription_id": sub.id,
                "product_id": new_product_id,
                "quantity": old_line.quantity or 1.0,
                "is_active_for_billing": True,
                "start_date": effective_date or False,
                "change_source": "portal",
                "change_note": "Portal product change",
            })
            sub.sudo().message_post(body=_("Customer changed product from portal."))
            return request.redirect(f"/my/subscriptions/{sub.id}")

        # GET: show simple form
        products = request.env["product.product"].sudo().search([("sale_ok", "=", True)], limit=50)
        return request.render("moyee_subscription_portal_manager.moyee_portal_change_product", {
            "subscription": sub,
            "lines": sub.recurring_invoice_line_ids,
            "products": products,
        })
