/* ==========================================================================
   Checkout — delivery quoting, fulfilment time syncing, submit gating,
   phone validation, voucher feedback. Reads window.CHECKOUT_CONFIG set by
   the checkout template; the delivery map lives in checkout-delivery-map.js.
   ========================================================================== */

(function () {
    'use strict';

    const cfg = window.CHECKOUT_CONFIG;
    if (!cfg) return;

    const onlinePaymentAvailable = Boolean(cfg.onlinePaymentAvailable);
    const paymentFallbackAvailable = Boolean(cfg.paymentFallbackAvailable);
    const deliveryMinimumAmount = Number(cfg.deliveryMinimumAmount) || 0;
    const deliveryMinimumRemaining = Number(cfg.deliveryMinimumRemaining) || 0;
    const deliveryMinimumMet = Boolean(cfg.deliveryMinimumMet);
    const deliveryQuoteUrl = cfg.deliveryQuoteUrl;
    const checkoutDeliveryConfig = cfg.deliveryMap || { configured: false };

    const checkoutForm = document.getElementById('checkoutForm');
    const serviceTypeInput = document.getElementById('desktopServiceType');
    const submitBtn = document.getElementById('submitBtn');
    const paymentNote = document.getElementById('paymentNote');
    const deliveryQuoteNotice = document.getElementById('deliveryQuoteNotice');

    const baseSubmitDisabled = (submitBtn && submitBtn.disabled) || (!onlinePaymentAvailable && !paymentFallbackAvailable);
    const basePaymentNoteHTML = paymentNote ? paymentNote.innerHTML : '';

    let deliveryPlaceIsValid = !checkoutDeliveryConfig.configured || Boolean(
        document.getElementById('deliveryLatitude')?.value && document.getElementById('deliveryLongitude')?.value
    );
    let deliveryQuoteReady = false;
    let deliveryQuoteRequestId = 0;
    let deliveryFeeLabel = null; // set when a quote lands; null = base total applies

    function getBaseTotalLabel() {
        const el = document.getElementById('checkoutTotalValue');
        return el ? `£${el.dataset.baseTotal}` : '£0.00';
    }

    function getCheckoutTotalLabel() {
        return deliveryFeeLabel || getBaseTotalLabel();
    }

    function deliveryIsSelected() {
        return serviceTypeInput?.value === 'delivery';
    }

    function syncFulfilmentTimeOptions(service) {
        document.querySelectorAll('[data-time-options]').forEach(group => {
            const isActive = group.dataset.timeOptions === service;
            group.style.display = isActive ? 'block' : 'none';
            group.querySelectorAll('select[name="fulfilment_time"]').forEach(select => {
                select.disabled = !isActive;
                if (isActive && !select.value && select.options.length) {
                    select.selectedIndex = 0;
                }
            });
            updateFulfilmentTimeSummary(group);
        });
    }

    function updateFulfilmentTimeSummary(group) {
        const select = group.querySelector('select[name="fulfilment_time"]');
        const summary = group.querySelector('[data-time-summary]');
        if (!select || !summary) return;
        const selectedOption = select.options[select.selectedIndex];
        summary.textContent = selectedOption?.dataset.summary || '';
    }

    function updateDeliveryGate() {
        if (!submitBtn || !deliveryIsSelected()) {
            if (submitBtn) submitBtn.disabled = baseSubmitDisabled;
            if (paymentNote) paymentNote.innerHTML = basePaymentNoteHTML;
            return;
        }
        if (!deliveryMinimumMet) {
            submitBtn.disabled = true;
            if (paymentNote) {
                paymentNote.innerHTML = `<i class="ph ph-basket"></i> Delivery starts at £${deliveryMinimumAmount.toFixed(2)} before discounts. Add £${deliveryMinimumRemaining.toFixed(2)} more or choose pickup.`;
            }
            return;
        }
        if (checkoutDeliveryConfig.configured && !deliveryPlaceIsValid) {
            submitBtn.disabled = true;
            if (paymentNote) {
                paymentNote.innerHTML = '<i class="ph ph-map-pin"></i> Select an address from the suggestions before placing a delivery order.';
            }
            return;
        }
        if (!deliveryQuoteReady) {
            submitBtn.disabled = true;
            if (paymentNote) {
                paymentNote.innerHTML = '<i class="ph ph-truck"></i> Delivery fee must be confirmed before payment.';
            }
            return;
        }
        submitBtn.disabled = baseSubmitDisabled;
        if (paymentNote) paymentNote.innerHTML = basePaymentNoteHTML;
    }

    function updateSubmitAmount() {
        if (!submitBtn || !onlinePaymentAvailable) return;
        submitBtn.textContent = `Pay ${getCheckoutTotalLabel()}`;
    }

    function setDeliveryQuoteNotice(state, message) {
        if (!deliveryQuoteNotice) return;
        deliveryQuoteNotice.hidden = !deliveryIsSelected();
        deliveryQuoteNotice.dataset.state = state || 'neutral';
        const text = deliveryQuoteNotice.querySelector('span');
        if (text) text.textContent = message;
    }

    function resetDeliveryQuote(message) {
        deliveryQuoteReady = !deliveryIsSelected();
        deliveryFeeLabel = null;
        const totalEl = document.getElementById('checkoutTotalValue');
        if (totalEl) totalEl.textContent = getBaseTotalLabel();
        const feeRow = document.getElementById('deliveryFeeRow');
        const feeValue = document.getElementById('deliveryFeeValue');
        if (feeRow) feeRow.style.display = 'none';
        if (feeValue) feeValue.textContent = '£0.00';
        if (deliveryIsSelected()) {
            setDeliveryQuoteNotice('neutral', message || 'Choose delivery details to calculate the delivery fee.');
        } else if (deliveryQuoteNotice) {
            deliveryQuoteNotice.hidden = true;
        }
        updateSubmitAmount();
    }

    function applyDeliveryQuote(data) {
        if (!data.quote_ready) {
            resetDeliveryQuote(data.error || data.message || 'Choose delivery details to calculate the delivery fee.');
            if (data.error) setDeliveryQuoteNotice('error', data.error);
            updateDeliveryGate();
            return;
        }

        deliveryQuoteReady = true;
        const fee = parseFloat(data.delivery_fee || '0') || 0;
        const total = parseFloat(data.total || '0') || 0;
        deliveryFeeLabel = `£${total.toFixed(2)}`;
        const feeRow = document.getElementById('deliveryFeeRow');
        const feeValue = document.getElementById('deliveryFeeValue');
        const totalEl = document.getElementById('checkoutTotalValue');
        if (feeRow) feeRow.style.display = 'flex';
        if (feeValue) feeValue.textContent = `£${fee.toFixed(2)}`;
        if (totalEl) totalEl.textContent = deliveryFeeLabel;
        const distanceInput = document.getElementById('deliveryDistanceMiles');
        if (distanceInput && data.delivery_distance_miles) {
            distanceInput.value = data.delivery_distance_miles;
        }
        const detailParts = [`Delivery fee £${fee.toFixed(2)}`];
        if (data.delivery_zone_name) detailParts.push(data.delivery_zone_name);
        if (data.delivery_eta_minutes) detailParts.push(`~${data.delivery_eta_minutes} mins`);
        setDeliveryQuoteNotice('success', detailParts.join(' · '));
        updateSubmitAmount();
        updateDeliveryGate();
    }

    function requestDeliveryQuote() {
        if (!deliveryIsSelected()) {
            resetDeliveryQuote();
            updateDeliveryGate();
            return;
        }
        if (!deliveryMinimumMet) {
            resetDeliveryQuote(`Delivery starts at £${deliveryMinimumAmount.toFixed(2)} before discounts.`);
            updateDeliveryGate();
            return;
        }
        if (checkoutDeliveryConfig.configured && !deliveryPlaceIsValid) {
            resetDeliveryQuote('Choose your delivery address to calculate the delivery fee.');
            updateDeliveryGate();
            return;
        }

        const requestId = ++deliveryQuoteRequestId;
        setDeliveryQuoteNotice('loading', 'Calculating delivery fee...');
        fetch(deliveryQuoteUrl, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: new FormData(checkoutForm)
        })
        .then(response => response.json())
        .then(data => {
            if (requestId !== deliveryQuoteRequestId) return;
            applyDeliveryQuote(data);
        })
        .catch(() => {
            if (requestId !== deliveryQuoteRequestId) return;
            deliveryQuoteReady = false;
            setDeliveryQuoteNotice('error', 'Could not calculate delivery fee. Please try again.');
            updateDeliveryGate();
        });
    }

    // ── Voucher (HTMX form). Let 400/429 responses swap the feedback in. ──
    document.body.addEventListener('htmx:beforeSwap', function (event) {
        if (event.detail.target && event.detail.target.id === 'voucherFeedback') {
            event.detail.shouldSwap = true;
            event.detail.isError = false;
        }
    });

    // After a voucher swap, the totals block was replaced out-of-band:
    // re-read the base total and re-quote delivery.
    document.body.addEventListener('htmx:afterSwap', function (event) {
        if (event.detail.target && (event.detail.target.id === 'voucherFeedback' || event.detail.target.id === 'checkoutTotals')) {
            deliveryFeeLabel = null;
            updateSubmitAmount();
            requestDeliveryQuote();
            updateDeliveryGate();
        }
    });

    // ── Phone validation ───────────────────────────────────────────────
    const phoneInput = document.getElementById('customerPhone');
    if (phoneInput) {
        phoneInput.addEventListener('blur', function () {
            const phone = this.value.replace(/\s/g, '');
            const ukRegex = /^(07\d{9}|\+447\d{9})$/;
            this.style.borderColor = (phone && !ukRegex.test(phone)) ? 'var(--error)' : '';
        });
    }

    // ── Service change wiring ──────────────────────────────────────────
    document.querySelectorAll('[data-desktop-service]').forEach(button => {
        button.addEventListener('click', () => {
            setTimeout(() => {
                syncFulfilmentTimeOptions(deliveryIsSelected() ? 'delivery' : 'pickup');
                window.checkoutDeliveryController?.setServiceSelected(deliveryIsSelected());
                requestDeliveryQuote();
                updateDeliveryGate();
            }, 150);
        });
    });

    document.addEventListener('checkout-service:changed', event => {
        syncFulfilmentTimeOptions(event.detail.isDelivery ? 'delivery' : 'pickup');
        window.checkoutDeliveryController?.setServiceSelected(Boolean(event.detail.isDelivery));
        requestDeliveryQuote();
        updateDeliveryGate();
    });

    document.querySelectorAll('select[name="fulfilment_time"]').forEach(select => {
        select.addEventListener('change', function () {
            updateFulfilmentTimeSummary(this.closest('[data-time-options]'));
        });
    });

    document.addEventListener('checkout-delivery:validity', event => {
        deliveryPlaceIsValid = Boolean(event.detail.valid);
        requestDeliveryQuote();
        updateDeliveryGate();
    });

    ['delivery_address_line1', 'delivery_city', 'delivery_postcode'].forEach(name => {
        document.querySelector(`[name="${name}"]`)?.addEventListener('input', () => {
            if (!checkoutDeliveryConfig.configured) requestDeliveryQuote();
        });
    });

    checkoutForm?.addEventListener('submit', event => {
        if (checkoutDeliveryConfig.configured && deliveryIsSelected() && !deliveryPlaceIsValid) {
            event.preventDefault();
            document.getElementById('deliveryAddressSearch')?.focus();
            updateDeliveryGate();
        }
    });

    // ── Init ───────────────────────────────────────────────────────────
    window.checkoutDeliveryController = window.CheckoutDeliveryMap?.init(checkoutDeliveryConfig);
    syncFulfilmentTimeOptions(deliveryIsSelected() ? 'delivery' : 'pickup');
    requestDeliveryQuote();
    updateDeliveryGate();
})();
