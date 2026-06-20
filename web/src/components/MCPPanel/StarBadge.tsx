/**
 * StarBadge — badge con el count de estrellas de GitHub.
 *
 * Usado tanto por `RegistryRow` (pestaña Explorar) como por `RecipeCard`
 * (pestaña Curados). Lo extraemos a su propio archivo para que ambos
 * tabs puedan importarlo sin acoplarse uno al otro.
 */

export function StarBadge({ stars }: { stars: number }) {
  const display = stars >= 1000 ? `${(stars / 1000).toFixed(1)}k` : String(stars);
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full
                     text-[10px] border border-white/[0.06] bg-elevated/50 text-text-dim"
      title={`${stars} estrellas en GitHub`}
    >
      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" className="text-warn">
        <path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
      </svg>
      {display}
    </span>
  );
}
