const CACHE_NAME = "agrisentinel-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Pass network requests through directly to support real-time feeds and dynamic telemetry
  event.respondWith(fetch(event.request));
});

