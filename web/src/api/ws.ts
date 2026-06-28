/**
 * Cliente WebSocket de O.R.I.O.N.
 *
 * Responsabilidad acotada: gestionar la conexión, exponer un método send,
 * y entregar cada mensaje recibido al handler que se le pase. Sin estado
 * de aplicación dentro — eso vive en stores/orion.ts.
 *
 * Comportamiento:
 *   - Reconexión exponencial 1s → 2s → 4s → ... → max 30s.
 *   - Buffer de envíos pendientes mientras la conexión está caída.
 *   - send(...) es seguro de llamar siempre, no lanza.
 */

import type { ServerEvent } from "@/types";

type Handler = (evt: ServerEvent) => void;
type ConnHandler = (connected: boolean) => void;

const MAX_BACKOFF_MS = 30_000;

export class OrionSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private onEvent: Handler;
  private onConn: ConnHandler;
  private pending: string[] = [];
  private backoffMs = 1_000;
  private reconnectTimer: number | null = null;
  private closedByClient = false;

  constructor(url: string, onEvent: Handler, onConn: ConnHandler) {
    this.url = url;
    this.onEvent = onEvent;
    this.onConn = onConn;
  }

  start(): void {
    this.closedByClient = false;
    this.connect();
  }

  stop(): void {
    this.closedByClient = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
  }

  send(type: string, payload: Record<string, unknown> = {}): void {
    const msg = JSON.stringify({ type, payload });
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(msg);
    } else {
      // Mientras estamos reconectando, encolamos. Cap defensivo.
      if (this.pending.length < 100) this.pending.push(msg);
    }
  }

  private connect(): void {
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.backoffMs = 1_000;
      this.onConn(true);
      // Vaciar la cola de envíos pendientes.
      while (this.pending.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
        const msg = this.pending.shift();
        if (msg !== undefined) this.ws.send(msg);
      }
    };

    this.ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string) as ServerEvent;
        // El server manda un `ping` cada 30s para detectar clientes
        // zombi. Respondemos con `pong` y no lo propagamos al store —
        // no es un evento de dominio, es housekeeping.
        if (data.type === "ping") {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: "pong", payload: {} }));
          }
          return;
        }
        this.onEvent(data);
      } catch {
        // mensaje inválido: ignorar
      }
    };

    this.ws.onerror = () => {
      // El handler se ejecuta antes de onclose; dejamos que onclose maneje
      // la reconexión.
    };

    this.ws.onclose = () => {
      this.onConn(false);
      this.ws = null;
      if (!this.closedByClient) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
      this.connect();
    }, this.backoffMs);
  }
}

export function inferBackendUrl(): { http: string; ws: string } {
  // En modo Vite dev (puerto 5173) el backend FastAPI está en :8765.
  // Cuando el frontend se sirve desde el propio backend (modo prod),
  // usamos el mismo host:puerto.
  const loc = window.location;
  if (loc.port === "5173") {
    return { http: "http://127.0.0.1:8765", ws: "ws://127.0.0.1:8765/ws" };
  }
  const wsProto = loc.protocol === "https:" ? "wss:" : "ws:";
  return {
    http: `${loc.protocol}//${loc.host}`,
    ws: `${wsProto}//${loc.host}/ws`,
  };
}

// ── Device + client_id detection ─────────────────────────────────────
// El backend (orion.core.client_context) lee ?device=&client_id=
// del handshake y los propaga al prompt builder para que Orion adapte
// la respuesta al dispositivo (móvil → más corta, voz-first; desktop
// → larga, con detalle).

export type DeviceKind = "desktop" | "mobile" | "tablet" | "watch" | "tv" | "unknown";

const CLIENT_ID_KEY = "orion.client_id";

/** Detecta el tipo de dispositivo por user-agent + matchMedia. Heurística
 *  pragmática — no perfecta, pero suficiente para adaptar el prompt. Si
 *  no podemos identificarlo, devolvemos "unknown" y el backend deja al
 *  prompt sin override. */
export function detectDevice(): DeviceKind {
  if (typeof navigator === "undefined" || typeof window === "undefined") return "unknown";
  const ua = navigator.userAgent;
  // Smartwatch (Wear OS, Apple Watch — raro, pero soportado).
  if (/watch/i.test(ua)) return "watch";
  // TV (Tizen, WebOS, Android TV).
  if (/smart-?tv|tizen|webos|hbbtv|google.*tv/i.test(ua)) return "tv";
  // Tablet primero — iPad moderno reporta MacIntel + touch.
  const isTouch =
    "maxTouchPoints" in navigator && (navigator as { maxTouchPoints?: number }).maxTouchPoints! > 1;
  if (/ipad|tablet/i.test(ua)) return "tablet";
  if (isTouch && /macintosh/i.test(ua)) return "tablet"; // iPadOS 13+ enmascara como Mac.
  // Móvil: incluye iPhone, Android (no tablet).
  if (/mobi|iphone|ipod|android.*mobile/i.test(ua)) return "mobile";
  // Android sin "Mobile" usualmente es tablet.
  if (/android/i.test(ua)) return "tablet";
  return "desktop";
}

/** Devuelve un client_id persistente en localStorage. La primera carga
 *  genera uno; las siguientes lo reusan. Si localStorage no está
 *  disponible (modo privado de algunos browsers), devuelve "" — el
 *  backend lo trata como cliente legacy. */
export function getClientId(): string {
  try {
    const existing = window.localStorage.getItem(CLIENT_ID_KEY);
    if (existing) return existing;
    const fresh =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID().slice(0, 12)
        : `c${Date.now().toString(36)}`;
    window.localStorage.setItem(CLIENT_ID_KEY, fresh);
    return fresh;
  } catch {
    return "";
  }
}

/** Toma la URL base del WS de `inferBackendUrl` y le agrega los query
 *  params de identificación. El backend (ws.py) los lee del handshake. */
export function buildWsUrl(): string {
  const { ws } = inferBackendUrl();
  const device = detectDevice();
  const clientId = getClientId();
  const params = new URLSearchParams();
  if (device !== "unknown") params.set("device", device);
  if (clientId) params.set("client_id", clientId);
  const qs = params.toString();
  return qs ? `${ws}?${qs}` : ws;
}
