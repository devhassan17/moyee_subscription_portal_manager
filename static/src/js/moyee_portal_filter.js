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

        this._updateFilterStates();

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
        const activeBolds = this.$(".moyee-filter-check[id^='bold']:checked").map(function() { return $(this).val(); }).get();
        const activeFruities = this.$(".moyee-filter-check[id^='char']:checked").map(function() { return $(this).val(); }).get();

        let visibleCount = 0;
        let visibleSubCount = 0;
        let visibleOtherCount = 0;

        this.$cards.each(function () {
            const $card = $(this);
            const grind = $card.data("grind");
            const weight = $card.data("weight");
            const bold = $card.data("bold");
            const fruity = $card.data("fruity");

            const matchGrind = activeGrinds.length === 0 || activeGrinds.includes(grind);
            const matchWeight = activeWeights.length === 0 || activeWeights.includes(weight);
            const matchBold = activeBolds.length === 0 || activeBolds.includes(bold);
            const matchFruity = activeFruities.length === 0 || activeFruities.includes(fruity);

            if (matchGrind && matchWeight && matchBold && matchFruity) {
                $card.removeClass("d-none");
                visibleCount++;
                if ($card.closest("#moyeeProductSliderSub").length > 0) {
                    visibleSubCount++;
                } else {
                    visibleOtherCount++;
                }
            } else {
                $card.addClass("d-none");
            }
        });

        // Hide/show sections and headings
        const $subHeading = this.$(".js_moyee_sub_heading");
        const $otherHeading = this.$(".js_moyee_other_heading");
        const $subSlider = this.$("#moyeeProductSliderSub");
        const $otherSlider = this.$("#moyeeProductSlider");

        if (visibleSubCount === 0) {
            $subHeading.addClass("d-none");
            $subSlider.addClass("d-none");
        } else {
            $subHeading.removeClass("d-none");
            $subSlider.removeClass("d-none");
        }

        if (visibleOtherCount === 0) {
            $otherHeading.addClass("d-none");
            $otherSlider.addClass("d-none");
        } else {
            $otherHeading.removeClass("d-none");
            $otherSlider.removeClass("d-none");
        }

        if (visibleCount === 0) {
            this.$noResults.removeClass("d-none");
        } else {
            this.$noResults.addClass("d-none");
        }

        this._updateFilterStates();
    },

    _updateFilterStates: function () {
        const grindWholeChecked = this.$("#grindWhole").is(":checked");
        const grindFilterChecked = this.$("#grindFilter").is(":checked");
        const grindEspressoChecked = this.$("#grindEspresso").is(":checked");
        const grindCapsulesChecked = this.$("#grindCapsules").is(":checked");

        const weight1kgChecked = this.$("#weight1kg").is(":checked");
        const weight250gChecked = this.$("#weight250g").is(":checked");
        const weight25capsChecked = this.$("#weight25caps").is(":checked");

        const isAnyBeansGrindChecked = grindWholeChecked || grindFilterChecked || grindEspressoChecked;
        const isAnyBeansWeightChecked = weight1kgChecked || weight250gChecked;

        const setOptionDisabled = (selector, disable) => {
            const $check = this.$(selector);
            const $parent = $check.closest('.form-check');
            $check.prop('disabled', disable);
            if (disable) {
                $parent.css({
                    'opacity': '0.4',
                    'pointer-events': 'none',
                    'transition': 'opacity 0.2s ease-in-out'
                });
            } else {
                $parent.css({
                    'opacity': '',
                    'pointer-events': '',
                    'transition': 'opacity 0.2s ease-in-out'
                });
            }
        };

        const disableCapsuleWeight = isAnyBeansGrindChecked || isAnyBeansWeightChecked;
        const disableCapsuleGrind = isAnyBeansGrindChecked || isAnyBeansWeightChecked;

        const disableBeansGrinds = grindCapsulesChecked || weight25capsChecked;
        const disableBeansWeights = grindCapsulesChecked || weight25capsChecked;

        setOptionDisabled("#grindWhole", disableBeansGrinds);
        setOptionDisabled("#grindFilter", disableBeansGrinds);
        setOptionDisabled("#grindEspresso", disableBeansGrinds);
        setOptionDisabled("#grindCapsules", disableCapsuleGrind);

        setOptionDisabled("#weight1kg", disableBeansWeights);
        setOptionDisabled("#weight250g", disableBeansWeights);
        setOptionDisabled("#weight25caps", disableCapsuleWeight);
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
