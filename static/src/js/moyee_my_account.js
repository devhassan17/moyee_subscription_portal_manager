/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

/**
 * Moyee My Account Page — interactivity widget.
 * Handles FAQ accordion, order/invoice expand, modals, smooth scroll, and TAF.
 */
publicWidget.registry.MoyeeMyAccountPage = publicWidget.Widget.extend({
    selector: ".moyee-account-page",
    events: {
        /* FAQ accordion */
        "click .moyee-faq-q": "_onFaqToggle",

        /* Expand / collapse orders & invoices */
        "click .moyee-orders-toggle": "_onToggleOrders",
        "click .moyee-invoices-toggle": "_onToggleInvoices",

        /* Modals */
        "click [data-moyee-modal]": "_onOpenModal",
        "click .moyee-modal-close": "_onCloseModal",
        "click .moyee-modal-cancel": "_onCloseModal",
        "click .moyee-modal-overlay": "_onOverlayClick",

        /* Smooth scroll for nav cards */
        "click [data-moyee-scroll]": "_onSmoothScroll",

        /* Tell a Friend */
        "click .moyee-taf-send": "_onTafSend",

        /* Cascading select dropdowns for Edit modal */
        "change .js_moyee_edit_line_form select[name='grind']": "_onGrindChange",
        "change .js_moyee_edit_line_form select[name='coffee_type']": "_onCoffeeTypeChange",

        /* Date picker click */
        "click input[type='date']": "_onDateInputClick",
    },

    // ──────────────────────────────────────────
    // Lifecycle
    // ──────────────────────────────────────────

    start: function () {
        this._ordersExpanded = false;
        this._invoicesExpanded = false;
        return this._super.apply(this, arguments);
    },

    // ──────────────────────────────────────────
    // FAQ Accordion
    // ──────────────────────────────────────────

    _onFaqToggle: function (ev) {
        var $item = $(ev.currentTarget).closest(".moyee-faq-item");
        $item.toggleClass("open");
    },

    // ──────────────────────────────────────────
    // Orders / Invoices toggle
    // ──────────────────────────────────────────

    _onToggleOrders: function (ev) {
        ev.preventDefault();
        var $extra = this.$(".moyee-orders-extra");
        var $btn = $(ev.currentTarget);
        this._ordersExpanded = !this._ordersExpanded;
        if (this._ordersExpanded) {
            $extra.css("display", "flex");
            $btn.text("Show less ↑");
        } else {
            $extra.css("display", "none");
            $btn.text("View all orders ↓");
        }
    },

    _onToggleInvoices: function (ev) {
        ev.preventDefault();
        var $extra = this.$(".moyee-invoices-extra");
        var $btn = $(ev.currentTarget);
        this._invoicesExpanded = !this._invoicesExpanded;
        if (this._invoicesExpanded) {
            $extra.css("display", "flex");
            $btn.text("Show less ↑");
        } else {
            $extra.css("display", "none");
            $btn.text("View all invoices ↓");
        }
    },

    // ──────────────────────────────────────────
    // Modal system
    // ──────────────────────────────────────────

    _onOpenModal: function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var modalId = $(ev.currentTarget).data("moyee-modal");
        if (modalId) {
            var $modal = this.$("#" + modalId);
            $modal.addClass("open");
            $("body").css("overflow", "hidden");

            // If this is an edit product modal, initialize the cascading dropdowns
            var $form = $modal.find(".js_moyee_edit_line_form");
            if ($form.length) {
                this._initCascadingDropdowns($form);
            }
        }
    },

    _onCloseModal: function (ev) {
        ev.preventDefault();
        $(ev.currentTarget).closest(".moyee-modal-overlay").removeClass("open");
        $("body").css("overflow", "");
    },

    _onOverlayClick: function (ev) {
        /* Close only when clicking the overlay itself, not the modal body */
        if ($(ev.target).hasClass("moyee-modal-overlay")) {
            $(ev.target).removeClass("open");
            $("body").css("overflow", "");
        }
    },

    // ──────────────────────────────────────────
    // Smooth scroll
    // ──────────────────────────────────────────

    _onSmoothScroll: function (ev) {
        ev.preventDefault();
        var target = $(ev.currentTarget).data("moyee-scroll");
        var $target = this.$("#" + target);
        if ($target.length) {
            $target[0].scrollIntoView({ behavior: "smooth" });
        }
    },

    // ──────────────────────────────────────────
    // Tell a Friend
    // ──────────────────────────────────────────

    _onTafSend: function (ev) {
        ev.preventDefault();
        var $input = this.$(".moyee-taf-input");
        var $success = this.$(".moyee-taf-success");
        var email = ($input.val() || "").trim();
        if (email && email.indexOf("@") > 0) {
            $success.fadeIn(200);
            $input.val("");
            setTimeout(function () {
                $success.fadeOut(300);
            }, 4000);
        } else {
            $input.css("border-color", "#cc0000");
            setTimeout(function () {
                $input.css("border-color", "");
            }, 2000);
        }
    },

    // ──────────────────────────────────────────
    // Cascading Dropdowns Logic for Edit Modal
    // ──────────────────────────────────────────

    _initCascadingDropdowns: function ($form) {
        var variantsStr = $form.attr("data-variants");
        if (!variantsStr) return;
        
        try {
            var variants = JSON.parse(variantsStr);
            $form.data("variants-list", variants);

            // Store the initial selected values so we don't overwrite them on first load
            var initialGrind = $form.find("select[name='grind']").val();
            var initialCoffeeType = $form.find("select[name='coffee_type']").val();
            var initialWeight = $form.find("select[name='weight']").val();

            this._updateCoffeeTypes($form, initialGrind, initialCoffeeType);
            this._updateWeights($form, initialGrind, $form.find("select[name='coffee_type']").val(), initialWeight);
        } catch (e) {
            console.error("Moyee error parsing variants JSON:", e);
        }
    },

    _onGrindChange: function (ev) {
        var $form = $(ev.currentTarget).closest(".js_moyee_edit_line_form");
        var grind = $(ev.currentTarget).val();
        
        this._updateCoffeeTypes($form, grind);
        this._updateWeights($form, grind, $form.find("select[name='coffee_type']").val());
    },

    _onCoffeeTypeChange: function (ev) {
        var $form = $(ev.currentTarget).closest(".js_moyee_edit_line_form");
        var grind = $form.find("select[name='grind']").val();
        var coffeeType = $(ev.currentTarget).val();
        
        this._updateWeights($form, grind, coffeeType);
    },

    _updateCoffeeTypes: function ($form, grind, selectedValue) {
        var variants = $form.data("variants-list") || [];
        var $coffeeSelect = $form.find("select[name='coffee_type']");
        var currentValue = selectedValue || $coffeeSelect.val();

        // Find templates available for this grind
        var templatesMap = {};
        variants.forEach(function (v) {
            if (v.grind === grind) {
                templatesMap[v.tmpl_id] = v.tmpl_name;
            }
        });

        // Rebuild options
        $coffeeSelect.empty();
        var keys = Object.keys(templatesMap);
        if (keys.length === 0) {
            $coffeeSelect.append($("<option>", {
                value: "",
                text: "No coffee available"
            }));
            return;
        }

        keys.forEach(function (tmplId) {
            $coffeeSelect.append($("<option>", {
                value: tmplId,
                text: templatesMap[tmplId],
                selected: String(tmplId) === String(currentValue)
            }));
        });
    },

    _updateWeights: function ($form, grind, coffeeType, selectedValue) {
        var variants = $form.data("variants-list") || [];
        var $weightSelect = $form.find("select[name='weight']");
        var currentValue = selectedValue || $weightSelect.val();

        // Find weights available for this grind and coffee template
        var weightsMap = {};
        variants.forEach(function (v) {
            if (v.grind === grind && String(v.tmpl_id) === String(coffeeType)) {
                var displayWeight = v.weight;
                if (v.weight === "1kg") displayWeight = "1 kg";
                else if (v.weight === "250g") displayWeight = "250g";
                else if (v.weight === "25caps") displayWeight = "25 Capsules";
                weightsMap[v.weight] = displayWeight;
            }
        });

        // Rebuild options
        $weightSelect.empty();
        var keys = Object.keys(weightsMap);
        if (keys.length === 0) {
            $weightSelect.append($("<option>", {
                value: "",
                text: "No amount available"
            }));
            return;
        }

        keys.forEach(function (weightVal) {
            $weightSelect.append($("<option>", {
                value: weightVal,
                text: weightsMap[weightVal],
                selected: String(weightVal) === String(currentValue)
            }));
        });
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

export default publicWidget.registry.MoyeeMyAccountPage;
