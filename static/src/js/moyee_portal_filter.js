/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.MoyeeProductFilter = publicWidget.Widget.extend({
    selector: ".o_portal_wrap",
    events: {
        'change .moyee-filter-check': '_onFilterChange',
        'input .moyee-price-slider': '_onPriceSliderChange',
        'click #clearMoyeeFilters': '_onClearFilters',
    },

    /**
     * @override
     */
    start: function () {
        this.$cards = this.$(".js_moyee_product_card");
        this.$noResults = this.$("#moyeeNoResults");
        this.$slider = this.$("#moyeeProductSlider");
        this.$priceMinLabel = this.$("#priceMinLabel");
        this.$priceMaxLabel = this.$("#priceMaxLabel");
        this.$priceRange = this.$("#priceRange");

        return this._super.apply(this, arguments);
    },

    // --------------------------------------------------------------------------
    // Handlers
    // --------------------------------------------------------------------------

    _onFilterChange: function () {
        this._applyFilters();
    },

    _onPriceSliderChange: function (ev) {
        const val = parseFloat($(ev.currentTarget).val());
        this.$priceMaxLabel.text(val.toFixed(2));
        this._applyFilters();
    },

    _onClearFilters: function (ev) {
        ev.preventDefault();
        this.$(".moyee-filter-check").prop("checked", false);
        const maxPrice = this.$priceRange.attr("max");
        this.$priceRange.val(maxPrice);
        this.$priceMaxLabel.text(parseFloat(maxPrice).toFixed(2));
        this._applyFilters();
    },

    // --------------------------------------------------------------------------
    // Private
    // --------------------------------------------------------------------------

    _applyFilters: function () {
        const activeGrinds = this.$(".moyee-filter-check[id^='grind']:checked").map(function() { return $(this).val(); }).get();
        const activeWeights = this.$(".moyee-filter-check[id^='weight']:checked").map(function() { return $(this).val(); }).get();
        const maxPrice = parseFloat(this.$priceRange.val());

        let visibleCount = 0;

        this.$cards.each(function () {
            const $card = $(this);
            const grind = $card.data("grind");
            const weight = $card.data("weight");
            const price = parseFloat($card.data("price"));

            const matchGrind = activeGrinds.length === 0 || activeGrinds.includes(grind);
            const matchWeight = activeWeights.length === 0 || activeWeights.includes(weight);
            const matchPrice = price <= maxPrice;

            if (matchGrind && matchWeight && matchPrice) {
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
});

export default publicWidget.registry.MoyeeProductFilter;
