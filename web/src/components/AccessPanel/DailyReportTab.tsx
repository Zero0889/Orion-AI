/**
 * DailyReportTab — la "tabla excel" que pidió el usuario.
 *
 * Estructura: ID · Nombre · Fecha · Entrada · Salida · Tiempo.
 *
 * Render:
 *   · Desktop ≥ md: tabla HTML clásica con header sticky.
 *   · Mobile: una card por row con los campos apilados (las tablas con
 *     >5 columnas no funcionan en pantallas de 400px).
 */

import type { AccessDailyRow } from "@/api/rest";

import { AccessEmpty, formatFecha } from "./index";

interface Props {
  rows: AccessDailyRow[];
}

export function DailyReportTab({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <AccessEmpty
        icon="shield"
        title="Sin registros todavía"
        hint="Cuando alguien ponga su huella en el ESP32, los ingresos del día aparecerán acá agrupados."
      />
    );
  }

  return (
    <div className="px-4 sm:px-6 py-4">
      {/* ── Mobile: cards ──────────────────────────────────────────── */}
      <div className="md:hidden flex flex-col gap-2">
        {rows.map((r, i) => (
          <div
            key={`${r.fingerprint_id}-${r.fecha}`}
            className="surface-2 rounded-lg p-3 flex flex-col gap-1.5 animate-fade-in-up"
            style={{ animationDelay: `${i * 18}ms` }}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-[0.16em] text-text-dim font-mono">
                  {String(i + 1).padStart(3, "0")} · {formatFecha(r.fecha)}
                </div>
                <div className="text-sm font-semibold text-text truncate">{r.name}</div>
              </div>
              <span
                className="shrink-0 px-2 py-1 rounded-md bg-pri/10 border border-pri/25
                           text-[11px] font-mono text-pri tabular-nums"
              >
                {r.tiempo_legible}
              </span>
            </div>
            <div className="flex items-center gap-4 text-[11px] font-mono text-text-dim tabular-nums">
              <span>
                <span className="text-ok">▲</span> {r.entrada}
              </span>
              <span>
                <span className="text-warn">▼</span> {r.salida}
              </span>
              <span className="ml-auto text-muted">{r.eventos_dia} lecturas</span>
            </div>
          </div>
        ))}
      </div>

      {/* ── Desktop: tabla HTML ────────────────────────────────────── */}
      <div className="hidden md:block surface-2 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-sunken/60 text-[10px] uppercase tracking-[0.18em] text-text-dim">
              <th className="px-3 py-2 text-left font-medium w-16">ID</th>
              <th className="px-3 py-2 text-left font-medium">Nombre</th>
              <th className="px-3 py-2 text-left font-medium w-28">Fecha</th>
              <th className="px-3 py-2 text-left font-medium w-20">Entrada</th>
              <th className="px-3 py-2 text-left font-medium w-20">Salida</th>
              <th className="px-3 py-2 text-left font-medium w-28">Tiempo</th>
              <th className="px-3 py-2 text-right font-medium w-20">Eventos</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={`${r.fingerprint_id}-${r.fecha}`}
                className="border-t border-white/[0.04] hover:bg-white/[0.02] transition-colors"
              >
                <td className="px-3 py-2 font-mono text-text-dim tabular-nums">
                  {String(i + 1).padStart(3, "0")}
                </td>
                <td className="px-3 py-2 font-medium text-text">{r.name}</td>
                <td className="px-3 py-2 font-mono text-text-dim tabular-nums">
                  {formatFecha(r.fecha)}
                </td>
                <td className="px-3 py-2 font-mono text-ok tabular-nums">{r.entrada}</td>
                <td className="px-3 py-2 font-mono text-warn tabular-nums">{r.salida}</td>
                <td className="px-3 py-2 font-mono text-pri tabular-nums">{r.tiempo_legible}</td>
                <td className="px-3 py-2 text-right font-mono text-text-dim tabular-nums">
                  {r.eventos_dia}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
