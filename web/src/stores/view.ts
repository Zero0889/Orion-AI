/**
 * Store de navegación: qué vista está activa en la columna principal.
 *
 * Mantengo el shape simple a propósito — para Orion no necesitamos un
 * router con URL profunda; basta con un estado de pestaña activa.
 */

import { create } from "zustand";

export type View =
  | "home"
  | "chat"
  | "notes"
  | "memory"
  | "history"
  | "telemetry"
  | "agents"
  | "iot"
  | "mcp"
  | "skills"
  | "notifications"
  | "circuit"
  | "settings";

interface ViewState {
  view: View;
  setView: (v: View) => void;
}

export const useViewStore = create<ViewState>((set) => ({
  view: "home",
  setView: (view) => set({ view }),
}));
