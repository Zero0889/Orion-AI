/** @type {import('tailwindcss').Config} */
//
// Tokens are wired through CSS variables (see styles.css). The default
// palette is a premium dark-first system; the backend `settings.theme`
// endpoint can override the same variables at runtime, so the existing
// `rev.theme` flow keeps working without changing the contract.
//
const cssVar = (name) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg:        cssVar("--orion-bg"),
        surface:   cssVar("--orion-surface"),
        elevated:  cssVar("--orion-elevated"),
        sunken:    cssVar("--orion-sunken"),
        glass:     cssVar("--orion-glass"),
        border:    cssVar("--orion-border"),
        "border-strong": cssVar("--orion-border-strong"),

        pri:       cssVar("--orion-pri"),
        "pri-dim": cssVar("--orion-pri-dim"),
        acc:       cssVar("--orion-acc"),
        "pri-glow":cssVar("--orion-pri-glow"),

        ok:        cssVar("--orion-ok"),
        warn:      cssVar("--orion-warn"),
        danger:    cssVar("--orion-danger"),

        text:      cssVar("--orion-text"),
        "text-dim":cssVar("--orion-text-dim"),
        muted:     cssVar("--orion-muted"),

        // back-compat aliases (older code still references these names)
        panel:     cssVar("--orion-surface"),
        panel2:    cssVar("--orion-elevated"),
        "border-b":cssVar("--orion-border-strong"),
      },
      fontFamily: {
        sans:    ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono:    ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
        micro: ["0.625rem",  { lineHeight: "0.875rem", letterSpacing: "0.16em" }],
      },
      borderRadius: {
        xs:  "6px",
        sm:  "8px",
        md:  "10px",
        lg:  "14px",
        xl:  "18px",
        "2xl": "22px",
        "3xl": "28px",
      },
      boxShadow: {
        glow:       "0 0 0 1px rgb(var(--orion-pri) / 0.30), 0 8px 28px -8px rgb(var(--orion-pri) / 0.35)",
        "glow-soft":"0 0 24px -4px rgb(var(--orion-pri) / 0.35)",
        rim:        "inset 0 1px 0 0 rgb(255 255 255 / 0.04), 0 1px 0 0 rgb(0 0 0 / 0.4)",
        elevate:    "0 1px 0 0 rgb(255 255 255 / 0.04), 0 10px 30px -12px rgb(0 0 0 / 0.55)",
        lift:       "0 20px 60px -20px rgb(0 0 0 / 0.7), 0 0 0 1px rgb(255 255 255 / 0.04)",
      },
      backgroundImage: {
        "grid-dots":  "radial-gradient(rgb(255 255 255 / 0.04) 1px, transparent 1px)",
        "fade-down":  "linear-gradient(to bottom, rgb(var(--orion-bg) / 0.85), rgb(var(--orion-bg) / 0))",
        "fade-up":    "linear-gradient(to top, rgb(var(--orion-bg) / 0.85), rgb(var(--orion-bg) / 0))",
        "shine":      "linear-gradient(135deg, rgb(var(--orion-pri) / 0.12) 0%, transparent 40%, rgb(var(--orion-acc) / 0.08) 100%)",
      },
      backgroundSize: {
        "dots-sm": "22px 22px",
      },
      transitionTimingFunction: {
        "out-expo":  "cubic-bezier(0.16, 1, 0.3, 1)",
        "out-soft":  "cubic-bezier(0.32, 0.72, 0, 1)",
        "in-out-soft": "cubic-bezier(0.65, 0, 0.35, 1)",
      },
      keyframes: {
        // ── ambient ───────────────────────────────────────────────
        "breath": {
          "0%,100%": { transform: "scale(1)",    opacity: "0.85" },
          "50%":     { transform: "scale(1.04)", opacity: "1" },
        },
        "drift-slow": {
          "0%,100%": { transform: "translate3d(0,0,0)" },
          "50%":     { transform: "translate3d(0,-6px,0)" },
        },
        "spin-slow":  { to: { transform: "rotate(360deg)" } },
        "spin-rev":   { to: { transform: "rotate(-360deg)" } },

        // ── orb states ────────────────────────────────────────────
        "pulse-ring": {
          "0%":   { transform: "scale(0.9)",  opacity: "0.6" },
          "70%":  { transform: "scale(1.4)",  opacity: "0" },
          "100%": { transform: "scale(1.4)",  opacity: "0" },
        },
        "pulse-ring-soft": {
          "0%":   { transform: "scale(0.95)", opacity: "0.35" },
          "100%": { transform: "scale(1.25)", opacity: "0" },
        },
        "halo": {
          "0%,100%": { opacity: "0.55", transform: "scale(1)"   },
          "50%":     { opacity: "0.9",  transform: "scale(1.06)" },
        },
        "wave": {
          "0%":   { transform: "scaleY(0.35)" },
          "50%":  { transform: "scaleY(1)" },
          "100%": { transform: "scaleY(0.5)" },
        },

        // ── microinteractions ─────────────────────────────────────
        "fade-in": {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in-down": {
          from: { opacity: "0", transform: "translateY(-6px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.96)" },
          to:   { opacity: "1", transform: "scale(1)" },
        },
        "slide-in-right": {
          from: { opacity: "0", transform: "translateX(8px)" },
          to:   { opacity: "1", transform: "translateX(0)" },
        },
        "shimmer": {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "caret": {
          "0%,100%": { opacity: "0" },
          "50%":     { opacity: "1" },
        },
      },
      animation: {
        // ambient + state
        "breath":       "breath 4.4s ease-in-out infinite",
        "drift-slow":   "drift-slow 9s ease-in-out infinite",
        "spin-slow":    "spin-slow 16s linear infinite",
        "spin-mid":     "spin-slow 8s linear infinite",
        "spin-fast":    "spin-slow 4s linear infinite",
        "spin-rev":     "spin-rev 12s linear infinite",
        "pulse-ring":   "pulse-ring 2.4s ease-out infinite",
        "pulse-soft":   "pulse-ring-soft 3.6s ease-out infinite",
        "halo":         "halo 3.2s ease-in-out infinite",
        "wave":         "wave 1.1s ease-in-out infinite",

        // microinteractions
        "fade-in":      "fade-in 220ms cubic-bezier(0.16,1,0.3,1) both",
        "fade-in-up":   "fade-in-up 260ms cubic-bezier(0.16,1,0.3,1) both",
        "fade-in-down": "fade-in-down 220ms cubic-bezier(0.16,1,0.3,1) both",
        "scale-in":     "scale-in 200ms cubic-bezier(0.16,1,0.3,1) both",
        "slide-in":     "slide-in-right 240ms cubic-bezier(0.16,1,0.3,1) both",
        "shimmer":      "shimmer 2.2s linear infinite",
        "caret":        "caret 1.1s steps(1,end) infinite",
      },
    },
  },
  plugins: [],
};
