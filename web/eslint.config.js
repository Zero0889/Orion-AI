// ESLint flat config (v9+) para el frontend de O.R.I.O.N.
//
// Filosofía:
//  - Set inicial conservador (no draconiano): el repo ya tiene >13k LOC
//    de TSX y romper la build entera el día 1 no aporta.
//  - typescript-eslint en modo "recommended" (no strict-type-checked,
//    que requiere parserOptions.project y enlentece CI).
//  - react-hooks y react-refresh ON.
//  - prettier desactiva las reglas de estilo que choquen con el formatter.

import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "node_modules",
      "public",
      "vite.config.ts",
      "postcss.config.js",
      "tailwind.config.js",
    ],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // react-refresh: nicety de Vite HMR (advierte cuando un archivo
      // exporta componentes + constantes). El refactor para cumplirla
      // implica reshape de archivos (App.tsx, OrbHUD, CommandPalette).
      // OFF hoy; activar en Fase 4 cuando se rompan en feature-folders.
      "react-refresh/only-export-components": "off",

      // exhaustive-deps: hay 3 sitios (DeviceFormModal, NotificationsPanel,
      // SkillsPanel) donde se omite una dep a propósito. WARN, no error,
      // para no bloquear CI hasta que se revisen caso por caso.
      "react-hooks/exhaustive-deps": "warn",

      // Permite `any` puntual (el código actual lo usa en varios stores
      // y en payloads del bus). Bajar a "error" cuando se tipen los eventos.
      "@typescript-eslint/no-explicit-any": "warn",

      // `_var` para parámetros intencionalmente sin usar.
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
    },
  },
  prettier,
);
