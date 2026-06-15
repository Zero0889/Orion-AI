/**
 * MemoryPanel — long-term memory across categories.
 *
 * Premium tabbed surface, inline editing, fresh card design.
 *
 * Mejoras:
 *   - Search global que filtra TODAS las categorías (no solo la activa).
 *   - Sugerencias por categoría: claves típicas en chips clickeables que
 *     pre-rellenan el composer para que el usuario configure a Orion de
 *     un solo click en vez de escribir clave/valor a mano.
 *   - Composer reformulado: campo "valor" expandido cuando hay clave
 *     elegida, atajos teclado, validación visual.
 *   - Toasts in-app reemplazando alerts/confirms.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { api, type MemoryShape, type MemoryCategory } from "@/api/rest";
import { useOrionStore } from "@/stores/orion";
import { toast } from "@/stores/toast";
import { Icon, type IconName } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

const CATEGORIES: { id: MemoryCategory; label: string; description: string; icon: IconName }[] = [
  { id: "identity",      label: "Identidad",    description: "Nombre, ciudad, trabajo, lo esencial",     icon: "shield"   },
  { id: "preferences",   label: "Preferencias", description: "Gustos, hobbies, ritmos diarios",          icon: "sparkles" },
  { id: "projects",      label: "Proyectos",    description: "Cosas en las que estás trabajando ahora",  icon: "cpu"      },
  { id: "relationships", label: "Relaciones",   description: "Familia, amistades, compañeros",           icon: "chat"     },
  { id: "wishes",        label: "Deseos",       description: "Planes, ambiciones, qué viene después",    icon: "bolt"     },
  { id: "notes",         label: "Notas",        description: "Hábitos, ideas, cualquier otra cosa",      icon: "notes"    },
];

// Claves típicas por categoría — chips clickeables que rellenan el
// composer para que el usuario configure a Orion sin escribir snake_case
// de memoria.
const SUGGESTED_KEYS: Record<MemoryCategory, { key: string; label: string; example: string }[]> = {
  identity: [
    { key: "nombre",       label: "Nombre",       example: "Zahir" },
    { key: "edad",         label: "Edad",         example: "32"    },
    { key: "ciudad",       label: "Ciudad",       example: "Lima"  },
    { key: "trabajo",      label: "Trabajo",      example: "Ingeniero de software" },
    { key: "idioma",       label: "Idioma",       example: "Español" },
    { key: "cumpleanos",   label: "Cumpleaños",   example: "1992-03-14" },
  ],
  preferences: [
    { key: "comida_favorita", label: "Comida favorita", example: "Pizza" },
    { key: "musica",          label: "Música",          example: "Synthwave, jazz" },
    { key: "deporte",         label: "Deporte",         example: "Tenis" },
    { key: "color_favorito",  label: "Color favorito",  example: "Azul" },
    { key: "horario_trabajo", label: "Horario trabajo", example: "9 a 18" },
  ],
  projects: [
    { key: "principal", label: "Principal", example: "O.R.I.O.N — sistema operativo asistido" },
    { key: "side",      label: "Side",      example: "Blog técnico" },
  ],
  relationships: [
    { key: "pareja",     label: "Pareja",     example: "" },
    { key: "mejor_amigo", label: "Mejor amigo", example: "" },
    { key: "mascota",    label: "Mascota",    example: "" },
  ],
  wishes: [
    { key: "viaje", label: "Viaje pendiente", example: "Japón" },
    { key: "meta_anio", label: "Meta del año", example: "Publicar Orion en GitHub" },
  ],
  notes: [
    { key: "habito", label: "Hábito", example: "Meditar 10 min al levantarme" },
  ],
};

const EMPTY_MEM: MemoryShape = {
  identity: {}, preferences: {}, projects: {},
  relationships: {}, wishes: {}, notes: {},
};

export function MemoryPanel() {
  const rev = useOrionStore((s) => s.rev.memory);
  const [mem,   setMem]   = useState<MemoryShape>(EMPTY_MEM);
  const [tab,   setTab]   = useState<MemoryCategory>("identity");
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");
  const [query, setQuery]   = useState("");
  const valRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let alive = true;
    api.getMemory()
      .then((m) => { if (alive) setMem(m); })
      .catch((e) => { if (alive) toast.error("No pude leer memoria", String(e)); });
    return () => { alive = false; };
  }, [rev]);

  const entries = useMemo(
    () => Object.entries(mem[tab] ?? {}).map(([key, entry]) => ({ key, ...entry })),
    [mem, tab],
  );

  // Búsqueda global cuando el usuario escribió algo en el buscador.
  // Devuelve hits planos { category, key, value, updated } a través de
  // TODAS las categorías. Cuando query está vacío, devuelve null y
  // mostramos la vista clásica de la pestaña activa.
  const globalHits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    const out: { cat: MemoryCategory; key: string; value: string; updated?: string }[] = [];
    for (const cat of CATEGORIES) {
      for (const [k, e] of Object.entries(mem[cat.id] ?? {})) {
        const value = String((e as { value?: unknown }).value ?? "");
        if (k.toLowerCase().includes(q) || value.toLowerCase().includes(q)) {
          out.push({ cat: cat.id, key: k, value, updated: (e as { updated?: string }).updated });
        }
      }
    }
    return out;
  }, [mem, query]);

  // Las claves sugeridas no usadas aún en la categoría activa — son las
  // que mostramos como chips para "armar" la memoria rápido.
  const unusedSuggestions = useMemo(() => {
    const used = new Set(Object.keys(mem[tab] ?? {}));
    return SUGGESTED_KEYS[tab].filter((s) => !used.has(s.key));
  }, [mem, tab]);

  /* ── Acciones ───────────────────────────────────────────────── */
  async function save(category: MemoryCategory, key: string, value: string) {
    const v = value.trim();
    if (!v) return;
    try { await api.putMemory(category, key, v); }
    catch (e) { toast.error("No se pudo guardar", String(e)); }
  }
  async function addNew() {
    const k = newKey.trim().replace(/\s+/g, "_").toLowerCase();
    const v = newVal.trim();
    if (!k || !v) return;
    try {
      await api.putMemory(tab, k, v);
      setNewKey(""); setNewVal("");
      toast.success("Memoria guardada", `${tab} / ${k}`);
    } catch (e) { toast.error("No se pudo guardar", String(e)); }
  }
  async function remove(category: MemoryCategory, key: string) {
    const ok = await toast.confirm({
      title:        "¿Borrar entrada?",
      detail:       `${category} / ${key}`,
      confirmLabel: "Borrar",
      danger:       true,
    });
    if (!ok) return;
    try {
      await api.deleteMemory(category, key);
      toast.success("Entrada borrada");
    } catch (e) { toast.error("No se pudo borrar", String(e)); }
  }
  function fillFromSuggestion(key: string, example: string) {
    setNewKey(key);
    setNewVal(example);
    setTimeout(() => valRef.current?.select(), 30);
  }

  const active = CATEGORIES.find((c) => c.id === tab)!;
  const totalEntries = Object.values(mem).reduce((acc, c) => acc + Object.keys(c).length, 0);

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        eyebrow="Conocimiento"
        title="Memoria"
        hint="Lo que Orion sabe sobre ti, organizado por categoría."
        action={<Badge tone="neutral">{totalEntries} entradas</Badge>}
      />

      {/* ── Search bar — busca en TODAS las categorías ───────────── */}
      <div className="px-6 pt-4">
        <div className="relative">
          <Icon name="search" size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-text-dim pointer-events-none" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar en toda la memoria…"
            className="w-full h-9 pl-9 pr-9 rounded-md bg-elevated/60 border border-white/[0.08]
                       text-sm placeholder-muted focus:outline-none focus:border-pri/40
                       transition-colors"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6 grid place-items-center
                         rounded text-text-dim hover:text-text hover:bg-white/[0.05]"
              title="Limpiar"
            >
              <Icon name="close" size={11} />
            </button>
          )}
        </div>
      </div>

      {/* ── Tabs (ocultos durante búsqueda global) ───────────────── */}
      {!globalHits && (
        <>
          <nav className="px-6 py-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
            {CATEGORIES.map((c) => {
              const n = Object.keys(mem[c.id] ?? {}).length;
              const isActive = tab === c.id;
              return (
                <button
                  key={c.id}
                  onClick={() => setTab(c.id)}
                  className={[
                    "group relative rounded-lg px-3 py-2.5 text-left border transition-all duration-200 ease-out-expo",
                    isActive
                      ? "bg-pri/10 border-pri/35 text-text shadow-glow-soft"
                      : "bg-elevated/40 border-white/[0.05] text-text-dim hover:text-text hover:border-white/[0.12]",
                  ].join(" ")}
                >
                  <div className="flex items-center justify-between mb-1">
                    <Icon name={c.icon} size={14} className={isActive ? "text-pri" : "text-text-dim"} />
                    <span className={`text-[10px] font-mono tabular-nums ${isActive ? "text-pri" : "text-muted"}`}>{n}</span>
                  </div>
                  <div className="text-xs font-medium tracking-tight">{c.label}</div>
                </button>
              );
            })}
          </nav>

          <p className="px-6 text-xs italic text-text-dim flex items-center gap-2">
            <Icon name={active.icon} size={13} className="text-pri/70" /> {active.description}
          </p>
        </>
      )}

      {/* ── Body: hits globales o entries de la pestaña ──────────── */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        {globalHits ? (
          <GlobalResults hits={globalHits} onSave={save} onDelete={remove} />
        ) : entries.length === 0 ? (
          <div className="flex flex-col gap-4">
            <Empty
              icon={active.icon}
              title="Sin entradas en esta categoría"
              hint="Pulsa una sugerencia abajo o pídeselo a Orion durante la charla."
            />
            {unusedSuggestions.length > 0 && (
              <SuggestionChips
                items={unusedSuggestions}
                onPick={fillFromSuggestion}
              />
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-2">
              {entries.map((e, i) => (
                <Row
                  key={e.key} entryKey={e.key} value={String(e.value ?? "")}
                  updated={e.updated} delay={i * 25}
                  onSave={(v) => save(tab, e.key, v)} onDelete={() => remove(tab, e.key)}
                />
              ))}
            </div>
            {unusedSuggestions.length > 0 && (
              <div className="mt-2">
                <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim mb-2 font-mono">
                  Añadir rápido
                </div>
                <SuggestionChips items={unusedSuggestions} onPick={fillFromSuggestion} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Composer — se ilumina cuando hay clave seleccionada ───── */}
      <div className="px-6 py-3 border-t border-white/[0.06] bg-bg/70">
        <div className="flex gap-2">
          <input
            type="text"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="clave (snake_case)"
            className="w-44 rounded-md bg-elevated border border-white/[0.08]
                       px-3 h-9 text-sm placeholder-muted font-mono
                       focus:outline-none focus:border-pri/40 transition-colors"
          />
          <input
            ref={valRef}
            type="text"
            value={newVal}
            onChange={(e) => setNewVal(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addNew(); }}
            placeholder={`valor (categoría: ${active.label.toLowerCase()})`}
            className={[
              "flex-1 rounded-md border px-3 h-9 text-sm placeholder-muted",
              "focus:outline-none focus:border-pri/40 transition-colors",
              newKey.trim() ? "bg-pri/5 border-pri/30" : "bg-elevated border-white/[0.08]",
            ].join(" ")}
          />
          <Button
            variant="primary" size="md" icon="plus"
            onClick={addNew}
            disabled={!newKey.trim() || !newVal.trim()}
          >
            Guardar
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ─── Chips de sugerencia ──────────────────────────────────────────── */
function SuggestionChips({
  items, onPick,
}: {
  items: { key: string; label: string; example: string }[];
  onPick: (key: string, example: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((s) => (
        <button
          key={s.key}
          onClick={() => onPick(s.key, s.example)}
          title={s.example ? `Ejemplo: ${s.example}` : undefined}
          className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md
                     border border-white/[0.07] bg-elevated/50 text-[11px]
                     text-text-dim hover:text-text hover:border-pri/35
                     hover:bg-pri/10 transition-all duration-150"
        >
          <Icon name="plus" size={10} />
          {s.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Resultados de búsqueda global ────────────────────────────────── */
function GlobalResults({
  hits, onSave, onDelete,
}: {
  hits: { cat: MemoryCategory; key: string; value: string; updated?: string }[];
  onSave: (cat: MemoryCategory, key: string, v: string) => void;
  onDelete: (cat: MemoryCategory, key: string) => void;
}) {
  if (hits.length === 0) {
    return <Empty icon="search" title="Sin resultados" hint="Probá con otra palabra clave." />;
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[10px] uppercase tracking-[0.22em] text-text-dim mb-1 font-mono">
        {hits.length} resultado{hits.length === 1 ? "" : "s"}
      </div>
      {hits.map((h, i) => {
        const catInfo = CATEGORIES.find((c) => c.id === h.cat);
        return (
          <Row
            key={`${h.cat}-${h.key}`}
            entryKey={h.key}
            value={h.value}
            updated={h.updated}
            delay={i * 20}
            badge={
              catInfo && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px]
                                 uppercase tracking-[0.18em] text-pri/80 bg-pri/10 border border-pri/20 font-mono">
                  <Icon name={catInfo.icon} size={9} />
                  {catInfo.label}
                </span>
              )
            }
            onSave={(v) => onSave(h.cat, h.key, v)}
            onDelete={() => onDelete(h.cat, h.key)}
          />
        );
      })}
    </div>
  );
}

/* ─── Row (entry editable) ─────────────────────────────────────────── */
function Row({
  entryKey, value, updated, delay, badge, onSave, onDelete,
}: {
  entryKey: string; value: string; updated?: string; delay?: number;
  badge?: React.ReactNode;
  onSave: (v: string) => void; onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState(value);
  useEffect(() => { setDraft(value); }, [value]);

  return (
    <Surface
      level={2}
      className="group px-3.5 py-2.5 animate-fade-in-up"
      style={{ animationDelay: `${delay ?? 0}ms` }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="shrink-0 flex items-center gap-2 max-w-[34%]">
          <code className="text-xs font-mono text-acc/90 tracking-tight truncate">
            {entryKey}
          </code>
          {badge}
        </div>
        {editing ? (
          <input
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => { onSave(draft); setEditing(false); }}
            onKeyDown={(e) => {
              if (e.key === "Enter")  { onSave(draft); setEditing(false); }
              if (e.key === "Escape") { setDraft(value); setEditing(false); }
            }}
            className="flex-1 bg-surface border border-pri/40 rounded px-2 py-1 text-sm focus:outline-none"
          />
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="flex-1 text-left text-sm text-text hover:text-pri transition-colors cursor-text"
          >
            {value}
          </button>
        )}
        <button
          onClick={onDelete}
          title="Borrar"
          className="h-7 w-7 grid place-items-center rounded-md text-text-dim
                     opacity-0 group-hover:opacity-100
                     hover:text-danger hover:bg-danger/10 transition-all"
        >
          <Icon name="close" size={14} />
        </button>
      </div>
      {updated && (
        <div className="text-[10px] uppercase tracking-[0.16em] text-muted mt-1 font-mono">
          {updated}
        </div>
      )}
    </Surface>
  );
}
