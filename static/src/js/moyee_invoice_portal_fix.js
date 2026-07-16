// Self-executing robust DOM listener to remove 'by Post' option from invoice_sending_method dropdown
(function () {
    const removePostOption = () => {
        const select = document.querySelector('select[name="invoice_sending_method"]');
        if (select) {
            // Remove by value
            const optionVal = select.querySelector('option[value="post"]');
            if (optionVal) {
                optionVal.remove();
            }
            // Remove by text matching "post" case-insensitive
            Array.from(select.options).forEach(opt => {
                if (opt.value === 'post' || (opt.textContent && opt.textContent.toLowerCase().includes('post'))) {
                    opt.remove();
                }
            });
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", removePostOption);
    } else {
        removePostOption();
    }

    // Observe changes to the DOM (for cases when Odoo re-renders or updates elements dynamically)
    const observer = new MutationObserver(removePostOption);
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();
