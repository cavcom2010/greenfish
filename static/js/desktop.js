/* ==========================================================================
   Desktop JavaScript — Interactions & UX
   ========================================================================== */

(function () {
    'use strict';

    const ORDER_ROUTES = {
        addToCart: '/orders/cart/add/',
        serviceType: '/orders/service-type/',
        cartDrawer: '/orders/cart/drawer/'
    };

    // ── Toast Notification System ──────────────────────────────────────
    window.showToast = function(message, type = 'success', duration = 3000) {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const icons = {
            success: 'ph-fill ph-check-circle',
            error: 'ph-fill ph-warning-circle',
            info: 'ph-fill ph-info'
        };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <i class="${icons[type] || icons.info}"></i>
            <span>${message}</span>
            <span class="toast-close" onclick="this.parentElement.classList.add('toast-exit'); setTimeout(() => this.parentElement.remove(), 300);" aria-label="Dismiss">&times;</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('toast-exit');
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    };

    // ── Cart Drawer ────────────────────────────────────────────────────
    let cartDrawerOpen = false;

    window.openCartDrawer = function() {
        const overlay = document.getElementById('cartDrawerOverlay');
        if (!overlay || cartDrawerOpen) return;

        cartDrawerOpen = true;
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Fetch cart content via HTMX
        const content = document.getElementById('cartDrawerContent');
        if (content) {
            fetch(ORDER_ROUTES.cartDrawer, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.text())
            .then(html => { content.innerHTML = html; })
            .catch(() => {
                content.innerHTML = `
                    <div style="text-align:center;padding:3rem;">
                        <p style="color:var(--text-muted);">Could not load basket. <a href="/orders/cart/" style="color:var(--brand);">View full basket</a></p>
                    </div>`;
            });
        }
    };

    window.closeCartDrawer = function() {
        const overlay = document.getElementById('cartDrawerOverlay');
        if (!overlay || !cartDrawerOpen) return;

        cartDrawerOpen = false;
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    };

    window.closeCartDrawerOnOverlay = function(e) {
        if (e.target === e.currentTarget) window.closeCartDrawer();
    };

    function refreshCartDrawer() {
        return fetch(ORDER_ROUTES.cartDrawer)
            .then(res => res.text())
            .then(html => {
                const content = document.getElementById('cartDrawerContent');
                if (content) content.innerHTML = html;
            });
    }

    // Close cart drawer on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && cartDrawerOpen) window.closeCartDrawer();
    });

    // Drawer quantity update
    window.drawerUpdateQty = function(itemId, newQty) {
        if (newQty < 1) {
            showToast('Use the trash icon to remove items', 'info', 2000);
            return;
        }

        const csrftoken = getCSRFToken();
        let cartState = null;
        fetch(`/orders/cart/update/${itemId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: `quantity=${newQty}`
        })
        .then(res => {
            if (!res.ok) throw new Error('Update failed');
            return res.json();
        })
        .then(data => {
            cartState = data;
            return refreshCartDrawer();
        })
        .then(() => {
            updateCartState(cartState);
        })
        .catch(() => {
            showToast('Could not update quantity. Please try again.', 'error');
        });
    };

    document.addEventListener('submit', function(e) {
        const form = e.target.closest('.cart-drawer-item-remove');
        if (!form) return;

        e.preventDefault();
        const csrftoken = getCSRFToken();
        let cartState = null;

        fetch(form.action, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(res => {
                if (!res.ok) throw new Error('Remove failed');
                return res.json();
            })
            .then(data => {
                cartState = data;
                return refreshCartDrawer();
            })
            .then(() => {
                updateCartState(cartState);
            })
            .catch(() => {
                showToast('Could not remove item. Please try again.', 'error');
            });
    });

    // ── Sticky Header Shadow on Scroll ───────────────────────────────────
    const header = document.querySelector('.site-header');
    if (header) {
        const toggleHeaderShadow = () => {
            header.classList.toggle('scrolled', window.scrollY > 10);
        };
        window.addEventListener('scroll', toggleHeaderShadow, { passive: true });
        toggleHeaderShadow();
    }

    // ── Scroll to Top ───────────────────────────────────────────────────
    const scrollToTopBtn = document.getElementById('scrollToTopBtn');
    if (scrollToTopBtn) {
        const toggleScrollButton = () => {
            scrollToTopBtn.classList.toggle('visible', window.scrollY > 360);
        };
        window.addEventListener('scroll', toggleScrollButton, { passive: true });
        scrollToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
        toggleScrollButton();
    }

    // ── Service Type Toggle ──────────────────────────────────────────────
    const serviceToggles = document.querySelectorAll('[data-desktop-service]');
    const serviceTypeInput = document.getElementById('desktopServiceType');
    const deliveryEnabled = Boolean(window.APP_CONFIG?.deliveryEnabled ?? true);

    function normalizeServiceType(service) {
        return service === 'delivery' && !deliveryEnabled ? 'pickup' : service;
    }

    function applyServiceType(service) {
        service = normalizeServiceType(service);
        serviceToggles.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.desktopService === service);
        });
        if (serviceTypeInput) {
            serviceTypeInput.value = service;
        }
        localStorage.setItem('service_type', service);
        modalCurrentService = service;

        // Update delivery address visibility on checkout
        const deliveryCard = document.getElementById('deliveryAddressCard');
        if (deliveryCard) {
            deliveryCard.hidden = service !== 'delivery';
            window.checkoutDeliveryController?.setServiceSelected(service === 'delivery');
        }

        const isDelivery = service === 'delivery';
        const serviceSummary = document.getElementById('serviceSummary');
        if (serviceSummary) {
            serviceSummary.textContent = isDelivery
                ? 'Delivered to your address after the kitchen confirms your order.'
                : 'Collect from the shop when your order is ready.';
        }

        const serviceInfoText = document.getElementById('serviceInfoText');
        if (serviceInfoText) {
            serviceInfoText.textContent = isDelivery ? 'Delivered to your door' : 'Collect from the shop';
        }

        const serviceTimeHeading = document.getElementById('serviceTimeHeading');
        if (serviceTimeHeading) {
            serviceTimeHeading.innerHTML = `<i class="ph ph-clock"></i> ${isDelivery ? 'Delivery' : 'Pickup'} Time`;
        }

        const serviceTimeDescription = document.getElementById('serviceTimeDescription');
        if (serviceTimeDescription) {
            serviceTimeDescription.textContent = isDelivery
                ? 'When should we aim to arrive with your order?'
                : 'When would you like to collect your order?';
        }

        document.dispatchEvent(new CustomEvent('checkout-service:changed', {
            detail: { service, isDelivery }
        }));

        // Persist to server
        persistServiceType(service);
    }

    function persistServiceType(service) {
        const csrftoken = getCSRFToken();
        fetch(ORDER_ROUTES.serviceType, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrftoken
            },
            body: `service_type=${encodeURIComponent(service)}`
        }).catch(() => null);
    }

    serviceToggles.forEach(btn => {
        btn.addEventListener('click', () => {
            applyServiceType(normalizeServiceType(btn.dataset.desktopService));
        });
    });

    // ── Time Slot Selection ──────────────────────────────────────────────
    const timeSlots = document.querySelectorAll('.time-slot');
    timeSlots.forEach(slot => {
        slot.addEventListener('click', () => {
            timeSlots.forEach(s => s.classList.remove('active'));
            slot.classList.add('active');
            const radio = slot.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;
        });
    });

    // ── Payment Option Selection ─────────────────────────────────────────
    const paymentOptions = document.querySelectorAll('.payment-option');
    paymentOptions.forEach(option => {
        option.addEventListener('click', () => {
            paymentOptions.forEach(o => o.classList.remove('active'));
            option.classList.add('active');
            const radio = option.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;
        });
    });

    // ── Modal System ─────────────────────────────────────────────────────
    window.openItemModal = function (itemId) {
        const overlay = document.getElementById('itemModalDesktop');
        const content = document.getElementById('modalDesktopContent');
        const title = document.getElementById('modalDesktopTitle');
        if (!overlay || !content) return;

        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        if (title) title.textContent = 'Item Details';
        content.innerHTML = getModalLoadingHTML();

        fetch(`/menu/item/${itemId}/`, {
            headers: { 'HX-Request': 'true' }
        })
            .then(res => res.text())
            .then(html => {
                content.innerHTML = html;
                initModalState();
            })
            .catch(() => {
                content.innerHTML = `
                    <div style="text-align:center;padding:3rem;">
                        <p style="color:var(--text-muted);">Error loading item. Please try again.</p>
                    </div>`;
            });
    };

    window.closeItemModal = function () {
        const overlay = document.getElementById('itemModalDesktop');
        const title = document.getElementById('modalDesktopTitle');
        if (overlay) overlay.classList.remove('active');
        if (title) title.textContent = 'Item Details';
        document.body.style.overflow = '';
    };

    // Close on overlay click
    const modalOverlay = document.getElementById('itemModalDesktop');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) window.closeItemModal();
        });
    }

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') window.closeItemModal();
    });

    // ── Modal State (quantity, modifiers, price) ─────────────────────────
    let modalQuantity = 1;
    let modalBasePrice = 0;
    let modalItemId = null;
    let modalCurrentService = normalizeServiceType(localStorage.getItem('service_type') || 'pickup');

    function initModalState() {
        modalQuantity = 1;
        const modalDiv = document.querySelector('#modalDesktopContent > div[data-item-id]');
        if (modalDiv) {
            modalItemId = modalDiv.dataset.itemId;
            modalBasePrice = parseFloat(modalDiv.dataset.basePrice) || 0;
            const title = document.getElementById('modalDesktopTitle');
            if (title && modalDiv.dataset.itemName) title.textContent = modalDiv.dataset.itemName;
            updateModalTotal();
        }

        // Bind event listeners inside modal
        bindModalEvents();
    }

    function bindModalEvents() {
        const content = document.getElementById('modalDesktopContent');
        if (!content) return;

        // Quantity buttons
        content.querySelectorAll('.qty-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const change = parseInt(btn.dataset.change);
                modalQuantity = Math.max(1, modalQuantity + change);
                const display = document.getElementById('modalQtyDisplay');
                if (display) display.textContent = modalQuantity;
                updateModalTotal();
            });
        });

        // Modifier checkboxes
        content.querySelectorAll('.modifier-checkbox').forEach(cb => {
            cb.addEventListener('change', updateModalTotal);
        });

        // Add to cart button
        const addBtn = document.getElementById('modalAddBtn');
        if (addBtn) {
            addBtn.addEventListener('click', addToCartFromModal);
        }
    }

    function updateModalTotal() {
        let modifiersTotal = 0;
        document.querySelectorAll('#modalDesktopContent .modifier-checkbox:checked').forEach(cb => {
            modifiersTotal += parseFloat(cb.dataset.price) || 0;
        });
        const total = (modalBasePrice + modifiersTotal) * modalQuantity;
        const priceEl = document.getElementById('modalTotalPrice');
        if (priceEl) priceEl.textContent = `£${total.toFixed(2)}`;
    }

    function addToCartFromModal() {
        const btn = document.getElementById('modalAddBtn');
        if (!btn || !modalItemId) return;

        const originalHTML = btn.innerHTML;
        btn.innerHTML = 'Adding...';
        btn.disabled = true;
        btn.style.opacity = '0.7';

        const modifiers = [];
        document.querySelectorAll('#modalDesktopContent .modifier-checkbox:checked').forEach(cb => {
            modifiers.push({
                id: cb.value,
                name: cb.dataset.name,
                price: parseFloat(cb.dataset.price) || 0
            });
        });

        const csrftoken = getCSRFToken();
        fetch(ORDER_ROUTES.addToCart, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrftoken
            },
            body: `menu_item_id=${modalItemId}&quantity=${modalQuantity}&service_type=${encodeURIComponent(modalCurrentService)}&modifiers=${encodeURIComponent(JSON.stringify(modifiers))}`
        })
            .then(res => {
                if (!res.ok) throw new Error(`Add to cart failed with status ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (data.success) {
                    btn.innerHTML = '✓ Added!';
                    btn.style.background = '#16A34A';
                    updateCartState(data);
                    showToast('Added to basket', 'success', 2000);
                    setTimeout(() => {
                        window.closeItemModal();
                        window.location.reload();
                    }, 800);
                } else {
                    throw new Error('Failed');
                }
            })
            .catch(() => {
                btn.innerHTML = '❌ Error';
                btn.style.background = '#DC2626';
                showToast('Could not add to basket. Please try again.', 'error');
                setTimeout(() => {
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                    btn.style.opacity = '1';
                }, 2000);
            });
    }

    function getModalLoadingHTML() {
        return `
            <div style="text-align:center;padding:3rem;">
                <div style="width:40px;height:40px;border:3px solid var(--border);border-top-color:var(--brand);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 1rem;"></div>
                <p style="color:var(--text-muted);">Loading item details...</p>
                <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
            </div>`;
    }

    // ── Cart State Update ────────────────────────────────────────────────
    function pluralizeItems(count) {
        return count === 1 ? 'item' : 'items';
    }

    function updateCartBadge(count) {
        const badges = document.querySelectorAll('.cart-badge-desktop');
        badges.forEach(badge => {
            badge.textContent = count;
            badge.hidden = count <= 0;
        });

        const cartButton = document.getElementById('desktopCartButton');
        if (cartButton) {
            const countText = count > 0 ? `, ${count} ${pluralizeItems(count)}` : '';
            cartButton.setAttribute('aria-label', `View cart${countText}`);
        }
    }

    function updateStickyCartBar(count, total) {
        const stickyBar = document.getElementById('stickyCartBar');
        if (!stickyBar) return;

        stickyBar.classList.toggle('visible', count > 0);
        stickyBar.setAttribute('aria-hidden', count > 0 ? 'false' : 'true');

        const countEl = document.getElementById('stickyCartCount');
        if (countEl) countEl.textContent = `${count} ${pluralizeItems(count)}`;

        const totalEl = document.getElementById('stickyCartTotal');
        if (totalEl && total !== undefined && total !== null) {
            totalEl.textContent = `£${Number(total).toFixed(2)}`;
        }
    }

    function updateCartState(data) {
        if (!data || data.cart_count === undefined) return;
        const count = Number(data.cart_count) || 0;
        updateCartBadge(count);
        updateStickyCartBar(count, data.cart_total);
    }

    document.body.addEventListener('cart-updated', function(event) {
        updateCartState(event.detail);
    });

    // ── Quick Add to Cart (from menu grid) ───────────────────────────────
    window.quickAddToCart = function (itemId) {
        const csrftoken = getCSRFToken();
        const service = normalizeServiceType(localStorage.getItem('service_type') || 'pickup');

        fetch(ORDER_ROUTES.addToCart, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrftoken
            },
            body: `menu_item_id=${itemId}&quantity=1&service_type=${encodeURIComponent(service)}&modifiers=[]`
        })
            .then(res => {
                if (!res.ok) throw new Error(`Quick add failed with status ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (data.success) {
                    updateCartState(data);

                    // Visual feedback on the button
                    const card = document.querySelector(`[data-quick-add="${itemId}"]`);
                    if (card) {
                        card.style.transform = 'scale(0.9)';
                        card.style.background = '#16A34A';
                        card.style.color = 'white';
                        setTimeout(() => {
                            card.style.transform = '';
                            card.style.background = '';
                            card.style.color = '';
                        }, 400);
                    }

                    showToast('Added to basket', 'success', 2000);
                }
            })
            .catch(() => {
                showToast('Could not add to basket. Please try again.', 'error');
            });
    };

    // ── CSRF Token Helper ────────────────────────────────────────────────
    function getCSRFToken() {
        const el = document.querySelector('[name=csrfmiddlewaretoken]');
        if (el) return el.value;
        // Try cookie
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // ── Restore Service Type from LocalStorage ───────────────────────────
    const savedService = localStorage.getItem('service_type');
    if (savedService && (savedService === 'pickup' || savedService === 'delivery')) {
        applyServiceType(normalizeServiceType(savedService));
    } else if (serviceToggles.length > 0) {
        const firstActive = document.querySelector('[data-desktop-service].active');
        if (firstActive) applyServiceType(normalizeServiceType(firstActive.dataset.desktopService));
    }

})();

// ── Cookie Consent (GDPR / UK ICO) ─────────────────────────────────────
(function() {
    'use strict';

    var CONSENT_KEY = 'cookie_consent';
    var banner = document.getElementById('cookieConsentBanner');

    // Check if user already made a choice
    if (!localStorage.getItem(CONSENT_KEY)) {
        setTimeout(function() {
            if (banner) banner.classList.add('visible');
        }, 1000);
    }

    window.acceptCookies = function(preference) {
        localStorage.setItem(CONSENT_KEY, preference);

        // Hide banner
        if (banner) banner.classList.remove('visible');

        // If user rejected analytics/marketing, remove non-essential scripts
        if (preference === 'essential') {
            // Disable any analytics/tracking scripts that were dynamically loaded
            document.querySelectorAll('script[data-cookie-category="analytics"], script[data-cookie-category="marketing"]').forEach(function(script) {
                if (script.src && script.src !== window.location.href) {
                    // Can't unload external scripts reliably, but flag for compliance
                    window._cookiesEssentialOnly = true;
                }
            });
        }

        // Notify server of consent (for audit / compliance logging)
        var csrftoken = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrftoken) {
            fetch('/cookie-consent/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrftoken.value
                },
                body: 'preference=' + encodeURIComponent(preference)
            }).catch(function() {});
        }
    };

    // Expose consent status for analytics scripts to check
    window.getCookieConsent = function() {
        return localStorage.getItem(CONSENT_KEY) || null;
    };
})();
