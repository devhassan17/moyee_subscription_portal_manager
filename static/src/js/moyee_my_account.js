/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

/**
 * Moyee My Account Page — interactivity widget.
 * Handles FAQ accordion, order/invoice expand, modals, smooth scroll, and TAF.
 */
publicWidget.registry.MoyeeMyAccountPage = publicWidget.Widget.extend({
    selector: "#wrapwrap",
    events: {
        /* FAQ accordion */
        "click .moyee-faq-q": "_onFaqToggle",

        /* Expand / collapse/paginate orders & invoices */
        "click .moyee-orders-toggle": "_onToggleOrders",
        "click .moyee-invoices-toggle": "_onToggleInvoices",
        "click .js-prev-orders-page": "_onPrevOrdersPage",
        "click .js-next-orders-page": "_onNextOrdersPage",
        "click .js-orders-show-less": "_onOrdersShowLess",
        "click .js-prev-invoices-page": "_onPrevInvoicesPage",
        "click .js-next-invoices-page": "_onNextInvoicesPage",
        "click .js-invoices-show-less": "_onInvoicesShowLess",
        "click .moyee-reorder-btn": "_onReorderClick",

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

        /* Track & Trace Link */
        "click .moyee-track-link": "_onTrackLinkClick",
    },

    // ──────────────────────────────────────────
    // Lifecycle
    // ──────────────────────────────────────────

    start: function () {
        this._ordersExpanded = false;
        this._invoicesExpanded = false;
        this._ordersPage = 1;
        this._invoicesPage = 1;
        this._pageSize = 10;
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
    // Orders / Invoices client-side pagination
    // ──────────────────────────────────────────

    _onToggleOrders: function (ev) {
        ev.preventDefault();
        this._ordersExpanded = true;
        this._ordersPage = 1;
        this._updateOrdersView();
    },

    _onPrevOrdersPage: function (ev) {
        ev.preventDefault();
        if (this._ordersPage > 1) {
            this._ordersPage--;
            this._updateOrdersView();
            var $target = this.$("#moyee-section-orders");
            if ($target.length) {
                $target[0].scrollIntoView({ behavior: "smooth" });
            }
        }
    },

    _onNextOrdersPage: function (ev) {
        ev.preventDefault();
        var total = this.$(".js-order-item").length;
        var totalPages = Math.ceil(total / this._pageSize) || 1;
        if (this._ordersPage < totalPages) {
            this._ordersPage++;
            this._updateOrdersView();
            var $target = this.$("#moyee-section-orders");
            if ($target.length) {
                $target[0].scrollIntoView({ behavior: "smooth" });
            }
        }
    },

    _onOrdersShowLess: function (ev) {
        ev.preventDefault();
        this._ordersExpanded = false;
        this._updateOrdersView();
        var $target = this.$("#moyee-section-orders");
        if ($target.length) {
            $target[0].scrollIntoView({ behavior: "smooth" });
        }
    },

    _updateOrdersView: function () {
        var $items = this.$(".js-order-item");
        var total = $items.length;
        if (!this._ordersExpanded) {
            $items.each(function (idx) {
                $(this).toggle(idx < 5);
            });
            this.$(".js-orders-toggle-wrap").removeClass("d-none");
            this.$(".js-orders-pagination").removeClass("d-flex").addClass("d-none");
        } else {
            this.$(".js-orders-toggle-wrap").addClass("d-none");
            this.$(".js-orders-pagination").removeClass("d-none").addClass("d-flex");

            var totalPages = Math.ceil(total / this._pageSize) || 1;
            if (this._ordersPage < 1) this._ordersPage = 1;
            if (this._ordersPage > totalPages) this._ordersPage = totalPages;

            var startIdx = (this._ordersPage - 1) * this._pageSize;
            var endIdx = startIdx + this._pageSize;

            $items.each(function (idx) {
                $(this).toggle(idx >= startIdx && idx < endIdx);
            });

            this.$(".js-orders-page-info").text("Page " + this._ordersPage + " of " + totalPages);
            this.$(".js-prev-orders-page").prop("disabled", this._ordersPage === 1);
            this.$(".js-next-orders-page").prop("disabled", this._ordersPage === totalPages);
        }
    },

    _onToggleInvoices: function (ev) {
        ev.preventDefault();
        this._invoicesExpanded = true;
        this._invoicesPage = 1;
        this._updateInvoicesView();
    },

    _onPrevInvoicesPage: function (ev) {
        ev.preventDefault();
        if (this._invoicesPage > 1) {
            this._invoicesPage--;
            this._updateInvoicesView();
            var $target = this.$("#moyee-section-invoices");
            if ($target.length) {
                $target[0].scrollIntoView({ behavior: "smooth" });
            }
        }
    },

    _onNextInvoicesPage: function (ev) {
        ev.preventDefault();
        var total = this.$(".js-invoice-item").length;
        var totalPages = Math.ceil(total / this._pageSize) || 1;
        if (this._invoicesPage < totalPages) {
            this._invoicesPage++;
            this._updateInvoicesView();
            var $target = this.$("#moyee-section-invoices");
            if ($target.length) {
                $target[0].scrollIntoView({ behavior: "smooth" });
            }
        }
    },

    _onInvoicesShowLess: function (ev) {
        ev.preventDefault();
        this._invoicesExpanded = false;
        this._updateInvoicesView();
        var $target = this.$("#moyee-section-invoices");
        if ($target.length) {
            $target[0].scrollIntoView({ behavior: "smooth" });
        }
    },

    _updateInvoicesView: function () {
        var $items = this.$(".js-invoice-item");
        var total = $items.length;
        if (!this._invoicesExpanded) {
            $items.each(function (idx) {
                $(this).toggle(idx < 3);
            });
            this.$(".js-invoices-toggle-wrap").removeClass("d-none");
            this.$(".js-invoices-pagination").removeClass("d-flex").addClass("d-none");
        } else {
            this.$(".js-invoices-toggle-wrap").addClass("d-none");
            this.$(".js-invoices-pagination").removeClass("d-none").addClass("d-flex");

            var totalPages = Math.ceil(total / this._pageSize) || 1;
            if (this._invoicesPage < 1) this._invoicesPage = 1;
            if (this._invoicesPage > totalPages) this._invoicesPage = totalPages;

            var startIdx = (this._invoicesPage - 1) * this._pageSize;
            var endIdx = startIdx + this._pageSize;

            $items.each(function (idx) {
                $(this).toggle(idx >= startIdx && idx < endIdx);
            });

            this.$(".js-invoices-page-info").text("Page " + this._invoicesPage + " of " + totalPages);
            this.$(".js-prev-invoices-page").prop("disabled", this._invoicesPage === 1);
            this.$(".js-next-invoices-page").prop("disabled", this._invoicesPage === totalPages);
        }
    },

    _onReorderClick: function (ev) {
        ev.stopPropagation();
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
        var $error = this.$(".moyee-taf-error");
        var email = ($input.val() || "").trim();
        if (email && email.indexOf("@") > 0) {
            $input.prop("disabled", true);
            // Simulate a brief delay to mimic server response before showing success
            setTimeout(function () {
                $input.prop("disabled", false);
                $success.fadeIn(200);
                $input.val("");
                if ($error.length) {
                    $error.hide();
                }
                setTimeout(function () {
                    $success.fadeOut(300);
                }, 4000);
            }, 500);
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

    _onTrackLinkClick: function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var url = $(ev.currentTarget).data("url");
        if (url) {
            window.open(url, '_blank');
        }
    },
});

export default publicWidget.registry.MoyeeMyAccountPage;
