/** @odoo-module **/

console.log("✅ Moyee hide_zero_qty_lines loaded");

const HIDE_CLASS = "moyee_hide_line";

function parseQty(td) {
    if (!td) return NaN;
    // "0.00", "0.00 €", "0,00"
    const raw = (td.textContent || "").trim().replace(/\s/g, "").replace(",", ".");
    const m = raw.match(/-?\d+(\.\d+)?/);
    return m ? Number(m[0]) : NaN;
}

function hideRemovedRows(root = document) {
    const rows = root.querySelectorAll("tr.o_data_row");
    for (const tr of rows) {
        const hasQty = tr.querySelector('td[name="product_uom_qty"]');
        if (!hasQty) continue;

        let shouldHide = false;

        // 1. Check if marked as soft-removed (x_moyee_is_removed)
        const removedTd = tr.querySelector('td[name="x_moyee_is_removed"]');
        if (removedTd) {
            const checkbox = removedTd.querySelector('input[type="checkbox"]');
            const isChecked = checkbox ? checkbox.checked : false;
            const valText = (removedTd.textContent || "").trim().toLowerCase();
            const isTrueText = valText === "true" || valText === "1" || valText === "yes";
            if (isChecked || isTrueText) {
                shouldHide = true;
            }
        }

        // 2. Check if quantity is 0 or less
        if (!shouldHide) {
            const qtyTd = tr.querySelector('td[name="product_uom_qty"]');
            if (qtyTd) {
                const qty = parseQty(qtyTd);
                if (!Number.isNaN(qty) && qty <= 0) {
                    shouldHide = true;
                }
            }
        }

        if (shouldHide) {
            tr.classList.add(HIDE_CLASS);
        } else {
            tr.classList.remove(HIDE_CLASS);
        }
    }
}

function start() {
    // initial
    hideRemovedRows(document);

    // keep applying on list rerenders
    const obs = new MutationObserver(() => hideRemovedRows(document));
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}