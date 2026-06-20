// Catálogo de eventos del bus (ver server/event_bus.py).
// Mantener sincronizado con el contrato del backend.

export type OrionState = "ESCUCHANDO" | "PENSANDO" | "HABLANDO";

export type LogRole = "user" | "ai" | "sys" | "err" | "file";

export interface ServerEvent {
  type: string;
  payload: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: LogRole;
  text: string;
  ts: number;
  /** Backend turn_id — presente cuando el mensaje llegó vía streaming.
   *  Permite identificar el mismo mensaje a través de múltiples chunks. */
  turnId?: string;
  /** True mientras el mensaje sigue recibiendo chunks. False (o undefined)
   *  cuando llegó el chunk final. Útil para mostrar un cursor parpadeante
   *  en la UI durante la transcripción. */
  streaming?: boolean;
  /** True cuando un evento `log` posterior ya confirmó el texto final.
   *  El dedup de logs lo usa para no "reconfirmar" el mismo mensaje y
   *  pushear duplicados. Sólo aplica a mensajes que vinieron por
   *  `chat.stream` (tienen turnId). */
  confirmedByLog?: boolean;
}

export interface ConnectionStatus {
  connected: boolean;
  reconnecting: boolean;
  attempts: number;
}
