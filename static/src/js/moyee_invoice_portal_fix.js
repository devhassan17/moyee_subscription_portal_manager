/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

// Safely patch PortalHomeCounters widget to prevent null textContent errors on standard portal pages
if (publicWidget && publicWidget.registry && publicWidget.registry.PortalHomeCounters) {
    publicWidget.registry.PortalHomeCounters.include({
        _updateCounters: function (counters) {
            if (!counters) return this._super.apply(this, arguments);
            try {
                Object.entries(counters).forEach(([key, count]) => {
                    const els = document.querySelectorAll(`.o_portal_my_home_counter[data-count-key="${key}"], [data-count-key="${key}"]`);
                    els.forEach(el => {
                        if (el) {
                            el.textContent = count;
                        }
                    });
                });
            } catch (e) {
                // Ignore fallback safe checks
            }
        }
    });
}

// Self-executing DOM listener to remove 'by Post' option from invoice_sending_method dropdown
(function () {
    const removePostOption = () => {
        try {
            const select = document.querySelector('select[name="invoice_sending_method"]');
            if (select && select.options) {
                Array.from(select.options).forEach(opt => {
                    if (opt && (opt.value === 'post' || (opt.textContent && opt.textContent.toLowerCase().includes('post')))) {
                        try { opt.remove(); } catch (e) {}
                    }
                });
            }
        } catch (err) {}
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", removePostOption);
    } else {
        removePostOption();
    }
})();
