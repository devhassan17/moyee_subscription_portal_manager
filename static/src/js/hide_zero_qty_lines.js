// /** @odoo-module **/

// import { patch } from "@web/core/utils/patch";
// import { ListRenderer } from "@web/views/list/list_renderer";

// patch(ListRenderer.prototype, "moyee_subscription_portal_manager.hide_zero_qty_lines", {
//     getRowClass(record) {
//         // ✅ In Odoo patching, call original via this._super()
//         const cls = this._super(record) || "";

//         try {
//             // Only target sale.order.line rows
//             if (record?.resModel === "sale.order.line") {
//                 const qty = Number(record.data?.product_uom_qty || 0);
//                 const removed = Boolean(record.data?.x_moyee_is_removed);

//                 // Hide if qty is 0 OR flagged removed
//                 if (qty <= 0 || removed) {
//                     return `${cls} moyee_hide_line`;
//                 }
//             }
//         } catch (e) {
//             // Fail-safe: don't break UI
//         }
//         return cls;
//     },
// });