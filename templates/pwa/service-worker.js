// Service Worker for GreenFish PWA — cache version: {{ CACHE_VERSION }}

const CACHE_VERSION = 'greenfish-{{ CACHE_VERSION }}';
const STATIC_CACHE = CACHE_VERSION + '-static';
const RUNTIME_CACHE = CACHE_VERSION + '-runtime';
const OFFLINE_URL = '/pwa/offline/';

// Pre-cached app shell: critical CSS, fonts, icons, vendor libs, and the
// most important navigation pages so the app loads near-instantly offline.
const STATIC_ASSETS = [
    '/',
    '/menu/',
    '/accounts/app/',
    '/rewards/',
    '/offers/',
    OFFLINE_URL,
    '/pwa/manifest.json',
    // Icons
    '/static/icons/icon-72.png',
    '/static/icons/icon-96.png',
    '/static/icons/icon-128.png',
    '/static/icons/icon-180.png',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    // Design system
    '/static/css/tokens.css',
    '/static/css/theme-evergreen.css',
    '/static/css/base.css',
    '/static/css/components.css',
    '/static/css/shell.css',
    // Fonts
    '/static/fonts/inter.css',
    // Vendor
    '/static/vendor/phosphor/regular/style.css',
    '/static/vendor/phosphor/fill/style.css',
    '/static/vendor/phosphor/bold/style.css',
    '/static/vendor/htmx.min.js',
];

const CACHEABLE_NAVIGATION_PATHS = new Set([
    '/', '/menu/', '/accounts/app/', '/rewards/', '/offers/', '/large-orders/',
    '/accounts/profile/', '/accounts/order-history/', '/loyalty/', '/loyalty/refer/',
    '/accounts/privacy/',
]);

const STATIC_PREFIXES = ['/static/'];

const UNCACHEABLE_PREFIXES = [
    '/admin/', '/media/', '/payments/', '/pwa/push/',
    '/orders/checkout/', '/orders/cart/', '/orders/confirmation/',
];

// ── Install ──────────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => cache.addAll(STATIC_ASSETS).catch(() => {}))
            .then(() => self.skipWaiting())
    );
});

// ── Activate: purge old caches ───────────────────────────────────────────
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) => {
            return Promise.all(
                names
                    .filter((n) => n !== STATIC_CACHE && n !== RUNTIME_CACHE)
                    .map((n) => caches.delete(n))
            );
        }).then(() => self.clients.claim())
    );
});

// ── Helpers ──────────────────────────────────────────────────────────────
function isSameOrigin(url) {
    return url.origin === self.location.origin;
}
function isStatic(pathname) {
    return STATIC_PREFIXES.some((p) => pathname.startsWith(p));
}
function isUncacheable(pathname) {
    return UNCACHEABLE_PREFIXES.some((p) => pathname.startsWith(p));
}
function isCacheableNav(pathname) {
    return CACHEABLE_NAVIGATION_PATHS.has(pathname);
}

async function putIn(cacheName, request, response) {
    try {
        const cache = await caches.open(cacheName);
        await cache.put(request, response.clone());
    } catch (_) { /* quota exceeded — network will serve next time */ }
}

// ── Navigation: network-first, fall back to cache, then offline page ─────
async function navRespond(event, pathname) {
    try {
        const network = await fetch(event.request);
        if (network.ok && isCacheableNav(pathname)) {
            await putIn(RUNTIME_CACHE, event.request, network);
        }
        return network;
    } catch (_) {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        return caches.match(OFFLINE_URL);
    }
}

// ── Static: cache-first, update in background ────────────────────────────
async function staticRespond(event) {
    const cached = await caches.match(event.request);
    if (cached) return cached;
    try {
        const network = await fetch(event.request);
        if (network.ok) await putIn(STATIC_CACHE, event.request, network);
        return network;
    } catch (_) {
        return cached; // may be undefined if never cached → browser handles it
    }
}

// ── Fetch ────────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (!isSameOrigin(url)) return;
    if (isUncacheable(url.pathname)) return;

    if (event.request.mode === 'navigate') {
        event.respondWith(navRespond(event, url.pathname));
    } else if (isStatic(url.pathname) || STATIC_ASSETS.includes(url.pathname)) {
        event.respondWith(staticRespond(event));
    }
});

// ── Push ─────────────────────────────────────────────────────────────────
self.addEventListener('push', (event) => {
    let data = {};
    try { data = event.data.json(); } catch (_) {
        data = {
            title: 'Order Update',
            body: event.data ? event.data.text() : 'You have a new notification',
        };
    }
    event.waitUntil(self.registration.showNotification(data.title || 'Order Update', {
        body: data.body || 'Tap for details',
        icon: data.icon || '/static/icons/icon-192.png',
        badge: data.badge || '/static/icons/icon-72.png',
        tag: data.tag || 'order',
        requireInteraction: !!data.requireInteraction,
        data: data.data || {},
        actions: data.actions || [],
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    let url = '/';
    const d = event.notification.data;
    if (d && d.orderNumber) url = '/orders/track/' + d.orderNumber + '/';
    else if (d && d.url) url = d.url;

    event.waitUntil(
        self.clients.matchAll({ type: 'window' }).then((windows) => {
            for (const w of windows) {
                if (w.url.includes(url.replace(/\/$/, '')) && 'focus' in w) return w.focus();
            }
            return self.clients.openWindow ? self.clients.openWindow(url) : null;
        })
    );
});

self.addEventListener('message', (event) => {
    if (event.data === 'skipWaiting') self.skipWaiting();
});
