/**
 * Store de navegación: qué vista está activa en la columna principal.
 *
 * Mantengo el shape simple a propósito — para Orion no necesitamos un
 * router con URL profunda; basta con un estado de pestaña activa.
 */

import { create } from "zustand";

export type View = "chat" | "notes" | "memory" | "history" | "settings";

interface ViewState {
  view: View;
  setView: (v: View) => void;
}

export const useViewStore = create<ViewState>((set) => ({
  view: "chat",
  setView: (view) => set({ view }),
}));
