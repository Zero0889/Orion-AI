/**
 * ErrorBoundary — captura crashes de cualquier subtree y muestra un
 * estado de error en vez de la pantalla blanca.
 *
 * Cubre dos casos típicos:
 *   1. Un panel lazy() falla al descargar (network flaky, deploy entre
 *      sesiones que invalida los hashes). React relanza una promesa
 *      rechazada — sin boundary, queda el Suspense fallback eterno.
 *   2. Un componente lanza durante render (NPE en datos del store,
 *      props inválidas tras un cambio de schema, etc).
 *
 * Sólo error boundaries CLASE pueden capturar errores de hijos —
 * función + hooks no tiene API equivalente (React 18.3). Por eso esta
 * es de las pocas clases del proyecto.
 */

import { Component, type ReactNode } from "react";

interface Props {
  /** Función opcional para reportar a un sink externo (Sentry, etc). */
  onError?: (err: unknown) => void;
  children: ReactNode;
}

interface State {
  err: unknown | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { err: null };

  static getDerivedStateFromError(err: unknown): State {
    return { err };
  }

  componentDidCatch(err: unknown) {
    // No usamos console.* porque vite drop:["console"] lo elimina en
    // producción. Si el caller pasó un onError lo invocamos.
    this.props.onError?.(err);
  }

  reset = () => this.setState({ err: null });

  render() {
    if (!this.state.err) return this.props.children;

    const msg = this.state.err instanceof Error ? this.state.err.message : String(this.state.err);

    return (
      <div className="h-full grid place-items-center animate-fade-in px-6">
        <div className="max-w-md w-full rounded-2xl border border-danger/25 bg-danger/[0.04] backdrop-blur-md p-6 text-center">
          <div className="mx-auto mb-3 grid place-items-center h-10 w-10 rounded-full bg-danger/15 border border-danger/30 text-danger">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
          <div className="text-[10px] uppercase tracking-[0.28em] text-danger/85 font-semibold mb-1">
            Error en la vista
          </div>
          <h3 className="text-sm font-medium text-text mb-2">
            Algo salió mal al renderizar esta sección.
          </h3>
          <p className="text-xs text-text-dim leading-relaxed mb-5 break-words">
            {msg.slice(0, 240)}
          </p>
          <div className="flex items-center justify-center gap-2">
            <button
              onClick={this.reset}
              className="h-8 px-3 rounded-md bg-pri text-bg text-xs font-medium
                         shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_2px_8px_-2px_rgb(var(--orion-pri-glow)/0.55)]
                         hover:brightness-110 transition-all"
            >
              Reintentar
            </button>
            <button
              onClick={() => window.location.reload()}
              className="h-8 px-3 rounded-md border border-white/[0.08] bg-elevated text-text-dim text-xs
                         hover:text-text hover:border-white/[0.14] transition-all"
            >
              Recargar Orion
            </button>
          </div>
        </div>
      </div>
    );
  }
}
