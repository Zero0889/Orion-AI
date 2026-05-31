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
}

export interface ConnectionStatus {
  connected: boolean;
  reconnecting: boolean;
  attempts: number;
}
