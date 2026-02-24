/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

patch(ListRenderer.prototype, "moyee_subscription_portal_manager.hide_zero_qty_lines", {
    getRowClass(record) {
        // keep existing classes
        const cls = (super.getRowClass && super.getRowClass(record)) || "";

        try {
            // We only target sale.order.line rows
            if (record?.resModel === "sale.order.line") {
                const qty = Number(record.data?.product_uom_qty || 0);
                const removed = Boolean(record.data?.x_moyee_is_removed);

                // Hide if qty is 0 OR flagged removed
                if (qty <= 0 || removed) {
                    return `${cls} moyee_hide_line`;
                }
            }
        } catch (e) {
            // fail-safe: never block rendering if something changes
        }
        return cls;
    },
});