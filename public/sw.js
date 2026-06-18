// Service Worker — Pronunciation Builder 🇬🇧
// Necessário para o Chrome/Android considerar o site "instalável" como PWA.
// Faz cache básico do app shell para abrir mais rápido e funcionar com conexão instável.

const CACHE_NAME = "pronunciation-builder-v1";
const APP_SHELL = [
  "./index.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Estratégia: network-first para o HTML (sempre pega a versão mais nova quando online),
// cache-first para o resto (ícones, manifest). Nunca intercepta chamadas ao Firebase/Google
// (deixa passar direto para a rede, pois autenticação e Firestore exigem dados sempre frescos).
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Não intercepta requests de outros domínios (CDNs, Firebase, Google Fonts, etc.)
  if (url.origin !== self.location.origin) return;

  if (event.request.mode === "navigate" || url.pathname.endsWith("index.html")) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request).then((cached) => cached || caches.match("./index.html")))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
