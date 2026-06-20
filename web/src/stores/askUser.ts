/**
 * askUser store — mantiene la pregunta interactiva pendiente.
 *
 * El backend emite `ask_user.start` cuando un agente (researcher,
 * writer, etc) llama a la tool `ask_user`. El handler de WS en
 * stores/orion.ts traduce el evento y llama a `setPending` acá.
 *
 * El componente <AskUserPrompt /> en ChatPanel lee este store y
 * renderiza un menú clickeable. Al elegir, envía la respuesta via
 * WS (`ask_user.response`) y limpia el pending.
 *
 * Solo soporta UNA pregunta a la vez — si llega otra mientras hay una
 * pendiente, la nueva la reemplaza (caso raro; el agente debería
 * encadenar UNA pregunta por turno).
 */

import { create } from "zustand";

export interface AskOption {
  label: string;
  description?: string;
}

export interface PendingQuestion {
  questionId: string;
  question: string;
  options: AskOption[];
  allowOther: boolean;
  /** ts en ms cuando llegó — útil para mostrar "hace X segundos" */
  receivedAt: number;
}

interface AskUserState {
  pending: PendingQuestion | null;
  setPending: (q: PendingQuestion | null) => void;
  clear: () => void;
}

export const useAskUserStore = create<AskUserState>((set) => ({
  pending: null,
  setPending: (q) => set({ pending: q }),
  clear: () => set({ pending: null }),
}));
