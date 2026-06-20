import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite escucha en :5173. El backend FastAPI ya autoriza CORS para
// http://localhost:5173 (ver server/app.py).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // "hidden": Vite emite los .map a disco para error tracking
    // server-side (Sentry, etc) pero NO inyecta el comentario
    // `//# sourceMappingURL=` en el .js — el cliente no descarga
    // sources y stack traces en consola quedan mineralizadas, pero
    // un upload del map a Sentry sigue resolviendo símbolos.
    sourcemap: "hidden",
    rollupOptions: {
      output: {
        // Split vendor chunks por estabilidad de cache: react cambia
        // poco, katex casi nunca, zustand muy poco — separarlos hace
        // que cuando cambia código de Orion sólo se invalide el chunk
        // de la app, no las libs. También resuelve el warning de Vite
        // sobre chunks > 500 kB.
        manualChunks: {
          "vendor-react":   ["react", "react-dom"],
          "vendor-katex":   ["katex"],
          "vendor-zustand": ["zustand"],
        },
      },
    },
  },
  // Optimizaciones del esbuild en producción:
  //   · drop console/debugger — saca prints de debug del bundle final.
  //     En dev (vite dev) NO se aplica, así que los logs siguen vivos
  //     cuando los necesitamos al iterar.
  //   · legalComments: none — quita banners de licencia inline (cada lib
  //     trae los suyos). El proyecto sigue cumpliendo: los archivos
  //     LICENSE viven en node_modules; el bundle no los necesita.
  esbuild: {
    drop: ["console", "debugger"],
    legalComments: "none",
  },
});
