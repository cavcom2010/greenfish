// Service Worker for PWA

const CACHE_NAME = 'restaurant-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/base.css',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
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
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch event - serve from cache or network
self.addEventListener('fetch', (event) => {
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }
    
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                // Return cached response or fetch from network
                if (response) {
                    return response;
                }
                return fetch(event.request)
                    .then((networkResponse) => {
                        // Cache successful GET requests
                        if (networkResponse.ok && event.request.url.startsWith(self.location.origin)) {
                            const clonedResponse = networkResponse.clone();
                            caches.open(CACHE_NAME).then((cache) => {
                                cache.put(event.request, clonedResponse);
                            });
                        }
                        return networkResponse;
                    })
                    .catch(() => {
                        // Return offline page for navigation requests
                        if (event.request.mode === 'navigate') {
                            return caches.match('/pwa/offline/');
                        }
                    });
            })
    );
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
