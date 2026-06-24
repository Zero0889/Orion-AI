/**
 * humanTime — formateo humano de timestamps (BRIEF G6).
 *
 * Regla del brief: NUNCA mostrar ISO (`2026-06-16T15:38:01`) al usuario.
 * Siempre formato relativo / humanizado en español:
 *
 *   < 60s    → "ahora"
 *   < 60min  → "hace 5 min"
 *   < 24h    → "hace 2 h"
 *   ayer     → "ayer 15:38"
 *   < 7 días → "lun 16 jun"
 *   este año → "16 jun"
 *   resto    → "16 jun 2024"
 *
 * Acepta `Date | number | string`:
 *  - `number`  → epoch en MILISEGUNDOS (estándar JS).
 *  - `string`  → cualquier cosa parseable por `new Date()` (ISO, RFC 2822…).
 *
 * Para timestamps en SEGUNDOS (UNIX) usar `humanizeUnix(ts)`.
 */

const SHORT_WEEKDAY = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"] as const;
const SHORT_MONTH = [
  "ene",
  "feb",
  "mar",
  "abr",
  "may",
  "jun",
  "jul",
  "ago",
  "sep",
  "oct",
  "nov",
  "dic",
] as const;

function toDate(input: Date | number | string): Date | null {
  if (input instanceof Date) return isNaN(input.getTime()) ? null : input;
  if (typeof input === "number") {
    if (!Number.isFinite(input)) return null;
    return new Date(input);
  }
  if (typeof input === "string") {
    const t = new Date(input);
    return isNaN(t.getTime()) ? null : t;
  }
  return null;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/**
 * Devuelve el timestamp humanizado completo. Cuando el evento es de hoy
 * o de ayer prioriza la franja relativa; pasado eso da fecha corta con
 * día de la semana (esta semana) o sin él (fechas más viejas).
 *
 * `now` se inyecta solo para tests / SSR — en runtime se usa `Date.now()`.
 */
export function humanizeTime(input: Date | number | string, now: Date = new Date()): string {
  const d = toDate(input);
  if (!d) return "—";

  const diffMs = now.getTime() - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  // Futuro inmediato (drift de reloj <30s) → "ahora"
  if (diffSec < 30 && diffSec > -60) return "ahora";

  // Eventos en el futuro: dar fecha/hora absoluta corta
  if (diffSec < 0) {
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }

  if (diffSec < 60) return "ahora";
  if (diffSec < 3600) {
    const m = Math.floor(diffSec / 60);
    return `hace ${m} min`;
  }

  // Calculamos antes el delta de DÍA CALENDARIO porque la regla del brief
  // privilegia "ayer 22:14" sobre "hace 16 h" cuando el evento cruzó la
  // medianoche, aunque hayan pasado <24h reloj.
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfDate = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const daysDiff = Math.round((startOfToday - startOfDate) / 86400000);

  if (daysDiff === 0) {
    const h = Math.floor(diffSec / 3600);
    return `hace ${h} h`;
  }

  if (daysDiff === 1) {
    return `ayer ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }

  if (daysDiff < 7) {
    return `${SHORT_WEEKDAY[d.getDay()]} ${d.getDate()} ${SHORT_MONTH[d.getMonth()]}`;
  }

  if (d.getFullYear() === now.getFullYear()) {
    return `${d.getDate()} ${SHORT_MONTH[d.getMonth()]}`;
  }

  return `${d.getDate()} ${SHORT_MONTH[d.getMonth()]} ${d.getFullYear()}`;
}

/**
 * Variante para timestamps UNIX en SEGUNDOS (no milisegundos).
 * Útil para feeds del backend que ya vienen así (Gmail, MCP, etc).
 */
export function humanizeUnix(ts: number, now: Date = new Date()): string {
  return humanizeTime(ts * 1000, now);
}

/**
 * Solo el "hace X" sin la rama de fecha absoluta. Útil cuando queremos
 * un indicador continuo (ej. "última sync: hace 12 s") y aceptamos que
 * eventos viejos sigan diciendo "hace X días".
 */
export function humanizeAge(input: Date | number | string, now: Date = new Date()): string {
  const d = toDate(input);
  if (!d) return "—";
  const diffSec = Math.max(0, Math.floor((now.getTime() - d.getTime()) / 1000));
  if (diffSec < 5) return "ahora";
  if (diffSec < 60) return `hace ${diffSec} s`;
  if (diffSec < 3600) return `hace ${Math.floor(diffSec / 60)} min`;
  if (diffSec < 86400) return `hace ${Math.floor(diffSec / 3600)} h`;
  return `hace ${Math.floor(diffSec / 86400)} d`;
}
