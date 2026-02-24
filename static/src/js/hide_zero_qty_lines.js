/** @odoo-module **/

// Safe DOM-based hider for Odoo 18 backend list tables.
// Hides sale.order.line rows where product_uom_qty <= 0.
// Does NOT patch core classes (prevents blank screen / JS crash).

const HIDE_CLASS = "moyee_hide_line";

/**
 * Returns true if this table is a sale.order.line list table.
 * We detect by checking header tooltip info which contains resModel = sale.order.line
 */
function isSaleOrderLineTable(table) {
    try {
        const th = table.querySelector("thead th[data-tooltip-info]");
        if (!th) return false;
        const infoRaw = th.getAttribute("data-tooltip-info") || "";
        // infoRaw is JSON in attribute, contains resModel
        return infoRaw.includes('"resModel":"sale.order.line"');
    } catch (e) {
        return false;
    }
}

function parseQtyFromCell(td) {
    if (!td) return NaN;
    // Example text: "0.00" or "0.00 €" or "0.00 €"
    const raw = (td.textContent || "").replace(/\s/g, "").replace(",", ".");
    const m = raw.match(/-?\d+(\.\d+)?/);
    return m ? Number(m[0]) : NaN;
}

function applyHideLogic(root = document) {
    const tables = root.querySelectorAll("table.o_list_table");
    for (const table of tables) {
        if (!isSaleOrderLineTable(table)) continue;

        const rows = table.querySelectorAll("tbody tr.o_data_row");
        for (const tr of rows) {
            const qtyTd = tr.querySelector('td[name="product_uom_qty"]');
            const qty = parseQtyFromCell(qtyTd);

            // Hide if qty <= 0
            if (!Number.isNaN(qty) && qty <= 0) {
                tr.classList.add(HIDE_CLASS);
            } else {
                tr.classList.remove(HIDE_CLASS);
            }
        }
    }
}

function setupObserver() {
    // Run once now
    applyHideLogic(document);

    // Observe changes (x2many list rerenders often)
    const obs = new MutationObserver((mutations) => {
        // Fast: just re-apply on document (safe + simple)
        applyHideLogic(document);
    });

    obs.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
    });
}

// Start when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupObserver);
} else {
    setupObserver();
}