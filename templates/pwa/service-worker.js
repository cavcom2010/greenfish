// Service Worker for PWA

const STATIC_CACHE_NAME = 'restaurant-static-v16';
const RUNTIME_CACHE_NAME = 'restaurant-runtime-v16';
const OFFLINE_URL = '/pwa/offline/';
const STATIC_ASSETS = [
    '/',
    '/menu/',
    OFFLINE_URL,
    '/pwa/manifest.json',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
];
const CACHEABLE_NAVIGATION_PATHS = new Set(['/', '/menu/']);
const STATIC_PREFIXES = ['/static/'];
const UNCACHEABLE_PREFIXES = ['/admin/', '/media/', '/orders/', '/payments/', '/pwa/push/'];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE_NAME)
            .then((cache) => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => ![STATIC_CACHE_NAME, RUNTIME_CACHE_NAME].includes(name))
                    .map((name) => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

function isSameOrigin(requestUrl) {
    return requestUrl.origin === self.location.origin;
}

function isStaticAssetRequest(pathname) {
    return STATIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isUncacheableRequest(pathname) {
    return UNCACHEABLE_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isCacheableNavigation(pathname) {
    return CACHEABLE_NAVIGATION_PATHS.has(pathname);
}

async function cacheResponse(cacheName, request, response) {
    const cache = await caches.open(cacheName);
    await cache.put(request, response.clone());
}

async function handleNavigationRequest(event, pathname) {
    try {
        const response = await fetch(event.request);
        if (response.ok && isCacheableNavigation(pathname)) {
            await cacheResponse(RUNTIME_CACHE_NAME, event.request, response);
        }
        return response;
    } catch (error) {
        const cached = await caches.match(event.request);
        if (cached) {
            return cached;
        }
        return caches.match(OFFLINE_URL);
    }
}

async function handleStaticRequest(event) {
    const cached = await caches.match(event.request);
    if (cached) {
        return cached;
    }

    const response = await fetch(event.request);
    if (response.ok) {
        await cacheResponse(STATIC_CACHE_NAME, event.request, response);
    }
    return response;
}

// Fetch event - serve only selected assets from cache
self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') {
        return;
    }

    const requestUrl = new URL(event.request.url);
    if (!isSameOrigin(requestUrl)) {
        return;
    }

    if (isUncacheableRequest(requestUrl.pathname)) {
        return;
    }

    if (event.request.mode === 'navigate') {
        event.respondWith(handleNavigationRequest(event, requestUrl.pathname));
        return;
    }

    if (isStaticAssetRequest(requestUrl.pathname) || STATIC_ASSETS.includes(requestUrl.pathname)) {
        event.respondWith(handleStaticRequest(event));
    }
});

// Push event - handle incoming push notifications
self.addEventListener('push', (event) => {
    let data = {};
    try {
        data = event.data.json();
    } catch (e) {
        data = {
            title: 'New Update',
            body: event.data ? event.data.text() : 'You have a new notification',
            icon: '/static/icons/icon-192.png',
            badge: '/static/icons/icon-72.png',
            tag: 'general'
        };
    }

    const options = {
        body: data.body || 'You have a new notification',
        icon: data.icon || '/static/icons/icon-192.png',
        badge: data.badge || '/static/icons/icon-72.png',
        tag: data.tag || 'notification',
        requireInteraction: data.requireInteraction || false,
        data: data.data || {},
        actions: data.actions || []
    };

    event.waitUntil(
        self.registration.showNotification(data.title || 'Order Update', options)
    );
});

// Notification click event - handle user clicking notification
self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    const notificationData = event.notification.data;
    let url = '/';

    // Determine URL based on notification type
    if (notificationData.orderNumber) {
        url = `/orders/track/${notificationData.orderNumber}/`;
    } else if (notificationData.url) {
        url = notificationData.url;
    }

    event.waitUntil(
        clients.matchAll({ type: 'window' })
            .then((clientList) => {
                // Check if there's already a window open
                for (const client of clientList) {
                    if (client.url === url && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Open new window if none exists
                if (clients.openWindow) {
                    return clients.openWindow(url);
                }
            })
    );
});

// Message event - handle messages from the main app
self.addEventListener('message', (event) => {
    if (event.data === 'skipWaiting') {
        self.skipWaiting();
    }
});
