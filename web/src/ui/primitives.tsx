/**
 * UI primitives — a tiny system of building blocks used across panels.
 *
 * Everything composes plain Tailwind classes (with our token vars) so we
 * don't pay for a runtime dep. Components are stateless and accept a
 * `className` escape hatch.
 */

import {
  forwardRef,
  useEffect,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";

import { Icon, type IconName } from "@/ui/Icon";

function cn(...c: Array<string | false | undefined | null>): string {
  return c.filter(Boolean).join(" ");
}

// ── Surface ───────────────────────────────────────────────────────────
export function Surface({
  level = 1,
  glass,
  hover,
  hud,
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & {
  level?: 1 | 2;
  glass?: boolean;
  hover?: boolean;
  /** Añade corner brackets HUD a la superficie para look más tech. */
  hud?: boolean;
}) {
  return (
    <div
      {...rest}
      className={cn(
        "relative rounded-lg",
        glass ? "surface-glass" : level === 2 ? "surface-2" : "surface-1",
        hover &&
          "transition-colors duration-200 ease-out-expo hover:bg-elevated/80 hover:border-white/10",
        hud && "overflow-hidden",
        className,
      )}
    >
      {hud && (
        <>
          <span
            aria-hidden
            className="absolute top-0 left-0 h-2 w-2 border-t border-l border-pri/50"
          />
          <span
            aria-hidden
            className="absolute top-0 right-0 h-2 w-2 border-t border-r border-pri/50"
          />
          <span
            aria-hidden
            className="absolute bottom-0 left-0 h-2 w-2 border-b border-l border-pri/30"
          />
          <span
            aria-hidden
            className="absolute bottom-0 right-0 h-2 w-2 border-b border-r border-pri/30"
          />
        </>
      )}
      {children}
    </div>
  );
}

// ── Button ────────────────────────────────────────────────────────────
type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg" | "icon";

const VARIANT: Record<Variant, string> = {
  // Primary — highlight interior superior + glow exterior + brillo en hover.
  // El shadow-[inset_…] simula "luz dentro del botón" (look visionOS).
  primary:
    "bg-pri text-bg " +
    "shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_2px_8px_-2px_rgb(var(--orion-pri-glow)/0.55),0_0_24px_-6px_rgb(var(--orion-pri-glow)/0.45)] " +
    "hover:brightness-110 hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.30),0_4px_14px_-4px_rgb(var(--orion-pri-glow)/0.70),0_0_32px_-6px_rgb(var(--orion-pri-glow)/0.55)] " +
    "active:brightness-95 " +
    "disabled:bg-elevated disabled:text-muted disabled:shadow-none",
  secondary:
    "bg-elevated text-text border border-white/[0.06] " +
    "shadow-[inset_0_1px_0_rgb(255_255_255/0.03)] " +
    "hover:bg-elevated hover:border-white/[0.14] hover:text-text " +
    "disabled:text-muted disabled:border-white/[0.04]",
  ghost:
    "bg-transparent text-text-dim hover:text-text hover:bg-white/[0.04] " +
    "disabled:text-muted disabled:hover:bg-transparent",
  danger:
    "bg-danger/10 text-danger border border-danger/30 " +
    "hover:bg-danger/15 hover:border-danger/50",
};

const SIZE: Record<Size, string> = {
  sm: "h-8  px-3 text-xs",
  md: "h-9  px-3.5 text-sm",
  lg: "h-10 px-4 text-sm",
  icon: "h-9  w-9 p-0 text-base",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: Variant;
    size?: Size;
    icon?: IconName;
    iconRight?: IconName;
    loading?: boolean;
  }
>(function Button(
  {
    variant = "secondary",
    size = "md",
    icon,
    iconRight,
    loading,
    className,
    children,
    disabled,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      {...rest}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium",
        "transition-all duration-150 ease-out-expo",
        "disabled:cursor-not-allowed",
        "active:scale-[0.98]",
        VARIANT[variant],
        SIZE[size],
        className,
      )}
    >
      {loading ? (
        <span className="h-3.5 w-3.5 rounded-full border-2 border-current border-r-transparent animate-spin-fast" />
      ) : (
        icon && <Icon name={icon} size={16} className="-ml-0.5" />
      )}
      {children && <span className="truncate">{children}</span>}
      {iconRight && !loading && <Icon name={iconRight} size={16} className="-mr-0.5 opacity-80" />}
    </button>
  );
});

// ── Badge ─────────────────────────────────────────────────────────────
// BRIEF G3: `inactive` (gris azulado) ≠ `danger` (rojo). Un estado
// deshabilitado, en cooldown o "no disponible" SIEMPRE usa inactive.
type BadgeTone = "neutral" | "info" | "success" | "warn" | "danger" | "accent" | "inactive";
const BADGE: Record<BadgeTone, string> = {
  neutral: "bg-white/[0.04]   text-text-dim border-white/[0.06]",
  info: "bg-pri/10         text-pri       border-pri/30",
  success: "bg-ok/10          text-ok        border-ok/30",
  warn: "bg-warn/10        text-warn      border-warn/30",
  danger: "bg-danger/10      text-danger    border-danger/30",
  accent: "bg-acc/10         text-acc       border-acc/30",
  inactive: "bg-sem-inactive/10 text-sem-inactive border-sem-inactive/30",
};

export function Badge({
  tone = "neutral",
  dot,
  children,
  className,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full",
        "text-[10px] uppercase tracking-[0.16em] font-medium border",
        BADGE[tone],
        className,
      )}
    >
      {dot && (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            tone === "success"
              ? "bg-ok"
              : tone === "warn"
                ? "bg-warn"
                : tone === "danger"
                  ? "bg-danger"
                  : tone === "accent"
                    ? "bg-acc"
                    : tone === "info"
                      ? "bg-pri"
                      : tone === "inactive"
                        ? "bg-sem-inactive"
                        : "bg-text-dim",
          )}
        />
      )}
      <span className="truncate">{children}</span>
    </span>
  );
}

// ── Empty state ──────────────────────────────────────────────────────
export function Empty({
  icon,
  illustration,
  title,
  hint,
  action,
  className,
}: {
  icon?: IconName;
  /** Slot opcional para SVG/ilustración. Si está presente, reemplaza
   *  al `icon` por completo. */
  illustration?: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center px-8 py-12 mx-auto max-w-sm",
        "animate-fade-in-up",
        className,
      )}
    >
      {illustration ? (
        <div className="relative mb-5">{illustration}</div>
      ) : (
        icon && (
          <div className="relative mb-5">
            <div className="absolute inset-0 -m-2 rounded-full bg-pri/10 blur-xl" />
            <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl border border-white/[0.08] bg-elevated text-text-dim">
              <Icon name={icon} size={20} />
            </div>
          </div>
        )
      )}
      <h3 className="text-sm font-medium text-text">{title}</h3>
      {hint && <p className="mt-1.5 text-xs text-text-dim leading-relaxed">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-3 w-full", className)} />;
}

// ── Section header ────────────────────────────────────────────────────
export function SectionHeader({
  eyebrow,
  title,
  hint,
  action,
}: {
  eyebrow?: string;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <header
      className="relative flex items-end justify-between px-6 py-5
                 border-b border-white/[0.06]
                 bg-gradient-to-b from-[rgb(var(--orion-pri)/0.04)] to-transparent"
    >
      {/* Accent bar inferior tech (1px) */}
      <span
        aria-hidden
        className="absolute bottom-0 left-0 h-px w-24
                   bg-gradient-to-r from-pri/70 via-pri/30 to-transparent"
      />
      {/* Scan-line top sutil */}
      <span
        aria-hidden
        className="absolute top-0 left-0 right-0 h-px
                   bg-gradient-to-r from-transparent via-pri/20 to-transparent"
      />
      <div className="min-w-0">
        {eyebrow && (
          <div className="flex items-center gap-2 mb-1.5">
            <span className="h-1 w-1 rounded-full bg-pri/80 shadow-[0_0_4px_rgb(var(--orion-pri-glow))]" />
            {/* BRIEF G5 — eyebrow = role "label" (10px, weight 500,
                tracking 0.12em) con tinte pri. Mantenemos la voz de
                marca en cada cabecera. */}
            <div className="orion-label text-pri/85" style={{ letterSpacing: "0.22em" }}>
              {eyebrow}
            </div>
          </div>
        )}
        {/* BRIEF G5 — H1 de panel: 24px, weight 600, tracking -0.01em. */}
        <h2 className="orion-h1 truncate">{title}</h2>
        {hint && <p className="orion-meta mt-1.5">{hint}</p>}
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </header>
  );
}

// ── Switch ────────────────────────────────────────────────────────────
export function Switch({
  on,
  onClick,
  size = "md",
  className,
}: {
  on: boolean;
  onClick: () => void;
  size?: "sm" | "md";
  className?: string;
}) {
  const dims =
    size === "sm"
      ? { track: "h-5 w-9", thumb: "h-4 w-4", travel: "translate-x-4" }
      : { track: "h-6 w-11", thumb: "h-5 w-5", travel: "translate-x-5" };
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onClick}
      className={cn(
        "relative rounded-full p-0.5 flex items-center shrink-0",
        "transition-colors duration-200 ease-out-expo",
        on
          ? "bg-pri/80 shadow-[0_0_14px_rgb(var(--orion-pri)/0.45)]"
          : "bg-white/[0.08] hover:bg-white/[0.12]",
        dims.track,
        className,
      )}
    >
      <span
        className={cn(
          "block rounded-full bg-white shadow-lg transition-transform duration-200 ease-out-expo",
          dims.thumb,
          on ? dims.travel : "translate-x-0",
        )}
      />
    </button>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────
export function Modal({
  open,
  onClose,
  title,
  eyebrow,
  footer,
  size = "md",
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  eyebrow?: string;
  footer?: ReactNode;
  size?: "md" | "lg";
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const w = size === "lg" ? "max-w-2xl" : "max-w-lg";

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-bg/80 backdrop-blur-md animate-fade-in p-4"
      onClick={onClose}
    >
      {/* ambient halo */}
      <div className="absolute h-[420px] w-[420px] rounded-full bg-pri/10 blur-3xl pointer-events-none animate-halo" />
      <div
        className={cn(
          "relative w-full surface-glass rounded-2xl shadow-lift animate-scale-in flex flex-col max-h-[88vh]",
          w,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-white/[0.06]">
          <div className="min-w-0">
            {eyebrow && (
              <div className="text-[10px] uppercase tracking-[0.24em] text-pri/80 mb-0.5">
                {eyebrow}
              </div>
            )}
            <h2 className="text-lg font-semibold tracking-tight text-text truncate">{title}</h2>
          </div>
          <button
            onClick={onClose}
            className="h-8 w-8 grid place-items-center rounded-md text-text-dim hover:text-text hover:bg-white/[0.05] transition-colors"
            title="Cerrar"
          >
            <Icon name="close" size={16} />
          </button>
        </header>

        <div className="px-6 py-5 overflow-y-auto scrollbar-thin flex-1">{children}</div>

        {footer && (
          <footer className="px-6 py-4 border-t border-white/[0.06] flex items-center justify-end gap-2">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}

// ── Field ─────────────────────────────────────────────────────────────
export function Field({
  label,
  hint,
  children,
  error,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-[0.18em] text-text-dim">{label}</span>
        {hint && <span className="text-[10px] text-muted">{hint}</span>}
      </div>
      {children}
      {error && (
        <p className="mt-1.5 text-xs text-danger flex items-center gap-1.5">
          <Icon name="alert" size={12} /> {error}
        </p>
      )}
    </label>
  );
}

// ── TextInput ─────────────────────────────────────────────────────────
export const TextInput = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function TextInput({ className, ...rest }, ref) {
    return (
      <input
        ref={ref}
        {...rest}
        className={cn(
          "w-full rounded-lg bg-elevated/80 border border-white/[0.08]",
          "px-3.5 h-10 text-sm placeholder-muted",
          "focus:outline-none focus:border-pri/40 focus:shadow-glow-soft",
          "transition-all duration-200 ease-out-expo",
          className,
        )}
      />
    );
  },
);

// ── KBD ───────────────────────────────────────────────────────────────
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd
      className="inline-flex h-5 min-w-5 items-center justify-center px-1.5 rounded
                    border border-white/[0.08] bg-elevated text-[10px] font-mono text-text-dim
                    shadow-rim"
    >
      {children}
    </kbd>
  );
}
