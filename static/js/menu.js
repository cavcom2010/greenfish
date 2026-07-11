/* ==========================================================================
   Menu page — client-side filtering (category + dietary + search) with
   URL sync, no page reloads. Item modal & cart live in app.js.
   ========================================================================== */

(function () {
    'use strict';

    // ── Menu filters (category + dietary), URL-synced, no reload ──────
    let currentMenuFilters = { category: '', dietary: '' };
    let searchQuery = '';

    function normalizeMenuFilters(filters) {
        return {
            category: filters.category || '',
            dietary: (filters.dietary || '').toLowerCase(),
        };
    }

    function getMenuTitleForFilters(filters) {
        if (filters.category) {
            const pill = document.querySelector(`[data-menu-category="${filters.category}"]`);
            return pill ? (pill.dataset.menuLabel || pill.textContent.trim()) : 'Full Menu';
        }
        if (filters.dietary) {
            const label = filters.dietary
                .replace(/-/g, ' ')
                .replace(/\b\w/g, letter => letter.toUpperCase());
            return `${label} options`;
        }
        return 'Full Menu';
    }

    function updateMenuUrl(filters, replace = false) {
        const url = new URL(window.location.href);

        if (filters.category) {
            url.searchParams.set('category', filters.category);
        } else {
            url.searchParams.delete('category');
        }

        if (filters.dietary) {
            url.searchParams.set('dietary', filters.dietary);
        } else {
            url.searchParams.delete('dietary');
        }

        const nextUrl = url.pathname + (url.search ? url.search : '') + url.hash;
        if (replace) {
            history.replaceState(filters, '', nextUrl);
        } else {
            history.pushState(filters, '', nextUrl);
        }
    }

    function applyMenuFilters(nextFilters, options = {}) {
        currentMenuFilters = normalizeMenuFilters(nextFilters);

        const menuGrid = document.getElementById('menuGrid');
        const title = document.getElementById('menuSectionTitle');
        const cards = menuGrid ? Array.from(menuGrid.querySelectorAll('.menu-card')) : [];
        let visibleCount = 0;

        cards.forEach(card => {
            const cardCategoryId = card.dataset.categoryId || '';
            const cardDietaryTags = (card.dataset.dietaryTags || '')
                .split(',')
                .map(tag => tag.trim().toLowerCase())
                .filter(Boolean);
            const name = (card.dataset.searchName || '').toLowerCase();
            const desc = (card.dataset.searchDesc || '').toLowerCase();

            const matchesCategory = !currentMenuFilters.category || cardCategoryId === currentMenuFilters.category;
            const matchesDietary = !currentMenuFilters.dietary || cardDietaryTags.includes(currentMenuFilters.dietary);
            const matchesSearch = !searchQuery || name.includes(searchQuery) || desc.includes(searchQuery);
            const visible = matchesCategory && matchesDietary && matchesSearch;

            card.classList.toggle('search-hidden', !visible);
            if (visible) visibleCount++;
        });

        if (title) {
            title.textContent = getMenuTitleForFilters(currentMenuFilters);
        }

        document.querySelectorAll('[data-menu-category]').forEach(pill => {
            const pillCategory = pill.dataset.menuCategory || '';
            const isActive = pillCategory === currentMenuFilters.category;
            pill.classList.toggle('active', isActive);
            pill.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        document.querySelectorAll('[data-menu-dietary]').forEach(pill => {
            const pillDietary = pill.dataset.menuDietary || '';
            const isActive = pillDietary === currentMenuFilters.dietary && pillDietary !== '';
            pill.classList.toggle('active', isActive);
            pill.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        const clearPill = document.querySelector('[data-menu-clear]');
        if (clearPill) {
            clearPill.hidden = !currentMenuFilters.dietary;
        }

        const noResults = document.getElementById('menuNoResults');
        if (noResults) {
            noResults.hidden = visibleCount > 0;
        }

        if (options.updateUrl !== false) {
            updateMenuUrl(currentMenuFilters, Boolean(options.replaceUrl));
        }
    }

    function readMenuFiltersFromUrl() {
        const params = new URLSearchParams(window.location.search);
        return normalizeMenuFilters({
            category: params.get('category') || '',
            dietary: params.get('dietary') || '',
        });
    }

    document.addEventListener('click', function (event) {
        const categoryPill = event.target.closest('[data-menu-category]');
        const dietaryPill = event.target.closest('[data-menu-dietary]');
        if (!categoryPill && !dietaryPill) return;

        event.preventDefault();

        if (categoryPill) {
            applyMenuFilters({
                category: categoryPill.dataset.menuCategory || '',
                dietary: currentMenuFilters.dietary,
            });
        }

        if (dietaryPill) {
            const selected = dietaryPill.dataset.menuDietary || '';
            applyMenuFilters({
                category: currentMenuFilters.category,
                // Tapping the active pill toggles it off
                dietary: selected === currentMenuFilters.dietary ? '' : selected,
            });
        }
    });

    window.addEventListener('popstate', function (event) {
        const nextFilters = event.state ? normalizeMenuFilters(event.state) : readMenuFiltersFromUrl();
        applyMenuFilters(nextFilters, { updateUrl: false });
    });

    // ── Search ─────────────────────────────────────────────────────────
    const searchInput = document.getElementById('menuSearchInput');
    const clearBtn = document.getElementById('menuSearchClear');

    if (searchInput) {
        let debounceTimer;

        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                searchQuery = this.value.trim().toLowerCase();
                if (clearBtn) clearBtn.classList.toggle('visible', searchQuery.length > 0);
                applyMenuFilters(currentMenuFilters, { updateUrl: false });
            }, 150);
        });

        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                searchInput.value = '';
                searchQuery = '';
                clearBtn.classList.remove('visible');
                applyMenuFilters(currentMenuFilters, { updateUrl: false });
                searchInput.focus();
            });
        }

        document.addEventListener('keydown', function (e) {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
            if (e.key === 'Escape' && document.activeElement === searchInput) {
                searchInput.blur();
            }
        });
    }

    // ── Initial state from URL ─────────────────────────────────────────
    const initialFilters = readMenuFiltersFromUrl();
    applyMenuFilters(initialFilters, { updateUrl: false });
    history.replaceState(initialFilters, '', window.location.href);
})();
