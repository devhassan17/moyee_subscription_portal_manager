/** @odoo-module **/

const HIDE_CLASS = "moyee_hide_line";

function parseQty(td) {
    if (!td) return NaN;
    // "0.00", "0.00 €", "0,00"
    const raw = (td.textContent || "").trim().replace(/\s/g, "").replace(",", ".");
    const m = raw.match(/-?\d+(\.\d+)?/);
    return m ? Number(m[0]) : NaN;
}

function hideZeroQtyRows(root = document) {
    const rows = root.querySelectorAll("tr.o_data_row");
    for (const tr of rows) {
        const qtyTd = tr.querySelector('td[name="product_uom_qty"]');
        if (!qtyTd) continue; // not a sale.order.line list row (or not the list we want)

        const qty = parseQty(qtyTd);
        if (!Number.isNaN(qty) && qty <= 0) {
            tr.classList.add(HIDE_CLASS);
        } else {
            tr.classList.remove(HIDE_CLASS);
        }
    }
}

function start() {
    // initial
    hideZeroQtyRows(document);

    // keep applying on list rerenders
    const obs = new MutationObserver(() => hideZeroQtyRows(document));
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}