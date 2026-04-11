/* ==========================================================================
   Desktop JavaScript — Interactions & UX
   ========================================================================== */

(function () {
    'use strict';

    const ORDER_ROUTES = {
        addToCart: '/orders/cart/add/',
        serviceType: '/orders/service-type/'
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

    // ── Service Type Toggle ──────────────────────────────────────────────
    const serviceToggles = document.querySelectorAll('[data-desktop-service]');
    const serviceTypeInput = document.getElementById('desktopServiceType');

    function applyServiceType(service) {
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
            deliveryCard.style.display = service === 'delivery' ? 'block' : 'none';
        }

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
            applyServiceType(btn.dataset.desktopService);
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
    let modalCurrentService = localStorage.getItem('service_type') || 'pickup';

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
                    updateCartBadge(data.cart_count);
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

    // ── Cart Badge Update ────────────────────────────────────────────────
    function updateCartBadge(count) {
        const badges = document.querySelectorAll('.cart-badge-desktop');
        badges.forEach(badge => {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'flex' : 'none';
        });
    }

    // ── Quick Add to Cart (from menu grid) ───────────────────────────────
    window.quickAddToCart = function (itemId) {
        const csrftoken = getCSRFToken();
        const service = localStorage.getItem('service_type') || 'pickup';

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
                    updateCartBadge(data.cart_count);
                    // Brief visual feedback
                    const card = document.querySelector(`[data-quick-add="${itemId}"]`);
                    if (card) {
                        card.style.transform = 'scale(0.95)';
                        setTimeout(() => { card.style.transform = ''; }, 200);
                    }
                }
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
        applyServiceType(savedService);
    } else if (serviceToggles.length > 0) {
        const firstActive = document.querySelector('[data-desktop-service].active');
        if (firstActive) applyServiceType(firstActive.dataset.desktopService);
    }

})();
