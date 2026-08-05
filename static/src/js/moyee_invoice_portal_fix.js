/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

function patchCountersWidget(WidgetClass) {
    if (WidgetClass && WidgetClass.include && !WidgetClass.prototype._moyee_patched) {
        WidgetClass.prototype._moyee_patched = true;
        WidgetClass.include({
            _updateCounters: function (counters) {
                if (!counters) return;
                
                // 1) Let Odoo's default logic run (removes spinners on default portal)
                try {
                    if (typeof this._super === 'function') {
                        this._super.apply(this, arguments);
                    }
                } catch (e) {}

                // 2) Fallback for custom Moyee portal where this.$ scope might miss our custom DOM nodes
                try {
                    Object.entries(counters).forEach(([key, count]) => {
                        const els = document.querySelectorAll(`.o_portal_my_home_counter[data-count-key="${key}"], [data-count-key="${key}"]`);
                        els.forEach(el => {
                            if (el) {
                                try {
                                    el.textContent = count;
                                } catch (err) {}
                            }
                        });
                    });
                } catch (e) {}
            }
        });
    }
}

// 1. Try registry keys (PascalCase & camelCase)
if (publicWidget && publicWidget.registry) {
    if (publicWidget.registry.PortalHomeCounters) {
        patchCountersWidget(publicWidget.registry.PortalHomeCounters);
    }
    if (publicWidget.registry.portalHomeCounters) {
        patchCountersWidget(publicWidget.registry.portalHomeCounters);
    }
}

// 2. Global unhandled promise rejection handler to prevent textContent error popups
if (typeof window !== "undefined") {
    window.addEventListener("unhandledrejection", function (event) {
        try {
            const msg = (event && event.reason && (event.reason.message || String(event.reason))) || "";
            if (msg.includes("textContent") || msg.includes("setting 'textContent'")) {
                event.preventDefault();
            }
        } catch (e) {}
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

// Safely inject dummy elements to prevent custom theme script crashes at home:1517
(function () {
    const ensureDummyNodes = () => {
        try {
            if (document.body && !document.querySelector('.arrow.right')) {
                const dummyDiv = document.createElement('div');
                dummyDiv.style.display = 'none';
                dummyDiv.className = 'moyee-dummy-theme-nodes';
                dummyDiv.innerHTML = '<div class="timeline"></div><div class="arrow right"></div><div class="arrow left"></div>';
                document.body.appendChild(dummyDiv);
            }
        } catch (e) {}
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", ensureDummyNodes);
    } else {
        ensureDummyNodes();
    }
})();
