/**
 * Toaster — overlay global de mensajes in-app.
 *
 * Lee `useToastStore` y dibuja una pila bottom-right de toasts con
 * animación de entrada/salida. Cada toast respeta su `tone` (color,
 * icono) y soporta el modo "confirm" con dos botones (reemplazo del
 * `confirm()` nativo del browser).
 *
 * Montado una sola vez en App.tsx; el resto del código llama
 * `toast.success/info/warn/error/confirm()` desde stores/toast.ts.
 */

import { useToastStore, type ToastItem } from "@/stores/toast";
import { Icon, type IconName } from "@/ui/Icon";

const TONE_STYLE: Record<ToastItem["tone"], { icon: IconName; bar: string }> = {
  success: { icon: "check", bar: "bg-ok" },
  info: { icon: "bolt", bar: "bg-pri" },
  warn: { icon: "alert", bar: "bg-warn" },
  error: { icon: "alert", bar: "bg-danger" },
};

export function Toaster() {
  const items = useToastStore((s) => s.items);
  const dismiss = useToastStore((s) => s.dismiss);

  if (items.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[10000] flex flex-col gap-2.5 max-w-[380px] w-[calc(100vw-32px)] sm:w-auto pointer-events-none"
      aria-live="polite"
    >
      {items.map((t) => {
        const s = TONE_STYLE[t.tone];
        return (
          <div
            key={t.id}
            role="status"
            className={[
              "pointer-events-auto relative overflow-hidden rounded-lg",
              "border border-white/[0.08] bg-elevated/95 backdrop-blur-xl",
              "shadow-[0_10px_40px_-12px_rgb(0_0_0/0.55)]",
              "animate-fade-in-up",
            ].join(" ")}
          >
            {/* Tone bar — barra de color a la izquierda */}
            <span className={`absolute left-0 top-0 bottom-0 w-[3px] ${s.bar}`} />

            <div className="pl-4 pr-3 py-3 flex items-start gap-3">
              <Icon
                name={s.icon}
                size={16}
                className={[
                  "mt-0.5 shrink-0",
                  t.tone === "success"
                    ? "text-ok"
                    : t.tone === "info"
                      ? "text-pri"
                      : t.tone === "warn"
                        ? "text-warn"
                        : "text-danger",
                ].join(" ")}
              />

              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-text leading-snug">{t.title}</div>
                {t.detail && (
                  <div className="mt-1 text-xs text-text-dim leading-relaxed">{t.detail}</div>
                )}

                {t.confirm && (
                  <div className="mt-3 flex items-center gap-2 justify-end">
                    <button
                      onClick={() => t.confirm?.onCancel?.()}
                      className="h-7 px-3 rounded-md text-xs text-text-dim
                                 hover:text-text hover:bg-white/[0.06] transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={() => t.confirm?.onConfirm()}
                      className={[
                        "h-7 px-3 rounded-md text-xs font-medium transition-colors",
                        t.confirm.danger
                          ? "bg-danger/15 text-danger border border-danger/40 hover:bg-danger/25"
                          : "bg-pri text-bg hover:brightness-110",
                      ].join(" ")}
                    >
                      {t.confirm.label}
                    </button>
                  </div>
                )}
              </div>

              {!t.confirm && (
                <button
                  onClick={() => dismiss(t.id)}
                  className="h-6 w-6 grid place-items-center rounded
                             text-text-dim hover:text-text hover:bg-white/[0.06]
                             transition-colors shrink-0"
                  aria-label="Cerrar"
                >
                  <Icon name="close" size={12} />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
