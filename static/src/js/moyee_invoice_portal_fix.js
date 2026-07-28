// Self-executing robust DOM listener to remove 'by Post' option from invoice_sending_method dropdown
(function () {
    const removePostOption = () => {
        try {
            const select = document.querySelector('select[name="invoice_sending_method"]');
            if (select && select.options) {
                // Remove by value
                const optionVal = select.querySelector('option[value="post"]');
                if (optionVal) {
                    try { optionVal.remove(); } catch (e) {}
                }
                // Remove by text matching "post" case-insensitive
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

    // Observe changes to the DOM safely
    if (typeof MutationObserver !== 'undefined' && document.documentElement) {
        const observer = new MutationObserver(() => {
            try { removePostOption(); } catch (e) {}
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
    }
})();
