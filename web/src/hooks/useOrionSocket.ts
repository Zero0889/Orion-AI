/**
 * useOrionSocket — conecta el frontend al backend FastAPI.
 *
 * Crea exactamente UN OrionSocket por ciclo de vida del componente que lo
 * monta (App.tsx) y lo despacha al store. El hook devuelve la función
 * ``send`` para que cualquier componente la pueda invocar.
 */

import { useEffect, useRef } from "react";

import { OrionSocket, inferBackendUrl } from "@/api/ws";
import { useOrionStore } from "@/stores/orion";
import type { ServerEvent } from "@/types";

export function useOrionSocket(): (type: string, payload?: Record<string, unknown>) => void {
  const socketRef = useRef<OrionSocket | null>(null);

  useEffect(() => {
    const { ws: wsUrl } = inferBackendUrl();
    const dispatch = useOrionStore.getState().applyEvent;
    const setConn = useOrionStore.getState().setConnected;

    const sock = new OrionSocket(
      wsUrl,
      (evt: ServerEvent) => dispatch(evt),
      (connected: boolean) => setConn(connected),
    );
    socketRef.current = sock;
    sock.start();
    return () => sock.stop();
  }, []);

  return (type: string, payload: Record<string, unknown> = {}) => {
    socketRef.current?.send(type, payload);
  };
}
