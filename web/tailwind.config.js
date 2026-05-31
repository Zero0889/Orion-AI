/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Tokens default (tema "red"). En Fase 3 se cargarán desde
        // /api/settings/theme para reflejar el tema activo del usuario.
        bg:        "#0a0205",
        panel:     "#140307",
        panel2:    "#1a040a",
        border:    "#3d0d18",
        "border-b":"#7a1a2c",
        pri:       "#ff2a4d",
        "pri-dim": "#a01828",
        acc:       "#ff6b1a",
        text:      "#ffc4cc",
        "text-dim":"#8a3a48",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      keyframes: {
        "orb-pulse": {
          "0%,100%": { transform: "scale(1)",   opacity: "0.9" },
          "50%":     { transform: "scale(1.05)",opacity: "1" },
        },
      },
      animation: {
        "orb-pulse": "orb-pulse 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
