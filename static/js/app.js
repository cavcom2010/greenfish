/* ==========================================================================
   App JavaScript — unified shell interactions (all viewports)
   Cart drawer, toasts, item modal/bottom sheet, service toggle,
   lazy images, scroll-to-top, PWA registration, cookie consent.
   ========================================================================== */

(function () {
    'use strict';

    function revealLoadedImages(root = document) {
        root.querySelectorAll('img[loading="lazy"]').forEach((image) => {
            if (image.complete && image.naturalWidth > 0) {
                image.classList.add('loaded');
                return;
            }
            image.addEventListener('load', () => image.classList.add('loaded'), { once: true });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => revealLoadedImages());
    } else {
        revealLoadedImages();
    }
    document.addEventListener('htmx:afterSwap', (event) => revealLoadedImages(event.target));

    const ORDER_ROUTES = {
        addToCart: '/orders/cart/add/',
        serviceType: '/orders/service-type/',
        cartDrawer: '/orders/cart/drawer/'
    };
    const maxCartItemQuantity = Math.max(1, parseInt(window.APP_CONFIG?.maxCartItemQuantity || '20', 10) || 20);

    function clampCartQuantity(quantity, allowZero = false) {
        const parsed = parseInt(quantity, 10);
        if (allowZero && parsed <= 0) return 0;
        return Math.min(maxCartItemQuantity, Math.max(1, Number.isNaN(parsed) ? 1 : parsed));
    }

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

        const content = document.getElementById('cartDrawerContent');
        if (content) {
            fetch(ORDER_ROUTES.cartDrawer, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.text())
            .then(html => { content.innerHTML = html; })
            .catch(() => {
                content.innerHTML = `
                    <div class="loading-block">
                        <p>Could not load basket. <a href="/orders/cart/" class="text-brand">View full basket</a></p>
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

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && cartDrawerOpen) window.closeCartDrawer();
    });

    // Drawer quantity update
    window.drawerUpdateQty = function(itemId, newQty) {
        if (newQty < 1) {
            showToast('Use the trash icon to remove items', 'info', 2000);
            return;
        }
        if (newQty > maxCartItemQuantity) {
            showToast(`Need more than ${maxCartItemQuantity}? Send a large order request.`, 'info', 3000);
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

    // Favourite toggle inside the item modal: swap the heart in place
    // instead of the form's full-page fallback navigation.
    document.addEventListener('submit', function(e) {
        const form = e.target.closest('[data-favorite-form]');
        if (!form) return;

        e.preventDefault();
        fetch(form.action, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(res => {
                if (!res.ok) throw new Error('Favourite toggle failed');
                return res.json();
            })
            .then(data => {
                const btn = form.querySelector('.favorite-btn');
                const icon = btn.querySelector('i');
                const label = btn.querySelector('[data-favorite-label]');
                btn.classList.toggle('is-favorite', data.is_favorite);
                icon.className = data.is_favorite ? 'ph-fill ph-heart' : 'ph ph-heart';
                if (label) label.textContent = data.is_favorite ? 'Saved to favourites' : 'Save to favourites';
                if (data.message) showToast(data.message, 'success', 2000);
            })
            .catch(() => {
                showToast('Could not update favourites. Please try again.', 'error');
            });
    });

    // ── Mobile hamburger menu ────────────────────────────────────────────
    let mobileMenuOpen = false;

    window.openMobileMenu = function() {
        const overlay = document.getElementById('mobileMenuOverlay');
        if (!overlay || mobileMenuOpen) return;
        mobileMenuOpen = true;
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        document.getElementById('mobileMenuButton')?.setAttribute('aria-expanded', 'true');
    };

    window.closeMobileMenu = function() {
        const overlay = document.getElementById('mobileMenuOverlay');
        if (!overlay || !mobileMenuOpen) return;
        mobileMenuOpen = false;
        overlay.classList.remove('active');
        document.body.style.overflow = '';
        document.getElementById('mobileMenuButton')?.setAttribute('aria-expanded', 'false');
    };

    window.closeMobileMenuOnOverlay = function(e) {
        if (e.target === e.currentTarget) window.closeMobileMenu();
    };

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && mobileMenuOpen) window.closeMobileMenu();
    });

    // Re-open the cookie banner so the visitor can change their choice.
    window.openCookiePreferences = function() {
        window.closeMobileMenu();
        const banner = document.getElementById('cookieConsentBanner');
        if (banner) banner.classList.add('visible');
    };

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

    // ── Item Modal / Bottom Sheet ────────────────────────────────────────
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
                    <div class="loading-block">
                        <p>Error loading item. Please try again.</p>
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

    const modalOverlay = document.getElementById('itemModalDesktop');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) window.closeItemModal();
        });
    }

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
            updateModalQuantityState();
            updateModalTotal();
        }

        bindModalEvents();
    }

    function bindModalEvents() {
        const content = document.getElementById('modalDesktopContent');
        if (!content) return;

        content.querySelectorAll('.qty-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const change = parseInt(btn.dataset.change);
                modalQuantity = clampCartQuantity(modalQuantity + change);
                updateModalQuantityState();
                updateModalTotal();
            });
        });

        content.querySelectorAll('.modifier-checkbox').forEach(cb => {
            cb.addEventListener('change', updateModalTotal);
        });

        const addBtn = document.getElementById('modalAddBtn');
        if (addBtn) {
            addBtn.addEventListener('click', addToCartFromModal);
        }
    }

    function updateModalQuantityState() {
        modalQuantity = clampCartQuantity(modalQuantity);
        const display = document.getElementById('modalQtyDisplay');
        if (display) display.textContent = modalQuantity;

        document.querySelectorAll('#modalDesktopContent .qty-btn').forEach(btn => {
            const change = parseInt(btn.dataset.change || '0', 10);
            btn.disabled = (change < 0 && modalQuantity <= 1) || (change > 0 && modalQuantity >= maxCartItemQuantity);
        });

        const largeOrderCue = document.querySelector('#modalDesktopContent [data-large-order-cue]');
        if (largeOrderCue) {
            largeOrderCue.hidden = modalQuantity < maxCartItemQuantity;
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
                        btn.innerHTML = originalHTML;
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.style.background = '';
                    }, 700);
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
                    btn.style.background = '';
                }, 2000);
            });
    }

    function getModalLoadingHTML() {
        return `
            <div class="loading-block">
                <div class="spinner"></div>
                <p>Loading item details...</p>
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

// ── PWA: Service Worker, Install Prompt, Push Toggle, Connectivity  ────
(function() {
    'use strict';

    var deferredPrompt = null;
    var installBtn = document.getElementById('installBtn');
    var pushToggleBtn = document.getElementById('pushToggleBtn');
    var pushToggleLabel = document.getElementById('pushToggleLabel');
    var snackbarTimer = null;

    var swUrl = window.APP_CONFIG && window.APP_CONFIG.serviceWorkerUrl;
    var registration = null;

    function showSnackbar(msg, duration) {
        var el = document.getElementById('snackbar');
        if (!el) return;
        if (snackbarTimer) clearTimeout(snackbarTimer);
        el.textContent = msg;
        el.classList.add('show');
        snackbarTimer = setTimeout(function() { el.classList.remove('show'); }, duration || 4000);
    }

    // ── Install prompt ──────────────────────────────────────────────
    window.addEventListener('beforeinstallprompt', function(e) {
        e.preventDefault();
        deferredPrompt = e;
        if (installBtn) installBtn.hidden = false;
    });

    window.addEventListener('appinstalled', function() {
        deferredPrompt = null;
        if (installBtn) installBtn.hidden = true;
        if (window.showToast) showToast('App installed — order in one tap!', 'success', 2500);
    });

    window.pwaInstall = function() {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function(result) {
            if (result.outcome === 'accepted') {
                if (installBtn) installBtn.hidden = true;
            }
            deferredPrompt = null;
        });
    };

    // Hide install button if already in standalone mode
    if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) {
        if (installBtn) installBtn.hidden = true;
    }

    // ── SW registration + update detection ──────────────────────────
    if ('serviceWorker' in navigator && swUrl) {
        navigator.serviceWorker.register(swUrl).then(function(reg) {
            registration = reg;

            // Detect waiting service worker → prompt user to refresh
            reg.addEventListener('updatefound', function() {
                var newWorker = reg.installing;
                if (!newWorker) return;
                newWorker.addEventListener('statechange', function() {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        showSnackbar('New version available \u2014 tap to refresh', 0);
                        document.getElementById('snackbar').style.cursor = 'pointer';
                        document.getElementById('snackbar').onclick = function() {
                            newWorker.postMessage('skipWaiting');
                            window.location.reload();
                        };
                    }
                });
            });
        }).catch(function() {});
    }

    // Detect controller change (new SW took over)
    navigator.serviceWorker && navigator.serviceWorker.addEventListener('controllerchange', function() {
        showSnackbar('App updated! Reloading\u2026', 2000);
        setTimeout(function() { window.location.reload(); }, 1000);
    });

    // ── Push helpers ────────────────────────────────────────────────
    function urlBase64ToUint8Array(b64) {
        var padding = '='.repeat((4 - b64.length % 4) % 4);
        var base64 = (b64 + padding).replace(/-/g, '+').replace(/_/g, '/');
        var raw = window.atob(base64);
        var out = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
        return out;
    }

    function getCsrfHeader() {
        var el = document.querySelector('[name=csrfmiddlewaretoken]');
        return el ? el.value : '';
    }

    function pushSubscribed() {
        return registration && registration.pushManager.getSubscription().then(function(s) { return !!s; });
    }

    function updatePushToggleUI() {
        if (!pushToggleBtn || !pushToggleLabel) return;
        if (!('PushManager' in window) || !(window.APP_CONFIG && window.APP_CONFIG.vapidPublicKey)) {
            pushToggleBtn.className = 'push-toggle blocked';
            pushToggleLabel.textContent = 'Push unavailable';
            return;
        }
        if (Notification.permission === 'denied') {
            pushToggleBtn.className = 'push-toggle blocked';
            pushToggleBtn.onclick = null;
            pushToggleLabel.textContent = 'Notifications blocked';
            return;
        }
        pushSubscribed().then(function(sub) {
            if (sub) {
                pushToggleBtn.className = 'push-toggle on';
                pushToggleLabel.textContent = 'Push: ON';
            } else {
                pushToggleBtn.className = 'push-toggle';
                pushToggleLabel.textContent = 'Push: OFF';
            }
        });
    }

    // Called on user engagement — subscribes to push
    window.subscribeToNotifications = function() {
        if (!registration || !('PushManager' in window)) return Promise.resolve(false);
        var vapidKey = window.APP_CONFIG && window.APP_CONFIG.vapidPublicKey;
        var subscribeUrl = window.APP_CONFIG && window.APP_CONFIG.pushSubscribeUrl;
        if (!vapidKey || !subscribeUrl) return Promise.resolve(false);

        return Notification.requestPermission().then(function(perm) {
            if (perm !== 'granted') return false;
            return registration.pushManager.getSubscription().then(function(existing) {
                var subPromise = existing || registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(vapidKey)
                });
                return subPromise.then(function(subscription) {
                    return fetch(subscribeUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfHeader() },
                        body: JSON.stringify({
                            subscription: subscription,
                            device_name: navigator.userAgentData ? navigator.userAgentData.platform + ' ' + navigator.userAgentData.brands.map(function(b) { return b.brand; }).join(' ') : (navigator.platform || 'unknown')
                        })
                    }).then(function() { return true; });
                });
            });
        }).catch(function() { return false; });
    };

    window.unsubscribeFromPush = function() {
        if (!registration) return Promise.resolve(false);
        return registration.pushManager.getSubscription().then(function(sub) {
            if (!sub) return false;
            var url = window.APP_CONFIG && window.APP_CONFIG.pushSubscribeUrl;
            return sub.unsubscribe().then(function(ok) {
                if (ok && url) {
                    fetch(url.replace(/subscribe_push\/$/, '') + 'unsubscribe-push/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfHeader() },
                        body: JSON.stringify({ endpoint: sub.endpoint })
                    }).catch(function() {});
                }
                return ok;
            });
        });
    };

    window.togglePushNotifications = function() {
        pushSubscribed().then(function(sub) {
            if (sub) {
                window.unsubscribeFromPush().then(function() {
                    if (window.showToast) showToast('Push notifications turned off', 'info', 2000);
                    updatePushToggleUI();
                });
            } else {
                window.subscribeToNotifications().then(function(ok) {
                    if (ok) {
                        if (window.showToast) showToast('Push notifications turned on!', 'success', 2000);
                    } else if (Notification.permission === 'denied') {
                        if (window.showToast) showToast('Notifications are blocked in your browser settings', 'error', 3000);
                    }
                    updatePushToggleUI();
                });
            }
        });
    };

    // pushsubscriptionchange: browser rotated keys → resubscribe
    registration && registration.pushManager.addEventListener('pushsubscriptionchange', function() {
        window.subscribeToNotifications().catch(function() {});
    });

    // permissionchange: user changed notification permission in browser settings
    if ('permissions' in navigator && navigator.permissions.query) {
        navigator.permissions.query({ name: 'notifications' }).then(function(permStatus) {
            permStatus.addEventListener('change', function() {
                updatePushToggleUI();
                if (window.showToast) {
                    showToast('Notification permission changed', 'info', 2000);
                }
            });
        }).catch(function() {});
    }

    // Initial push toggle refresh (deferred so DOM exists)
    if (pushToggleBtn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', updatePushToggleUI);
        } else {
            updatePushToggleUI();
        }
    }

    // ── Online / offline connectivity toasts ────────────────────────
    window.addEventListener('online', function() {
        showSnackbar('You\u2019re back online', 3000);
    });
    window.addEventListener('offline', function() {
        showSnackbar('You\u2019re offline \u2014 cached pages still load', 4000);
    });

})();


// ── Cookie Consent (GDPR / UK ICO) ─────────────────────────────────────
(function() {
    'use strict';

    var CONSENT_KEY = 'cookie_consent';
    var banner = document.getElementById('cookieConsentBanner');

    if (!localStorage.getItem(CONSENT_KEY)) {
        setTimeout(function() {
            if (banner) banner.classList.add('visible');
        }, 1000);
    }

    window.acceptCookies = function(preference) {
        localStorage.setItem(CONSENT_KEY, preference);

        if (banner) banner.classList.remove('visible');

        if (preference === 'essential') {
            window._cookiesEssentialOnly = true;
        }

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

    window.getCookieConsent = function() {
        return localStorage.getItem(CONSENT_KEY) || null;
    };
})();
