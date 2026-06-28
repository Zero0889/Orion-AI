/* eslint-disable no-undef */
/**
 * Orion Service Worker — runtime cache para que el frontend cargue
 * instantáneo en visitas repetidas (especialmente útil desde el móvil
 * vía Tailscale, donde la primera carga puede ser lenta).
 *
 * Estrategia: **stale-while-revalidate** para GET HTTP idempotentes.
 *   1. Respondemos desde cache si existe → load instantáneo.
 *   2. En paralelo refetcheamos y actualizamos la cache.
 *   3. La próxima carga ya tiene el bundle nuevo.
 *
 * Nunca cacheamos:
 *   - `/api/*`  → server-state, debe ser fresco siempre.
 *   - `/ws`     → WebSocket, ni siquiera pasa por el handler de fetch.
 *   - peticiones que no son GET (POST/PUT/DELETE).
 *   - peticiones con `Range:` (rangos parciales).
 *
 * No hace pre-cache de archivos específicos: Vite los hashea por build
 * y mantener una lista quedaría desincronizada en cada release.
 */

const CACHE = "orion-shell-v1";

self.addEventListener("install", (event) => {
  // Activación inmediata — sin tab antigua que mantener viva.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  if (req.headers.has("range")) return;

  const url = new URL(req.url);
  // Mismo origen sólo — no interceptamos terceros.
  if (url.origin !== self.location.origin) return;
  // API y WS no se cachean.
  if (url.pathname.startsWith("/api/")) return;
  if (url.pathname === "/ws") return;

  event.respondWith(staleWhileRevalidate(req));
});

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(req);
  const networkPromise = fetch(req)
    .then((res) => {
      // Sólo cacheamos respuestas OK y opacas (cross-origin no aplica acá
      // por el filtro de origin, pero por las dudas).
      if (res && res.status === 200 && res.type === "basic") {
        cache.put(req, res.clone()).catch(() => {});
      }
      return res;
    })
    .catch(() => cached);
  return cached || networkPromise;
}
