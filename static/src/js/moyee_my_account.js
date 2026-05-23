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
            this.$("#" + modalId).addClass("open");
            $("body").css("overflow", "hidden");
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
});

export default publicWidget.registry.MoyeeMyAccountPage;
