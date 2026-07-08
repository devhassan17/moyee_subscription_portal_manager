/** @odoo-module **/

const HIDE_CLASS = "moyee_hide_line";

function parseQty(td) {
    if (!td) return NaN;
    // "0.00", "0.00 €", "0,00"
    const raw = (td.textContent || "").trim().replace(/\s/g, "").replace(",", ".");
    const m = raw.match(/-?\d+(\.\d+)?/);
    return m ? Number(m[0]) : NaN;
}

function hideRemovedRows(root = document) {
    if (!root.querySelector('td[name="x_moyee_is_removed"]')) {
        return;
    }
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

function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function start() {
    // initial
    hideRemovedRows(document);

    // keep applying on list rerenders (debounced for performance)
    const debouncedHide = debounce(() => hideRemovedRows(document), 100);
    const obs = new MutationObserver(debouncedHide);
    obs.observe(document.body, { childList: true, subtree: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}