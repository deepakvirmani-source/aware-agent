/**
 * sw.js — Service Worker for Aware PWA
 * Strategy:
 *   - Static assets: Cache-first (CSS, JS, fonts)
 *   - API calls: Network-first, fall back to cache
 *   - Offline: Show cached data with offline banner
 */

const CACHE_NAME = 'aware-v2';
const STATIC_CACHE = 'aware-static-v2';
const API_CACHE = 'aware-api-v2';

const STATIC_ASSETS = [
  '/',
  '/static/index.html',
  '/static/style.css',
  '/static/app.js',
  '/manifest.json',
];

// ── Install: cache static assets ─────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Failed to cache some static assets:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// ── Activate: clean up old caches ─────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== API_CACHE)
          .map(k => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

// ── Fetch: routing strategy ───────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // API calls: Network-first, fall back to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithCache(event.request, API_CACHE));
    return;
  }

  // Static assets: Cache-first
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname === '/manifest.json' ||
    url.pathname === '/sw.js'
  ) {
    event.respondWith(cacheFirstWithNetwork(event.request, STATIC_CACHE));
    return;
  }

  // Navigation (HTML pages): Network-first, fall back to cached index
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match('/') || caches.match('/static/index.html'))
    );
    return;
  }

  // Everything else: network with cache fallback
  event.respondWith(networkFirstWithCache(event.request, STATIC_CACHE));
});

// ── Cache strategies ──────────────────────────────────────────────────────────

async function networkFirstWithCache(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      // Clone before consuming
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    // Network failed — try cache
    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // Return offline JSON for API calls
    if (request.url.includes('/api/')) {
      return new Response(
        JSON.stringify({
          offline: true,
          message: 'You are offline. Showing last cached data.',
        }),
        {
          headers: { 'Content-Type': 'application/json' },
          status: 503,
        }
      );
    }
    throw err;
  }
}

async function cacheFirstWithNetwork(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);
  if (cachedResponse) {
    // Background revalidate
    fetch(request)
      .then(response => { if (response.ok) cache.put(request, response); })
      .catch(() => {});
    return cachedResponse;
  }
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    throw err;
  }
}

// ── Background sync ───────────────────────────────────────────────────────────

self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-news') {
    event.waitUntil(
      fetch('/api/refresh', { method: 'POST' })
        .then(() => {
          // Notify all clients
          return self.clients.matchAll().then(clients => {
            clients.forEach(client => client.postMessage({ type: 'NEWS_REFRESHED' }));
          });
        })
        .catch(err => console.warn('[SW] Background sync failed:', err))
    );
  }
});

// ── Push notifications ────────────────────────────────────────────────────────

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  const options = {
    body: data.body || 'New alert for your area',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    vibrate: [100, 50, 100],
    data: { url: data.url || '/' },
    actions: [
      { action: 'view', title: 'View' },
      { action: 'dismiss', title: 'Dismiss' },
    ],
  };
  event.waitUntil(
    self.registration.showNotification(data.title || 'Aware Alert', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action !== 'dismiss') {
    event.waitUntil(
      clients.openWindow(event.notification.data.url || '/')
    );
  }
});
