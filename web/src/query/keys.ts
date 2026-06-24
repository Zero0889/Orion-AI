/**
 * Registro central de queryKeys de TanStack Query.
 *
 * Mantener TODAS las keys acá tiene dos beneficios:
 *
 *  1. **Bridge WS → invalidation** (en stores/orion.ts) usa las mismas
 *     keys que los `useQuery` de los paneles — si renombrás una key
 *     acá, rompe en compile time tanto el consumidor como el bridge.
 *
 *  2. **Refactor seguro** — el día que necesitemos jerarquía
 *     (`["iot", "devices", id]` invalidando todo `["iot"]`), la
 *     herramienta para hacerlo bien vive en un solo lugar.
 *
 * Convención: arrays planos cuando la query no tiene parámetros,
 * funciones que devuelven arrays cuando dependen de un id.
 */

export const QUERY_KEYS = {
  notes: ["notes"] as const,
  memory: ["memory"] as const,
  conversations: ["conversations"] as const,
  conversation: (id: string) => ["conversations", id] as const,
  settingsTheme: ["settings", "theme"] as const,
  notifications: ["notifications"] as const,
  notificationsList: (unread: boolean) => ["notifications", "list", { unread }] as const,
  notificationsStatus: ["notifications", "status"] as const,
  iot: {
    all: ["iot"] as const,
    devices: ["iot", "devices"] as const,
    scenes: ["iot", "scenes"] as const,
    sensors: ["iot", "sensors"] as const,
    paused: ["iot", "paused"] as const,
  },
  orchestra: ["orchestra"] as const,
  mcpServers: ["mcp", "servers"] as const,
  settingsBrain: ["settings", "brain"] as const,
} as const;
