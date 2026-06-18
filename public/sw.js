// Service Worker — Pronunciation Builder 🇬🇧
// Necessário para o Chrome/Android considerar o site "instalável" como PWA.
// Faz cache básico do app shell para abrir mais rápido e funcionar com conexão instável.

const CACHE_NAME = "pronunciation-builder-v2";
const APP_SHELL = [
  "./",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .catch((err) => console.warn("Falha ao popular cache do app shell:", err))
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

// Estratégia: network-first para navegação/HTML (sempre tenta a versão mais nova),
// cache-first para o resto (ícones, manifest). Nunca intercepta chamadas ao Firebase/Google
// (deixa passar direto para a rede, pois autenticação e Firestore exigem dados sempre frescos).
// Importante: só intercepta GET — outros métodos (POST, etc.) sempre vão direto pra rede.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);

  // Não intercepta requests de outros domínios (CDNs, Firebase, Google Fonts, etc.)
  if (url.origin !== self.location.origin) return;

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(event.request);
          if (cached) return cached;
          const fallback = await caches.match("./");
          if (fallback) return fallback;
          // Último recurso: deixa o navegador tentar de novo e mostrar seu próprio erro de rede,
          // em vez de o SW lançar uma exceção não tratada.
          return fetch(event.request);
        })
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
