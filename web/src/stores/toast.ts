/**
 * Toast store — mensajes in-app efímeros (success / info / warn / error).
 *
 * Reemplaza alert/confirm/console.error sueltos en la UI. Auto-expira
 * por default a los 4s; el caller puede pasar `duration: 0` para
 * persistente (cierra manual).
 *
 * También soporta toasts con acción confirmatoria: `confirm(...)` muestra
 * un toast con dos botones (confirmar/cancelar) y devuelve una promesa
 * que resuelve con el booleano elegido. Pensado para reemplazar el
 * `confirm()` nativo del browser, que rompe el layout con un modal feo
 * arriba de la pantalla.
 */

import { create } from "zustand";

export type ToastTone = "success" | "info" | "warn" | "error";

export interface ToastItem {
  id: string;
  tone: ToastTone;
  title: string;
  detail?: string;
  duration: number; // ms — 0 = persistente
  // Si está seteado, el toast pinta dos botones y al elegir cualquiera
  // resuelve la promesa correspondiente.
  confirm?: {
    label: string;
    onConfirm: () => void;
    onCancel?: () => void;
    danger?: boolean;
  };
}

interface ToastState {
  items: ToastItem[];
  push: (t: Omit<ToastItem, "id" | "duration"> & { duration?: number }) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

let nextId = 1;

export const useToastStore = create<ToastState>((set, get) => ({
  items: [],
  push(t) {
    const id = `t${nextId++}`;
    const item: ToastItem = { id, duration: 4000, ...t };
    set((s) => ({ items: [...s.items, item] }));
    if (item.duration > 0) {
      window.setTimeout(() => get().dismiss(id), item.duration);
    }
    return id;
  },
  dismiss(id) {
    set((s) => ({ items: s.items.filter((x) => x.id !== id) }));
  },
  clear() {
    set({ items: [] });
  },
}));

/* ── Helpers ergonómicos ──────────────────────────────────────────── */

export const toast = {
  success: (title: string, detail?: string) =>
    useToastStore.getState().push({ tone: "success", title, detail }),
  info: (title: string, detail?: string) =>
    useToastStore.getState().push({ tone: "info", title, detail }),
  warn: (title: string, detail?: string) =>
    useToastStore.getState().push({ tone: "warn", title, detail }),
  error: (title: string, detail?: string) =>
    useToastStore.getState().push({ tone: "error", title, detail }),

  /** Reemplaza al `confirm()` nativo. Devuelve una promesa con la
   *  decisión del usuario. El toast permanece hasta que elija. */
  confirm(opts: {
    title: string;
    detail?: string;
    confirmLabel?: string;
    danger?: boolean;
  }): Promise<boolean> {
    return new Promise((resolve) => {
      const { push, dismiss } = useToastStore.getState();
      const id = push({
        tone: opts.danger ? "warn" : "info",
        title: opts.title,
        detail: opts.detail,
        duration: 0,
        confirm: {
          label: opts.confirmLabel ?? "Confirmar",
          danger: opts.danger,
          onConfirm: () => {
            dismiss(id);
            resolve(true);
          },
          onCancel: () => {
            dismiss(id);
            resolve(false);
          },
        },
      });
    });
  },
};
