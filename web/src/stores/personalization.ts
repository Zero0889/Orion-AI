/**
 * Store de personalización del usuario — sobrevive a recargas via
 * localStorage (no es server-state, solo preferencias del cliente).
 *
 * Mantiene:
 *  - `wallpaper`         · dataURL de la imagen subida (o null = sin fondo
 *    personalizado, cae al NeuralBackground por defecto).
 *  - `wallpaperBlur`     · blur en píxeles aplicado al wallpaper (0–40).
 *  - `wallpaperOverlay`  · opacidad de la capa oscura sobre el wallpaper
 *    para legibilidad (0–90, en %).
 *  - `eyeColorPri/Acc`   · override de `--orion-pri` y `--orion-acc`
 *    (triplete "R G B" o null = usar los del tema activo).
 *
 * El consumo lo hacen `<WallpaperLayer />` (background) y un useEffect en
 * `App.tsx` (que escribe las CSS vars en `<html>` cuando hay override).
 */

import { create } from "zustand";

const KEY = "orion.personalization";

interface PersonalizationState {
  wallpaper: string | null;
  wallpaperBlur: number;
  wallpaperOverlay: number;
  /** Cuando true, al subir un wallpaper extraemos su color dominante y
   *  lo aplicamos automáticamente como eye-color override. Cuando false
   *  el usuario controla el color manual desde la grilla de swatches. */
  autoColorFromWallpaper: boolean;
  eyeColorPri: string | null;
  eyeColorAcc: string | null;
}

interface PersonalizationActions {
  setWallpaper: (dataUrl: string | null) => void;
  setWallpaperBlur: (n: number) => void;
  setWallpaperOverlay: (n: number) => void;
  setAutoColorFromWallpaper: (v: boolean) => void;
  setEyeColor: (pri: string | null, acc: string | null) => void;
  clearWallpaper: () => void;
  clearEyeColor: () => void;
}

const DEFAULTS: PersonalizationState = {
  wallpaper: null,
  wallpaperBlur: 16,
  wallpaperOverlay: 60,
  autoColorFromWallpaper: true,
  eyeColorPri: null,
  eyeColorAcc: null,
};

function load(): PersonalizationState {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<PersonalizationState>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

function persist(state: PersonalizationState): { ok: true } | { ok: false; reason: string } {
  if (typeof window === "undefined") return { ok: true };
  try {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({
        wallpaper: state.wallpaper,
        wallpaperBlur: state.wallpaperBlur,
        wallpaperOverlay: state.wallpaperOverlay,
        autoColorFromWallpaper: state.autoColorFromWallpaper,
        eyeColorPri: state.eyeColorPri,
        eyeColorAcc: state.eyeColorAcc,
      }),
    );
    return { ok: true };
  } catch (e) {
    // Lo común acá es QuotaExceededError: dataURLs grandes (>4 MB) no
    // caben en localStorage. El llamador decide cómo manejarlo (toast).
    return { ok: false, reason: String(e) };
  }
}

export const usePersonalization = create<PersonalizationState & PersonalizationActions>(
  (set, get) => ({
    ...load(),

    setWallpaper: (dataUrl) => {
      set({ wallpaper: dataUrl });
      const result = persist(get());
      if (!result.ok && dataUrl) {
        // Si no entró en localStorage, revertimos para no quedar en
        // estado inconsistente entre tabs.
        set({ wallpaper: null });
        throw new Error(result.reason);
      }
    },

    setWallpaperBlur: (n) => {
      set({ wallpaperBlur: Math.max(0, Math.min(40, n)) });
      persist(get());
    },

    setWallpaperOverlay: (n) => {
      set({ wallpaperOverlay: Math.max(0, Math.min(90, n)) });
      persist(get());
    },

    setAutoColorFromWallpaper: (v) => {
      set({ autoColorFromWallpaper: v });
      persist(get());
    },

    setEyeColor: (pri, acc) => {
      set({ eyeColorPri: pri, eyeColorAcc: acc });
      persist(get());
    },

    clearWallpaper: () => {
      set({ wallpaper: null });
      persist(get());
    },

    clearEyeColor: () => {
      set({ eyeColorPri: null, eyeColorAcc: null });
      persist(get());
    },
  }),
);
