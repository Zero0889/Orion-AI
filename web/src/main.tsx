import { QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { queryClient } from "./query/client";
import "./styles.css";
// NOTA: el CSS de KaTeX se importa desde `lib/markdown.tsx`. Como
// markdown es lazy-loaded (sólo lo trae ChatPanel cuando se monta),
// Vite emite el CSS de KaTeX en un chunk aparte que sólo se carga
// cuando renderizás Markdown — no en el paint inicial.

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
