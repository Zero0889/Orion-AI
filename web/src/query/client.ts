/**
 * QueryClient singleton.
 *
 * Lo exportamos como módulo para que el bridge WS→invalidateQueries
 * (en stores/orion.ts) lo pueda importar sin tener que llegar via
 * React context. El mismo cliente lo monta `QueryClientProvider` en
 * App.tsx para que los componentes lo consuman via hooks.
 *
 * Defaults justificados para Orion:
 *
 *  - staleTime: 30s. Las queries no se refetchean automáticamente cada
 *    vez que un componente se re-monta dentro de ese rango. Nuestro
 *    modelo de invalidación es por evento WS (note.changed, iot.action,
 *    etc.) — el polling implícito no aporta y solo genera ruido sobre
 *    el backend local.
 *
 *  - refetchOnWindowFocus: false. La ventana Orion suele estar abierta
 *    en background mientras el usuario habla; refetchar todo cuando
 *    vuelve foco genera flashes innecesarios y compite con la voz por
 *    el event loop.
 *
 *  - retry: 1. Si una llamada falla, reintentamos UNA vez (típico
 *    network flake). Más reintentos suelen ser delay sin payoff cuando
 *    el backend está caído de verdad — mejor mostrar error y dejar que
 *    el user reintente.
 */

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
