/* ============================================================
   Service Worker — offline support + asset caching
   ============================================================ */

const CACHE_NAME    = 'forexbot-v1';
const OFFLINE_URL   = '/offline/';

// Assets to pre-cache on install
const PRECACHE = [
  '/',
  '/dashboard/',
  '/bots/',
  '/strategies/',
  '/static/css/main.css',
  '/static/js/api.js',
  '/static/js/websocket.js',
  '/static/js/main.js',
  '/static/images/favicon.svg',
  OFFLINE_URL,
];

// ── Install ───────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// ── Activate ──────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// ── Fetch strategy ────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET, WebSocket, and cross-origin requests
  if (request.method !== 'GET') return;
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return;
  if (url.origin !== location.origin) return;

  // API calls — network first, fail gracefully (no cache)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(
          JSON.stringify({ success: false, message: 'Offline — no network', offline: true }),
          { headers: { 'Content-Type': 'application/json' } }
        )
      )
    );
    return;
  }

  // Static assets — cache first (immutable)
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        return resp;
      }))
    );
    return;
  }

  // HTML pages — network first, fall back to cache, then offline page
  event.respondWith(
    fetch(request)
      .then(resp => {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        return resp;
      })
      .catch(async () => {
        const cached = await caches.match(request);
        return cached || caches.match(OFFLINE_URL);
      })
  );
});

// ── Background sync for NLP commands sent while offline ───────
self.addEventListener('sync', event => {
  if (event.tag === 'sync-nlp-commands') {
    event.waitUntil(syncOfflineCommands());
  }
});

async function syncOfflineCommands() {
  // Retrieve queued commands from IndexedDB and replay them
  // (IndexedDB access from SW requires idb library — simplified here)
  const cache    = await caches.open('forexbot-offline-queue');
  const requests = await cache.keys();
  for (const req of requests) {
    try {
      await fetch(req);
      await cache.delete(req);
    } catch (e) {
      // Still offline — leave in queue
    }
  }
}

// ── Push notifications ────────────────────────────────────────
self.addEventListener('push', event => {
  const data = event.data?.json() || {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'ForexBot', {
      body:    data.body || '',
      icon:    '/static/images/icons/icon-192.png',
      badge:   '/static/images/icons/icon-72.png',
      tag:     data.tag || 'forexbot',
      data:    data.url ? { url: data.url } : {},
      actions: data.actions || [],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/dashboard/';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      for (const client of windowClients) {
        if (client.url === url && 'focus' in client) return client.focus();
      }
      return clients.openWindow(url);
    })
  );
});