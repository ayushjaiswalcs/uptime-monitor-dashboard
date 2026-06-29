/**
 * service-worker.js — PWA service worker for the GitHub Pages dashboard.
 *
 * Paths are RELATIVE because GitHub Pages serves project sites from a subpath
 * (https://user.github.io/repo/), not the domain root.
 *
 * Strategy:
 *   Shell (HTML/CSS/JS/icons) → cache-first
 *   status.json (cross-origin) → network-first, fall back to last cached copy
 *
 * Bump CACHE_VERSION when you change dashboard files so phones get fresh assets.
 */

const CACHE_VERSION = 'v1';
const CACHE_NAME    = `uptime-pages-${CACHE_VERSION}`;

const SHELL_ASSETS = [
  './',
  './index.html',
  './style.css',
  './app.js',
  './manifest.json',
  './icons/icon-192.svg',
  './icons/icon-512.svg',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys
        .filter(k => k.startsWith('uptime-pages-') && k !== CACHE_NAME)
        .map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = event.request.url;

  // status.json (any origin) — always try the network first for fresh data
  if (url.includes('status.json')) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Everything else — cache-first shell
  event.respondWith(cacheFirst(event.request));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    // Cache a clone so we can show last-known data when offline
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached ?? new Response('[]', { headers: { 'Content-Type': 'application/json' } });
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}
