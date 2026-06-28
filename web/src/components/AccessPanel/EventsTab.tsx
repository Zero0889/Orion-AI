/**
 * EventsTab — registros crudos del ESP32, más recientes primero.
 *
 * Esta tabla NO se exporta a XLSX (solo es para inspección/auditoría).
 * Cada row es un evento individual; el agrupamiento por usuario/día
 * está en la otra tab.
 */

import { Badge } from "@/ui/primitives";

import type { AccessEvent } from "@/api/rest";

import { AccessEmpty, eventTypeColor, formatTimestamp } from "./index";

interface Props {
  events: AccessEvent[];
  totalEvents: number;
}

export function EventsTab({ events, totalEvents }: Props) {
  if (events.length === 0) {
    return (
      <AccessEmpty
        icon="history"
        title="Sin eventos"
        hint="El ESP32 todavía no mandó ningún registro. Verificá que el sketch tenga la URL correcta de Orion."
      />
    );
  }

  return (
    <div className="px-4 sm:px-6 py-4">
      <div className="flex items-center gap-2 mb-3 text-[10px] uppercase tracking-[0.22em] text-text-dim font-mono">
        <span>{events.length} mostrados</span>
        <span className="text-muted">·</span>
        <span>{totalEvents} totales</span>
      </div>

      <div className="surface-2 rounded-lg overflow-hidden">
        <table className="w-full text-xs sm:text-sm">
          <thead>
            <tr className="bg-sunken/60 text-[10px] uppercase tracking-[0.18em] text-text-dim">
              <th className="px-3 py-2 text-left font-medium">Cuando</th>
              <th className="px-3 py-2 text-left font-medium hidden sm:table-cell">Persona</th>
              <th className="px-3 py-2 text-left font-medium">Tipo</th>
              <th className="px-3 py-2 text-right font-medium hidden md:table-cell">Conf</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr
                key={e.id}
                className="border-t border-white/[0.04] hover:bg-white/[0.02] transition-colors"
              >
                <td className="px-3 py-2 font-mono text-text tabular-nums whitespace-nowrap">
                  {formatTimestamp(e.timestamp)}
                </td>
                <td className="px-3 py-2 hidden sm:table-cell">
                  {e.user_name ? (
                    <span className="text-text">{e.user_name}</span>
                  ) : (
                    <span className="text-muted italic">
                      Huella #{e.fingerprint_id >= 0 ? e.fingerprint_id : "?"}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <Badge tone={eventTypeColor(e.event_type)} dot>
                    {e.event_type}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-right font-mono text-text-dim tabular-nums hidden md:table-cell">
                  {e.confidence || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
