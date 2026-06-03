/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.MoyeeProductFilter = publicWidget.Widget.extend({
    selector: ".o_portal_wrap",
    events: {
        'change .moyee-filter-check': '_onFilterChange',
        'click #clearMoyeeFilters': '_onClearFilters',
        'change #moyeeSameAsShipping': '_onSameAsShipping',
        'input [name^="ship_"], select[name^="ship_"]': '_onShipAddressChange',
        'click input[type="date"]': '_onDateInputClick',
    },

    /**
     * @override
     */
    start: function () {
        this.$cards = this.$(".js_moyee_product_card");
        this.$noResults = this.$("#moyeeNoResults");
        this.$slider = this.$("#moyeeProductSlider");

        // Sync initially if checkbox happens to be checked on load
        if (this.$('#moyeeSameAsShipping').is(':checked')) {
            this._copyShippingToInvoice();
        }

        return this._super.apply(this, arguments);
    },

    // --------------------------------------------------------------------------
    // Handlers
    // --------------------------------------------------------------------------

    _onFilterChange: function () {
        this._applyFilters();
    },

    _onClearFilters: function (ev) {
        ev.preventDefault();
        this.$(".moyee-filter-check").prop("checked", false);
        this._applyFilters();
    },

    _onShipAddressChange: function (ev) {
        if (this.$('#moyeeSameAsShipping').is(':checked')) {
            const shipField = $(ev.currentTarget).attr('name');
            const invField = shipField.replace('ship_', 'inv_');
            this.$(`[name='${invField}']`).val($(ev.currentTarget).val());
        }
    },

    _onSameAsShipping: function (ev) {
        const checked = $(ev.currentTarget).is(":checked");
        const $invSection = this.$("#moyeeInvAddress");
        const $invToggleBtn = this.$("[data-bs-target='#moyeeInvAddress']");

        if (checked) {
            this._copyShippingToInvoice();

            // Collapse the invoice section & update button styling
            $invSection.collapse("hide");
            $invToggleBtn.text("Invoice address = Shipping address ✓").addClass("btn-success").removeClass("btn-light");
        } else {
            // Re-enable and show invoice fields
            $invToggleBtn.text("Manage invoice address ▾").removeClass("btn-success").addClass("btn-light");
        }
    },

    // --------------------------------------------------------------------------
    // Private
    // --------------------------------------------------------------------------

    _copyShippingToInvoice: function() {
        const fieldMap = {
            'ship_name': 'inv_name',
            'ship_phone': 'inv_phone',
            'ship_street': 'inv_street',
            'ship_street2': 'inv_street2',
            'ship_city': 'inv_city',
            'ship_zip': 'inv_zip',
            'ship_country_id': 'inv_country_id',
        };

        for (const [shipField, invField] of Object.entries(fieldMap)) {
            const shipVal = this.$(`[name='${shipField}']`).val();
            this.$(`[name='${invField}']`).val(shipVal);
        }
    },

    _applyFilters: function () {
        const activeGrinds = this.$(".moyee-filter-check[id^='grind']:checked").map(function() { return $(this).val(); }).get();
        const activeWeights = this.$(".moyee-filter-check[id^='weight']:checked").map(function() { return $(this).val(); }).get();

        let visibleCount = 0;

        this.$cards.each(function () {
            const $card = $(this);
            const grind = $card.data("grind");
            const weight = $card.data("weight");

            const matchGrind = activeGrinds.length === 0 || activeGrinds.includes(grind);
            const matchWeight = activeWeights.length === 0 || activeWeights.includes(weight);

            if (matchGrind && matchWeight) {
                $card.removeClass("d-none");
                visibleCount++;
            } else {
                $card.addClass("d-none");
            }
        });

        // Toggle visibility of slider and no results message
        if (visibleCount === 0) {
            this.$slider.addClass("d-none");
            this.$noResults.removeClass("d-none");
        } else {
            this.$slider.removeClass("d-none");
            this.$noResults.addClass("d-none");
        }
    },

    _onDateInputClick: function (ev) {
        if (typeof ev.currentTarget.showPicker === 'function') {
            try {
                ev.currentTarget.showPicker();
            } catch (err) {
                console.warn("showPicker is not supported or failed:", err);
            }
        }
    },
});

publicWidget.registry.MoyeeSubscriptionBreadcrumbFix = publicWidget.Widget.extend({
    selector: "#wrapwrap",
    start: function () {
        // Hide breadcrumbs on the main subscription portal page.
        // Odoo's purchase module has a core bug that incorrectly adds "Purchase Orders"
        // to the breadcrumb of sale orders in "sent" or "cancel" state. 
        // We hide the entire breadcrumb bar here to avoid customer confusion.
        if (this.$("a[href*='/moyee/manage']").length > 0) {
            this.$("ol.breadcrumb").closest('nav, .o_portal_submenu, .portal-breadcrumbs').hide();
        }
        return this._super.apply(this, arguments);
    }
});

export default publicWidget.registry.MoyeeProductFilter;
