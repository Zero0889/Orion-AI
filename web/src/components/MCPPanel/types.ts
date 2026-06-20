/**
 * Types compartidos entre los componentes del MCPPanel.
 */

import type { MCPServerBody } from "@/api/rest";

export type Tab = "installed" | "curated" | "explore";

/** Datos para pre-rellenar el modal cuando el usuario hace "Instalar"
 *  desde la pestaña Explorar. */
export interface PrefillFromRegistry {
  suggestedId: string;
  body: MCPServerBody;
  envRequired: { name: string; description: string; required: boolean }[];
}
