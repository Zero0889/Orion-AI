/**
 * useZoomShortcuts — Ctrl + / Ctrl - / Ctrl 0 para escalar todo el chrome.
 *
 * El factor se aplica al `<html>` usando la propiedad `zoom` (Chromium /
 * Tauri lo soportan y escala layout completo, no sólo pintura). El valor
 * se persiste en localStorage y se rehidrata al montar.
 *
 * Cada cambio dispara un toast efímero con el % actual.
 *
 * También expone helpers `zoomIn / zoomOut / zoomReset` para que el
 * CommandPalette pueda invocarlos desde acciones buscables.
 */

import { useEffect } from "react";

import { toast } from "@/stores/toast";

const KEY = "orion.zoom";
const STEP = 0.1;
const MIN = 0.7;
const MAX = 1.6;
const DEFAULT = 1.0;

function clamp(v: number): number {
  return Math.min(MAX, Math.max(MIN, Math.round(v * 10) / 10));
}

function apply(z: number): void {
  // Aplicamos zoom sobre #root (no sobre <html>) y compensamos su tamaño
  // dividiendo 100vw/100vh por el factor — así el layout reflowea para
  // ocupar exactamente la ventana visible a cualquier nivel de zoom, sin
  // clipping ni scrollbars indeseados. El componente raíz de App.tsx
  // usa h-full/w-full para heredar este box.
  const root = document.getElementById("root") as HTMLElement | null;
  if (root) root.style.zoom = String(z);
  document.documentElement.style.setProperty("--orion-zoom", String(z));
  window.localStorage.setItem(KEY, String(z));
}

function read(): number {
  const raw = window.localStorage.getItem(KEY);
  const n = raw ? Number(raw) : DEFAULT;
  return Number.isFinite(n) ? clamp(n) : DEFAULT;
}

function announce(z: number, label: string): void {
  toast.info(label, `Zoom: ${Math.round(z * 100)}%`);
}

export function zoomIn(): void {
  const z = clamp(read() + STEP);
  apply(z);
  announce(z, "Acercar");
}
export function zoomOut(): void {
  const z = clamp(read() - STEP);
  apply(z);
  announce(z, "Alejar");
}
export function zoomReset(): void {
  apply(DEFAULT);
  announce(DEFAULT, "Zoom reiniciado");
}

export function useZoomShortcuts(): void {
  useEffect(() => {
    apply(read());

    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      // `=` y `+` viven en la misma tecla; en algunos layouts `+` requiere shift.
      if (e.key === "=" || e.key === "+") {
        e.preventDefault();
        zoomIn();
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        zoomOut();
      } else if (e.key === "0") {
        e.preventDefault();
        zoomReset();
      }
    };

    // wheel + ctrl también es zoom en browsers — lo respetamos como nuestro.
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      if (e.deltaY < 0) zoomIn();
      else if (e.deltaY > 0) zoomOut();
    };

    window.addEventListener("keydown", onKey);
    window.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("wheel", onWheel);
    };
  }, []);
}
