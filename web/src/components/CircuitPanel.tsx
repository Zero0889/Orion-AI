/**
 * CircuitPanel — Imagen de circuito → SPICE (.cir) + KiCad (.kicad_sch).
 *
 * Flujo:
 *   1. El usuario arrastra/elige una imagen del circuito.
 *   2. Subimos la imagen vía /api/files/upload (reusa el handler genérico).
 *   3. Llamamos /api/circuit/from-image con la ruta devuelta.
 *   4. Mostramos un resumen del circuito detectado y los archivos generados.
 *
 * Patrón visual calcado de IoTPanel: SectionHeader + secciones con scroll
 * + tarjetas. Botones discretos por item: copiar ruta, abrir carpeta,
 * eliminar.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type CircuitGenerateResult, type CircuitItem } from "@/api/rest";
import { humanizeTime } from "@/lib/humanTime";
import { toast } from "@/stores/toast";
import { Icon } from "@/ui/Icon";
import { Badge, Button, Empty, SectionHeader, Surface } from "@/ui/primitives";

const ACCEPT = "image/png,image/jpeg,image/webp,image/bmp,image/gif";

interface Generated {
  spice?: string;
  kicad?: string;
  summary: string;
}

export function CircuitPanel() {
  const [items, setItems] = useState<CircuitItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [lastResult, setLastResult] = useState<Generated | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  // refetch lista
  useEffect(() => {
    let alive = true;
    api
      .circuitList()
      .then((r) => {
        if (alive) {
          setItems(r.items);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [refreshTick]);

  // Procesar una imagen ya seleccionada
  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setProcessing(true);
    setLastResult(null);
    try {
      const upload = await api.uploadFile(file);
      const result: CircuitGenerateResult = await api.circuitFromImage(upload.path);
      setLastResult({
        spice: result.spice_path,
        kicad: result.kicad_path,
        summary: result.summary,
      });
      toast.success(
        "Circuito generado",
        [result.spice_path && ".cir SPICE listo", result.kicad_path && ".kicad_sch listo"]
          .filter(Boolean)
          .join(" — ") || "Sin archivos",
      );
      setRefreshTick((n) => n + 1);
    } catch (e) {
      const msg = String(e);
      setError(msg);
      toast.error("No se pudo generar el circuito", msg.slice(0, 120));
    } finally {
      setProcessing(false);
    }
  }, []);

  // Input file
  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    if (inputRef.current) inputRef.current.value = "";
  }

  // Drag & drop
  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith("image/")) handleFile(f);
  }

  // Agrupar items por basename (cir + kicad_sch del mismo circuito)
  const grouped = useMemo(() => {
    const map = new Map<
      string,
      { base: string; spice?: CircuitItem; kicad?: CircuitItem; mtime: number }
    >();
    for (const it of items) {
      const base = it.name.replace(/\.(cir|kicad_sch)$/i, "");
      const entry = map.get(base) ?? { base, mtime: 0 };
      if (it.kind === "spice") entry.spice = it;
      else entry.kicad = it;
      entry.mtime = Math.max(entry.mtime, it.modified);
      map.set(base, entry);
    }
    return Array.from(map.values()).sort((a, b) => b.mtime - a.mtime);
  }, [items]);

  async function copyPath(path: string) {
    try {
      await navigator.clipboard.writeText(path);
      toast.info("Ruta copiada", path);
    } catch {
      toast.warn("No se pudo copiar", path);
    }
  }

  async function deleteOne(path: string) {
    try {
      await api.circuitDelete(path);
      toast.success("Archivo eliminado");
      setRefreshTick((n) => n + 1);
    } catch (e) {
      toast.error("No se pudo eliminar", String(e).slice(0, 120));
    }
  }

  async function autodrawInProteus(cirPath: string, placeInCanvas: boolean) {
    toast.info(
      "Pon Proteus en foreground",
      placeInCanvas
        ? "3 segundos para enfocar Proteus. ORION añadirá los componentes Y los colocará en el canvas."
        : "3 segundos para enfocar Proteus. ORION solo añadirá al panel DEVICES.",
    );
    try {
      const r = await api.circuitProteusAutodraw(cirPath, { placeInCanvas });
      if (r.ok) toast.success("Componentes añadidos a Proteus", r.summary.slice(0, 200));
      else toast.warn("Automatización terminó con avisos", r.summary.slice(0, 200));
    } catch (e) {
      toast.error("Autodibujo falló", String(e).slice(0, 200));
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <SectionHeader
        eyebrow="Herramientas"
        title="Circuitos"
        hint="Sube una imagen de un circuito electrónico y obtén la netlist SPICE (Proteus) y el esquemático KiCad."
        action={
          <div className="flex items-center gap-2">
            <Badge tone="info" dot>
              {items.length} archivos
            </Badge>
            <Button
              variant="primary"
              size="sm"
              icon="upload"
              onClick={() => inputRef.current?.click()}
              disabled={processing}
            >
              {processing ? "Analizando…" : "Subir imagen"}
            </Button>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              onChange={onPick}
              className="hidden"
            />
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {error && (
          <div className="mx-6 mt-3 flex items-start gap-2 p-3 rounded-md border border-danger/30 bg-danger/10 text-xs text-danger animate-fade-in">
            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Drop zone — BRIEF · Circuitos:
            · Borde "scan" en loop: línea del color acento recorre el
              perímetro sin parar (conic-gradient rotando dentro de una
              máscara de padding fino — clásico glow border de cabina).
            · Ícono PCB en SVG con trazas + chip central, no el genérico.
            · drag-over: escala 1.02, glow verde-vivo, "Suéltalo aquí".
            · prefers-reduced-motion: corta la rotación. */}
        <section className="p-6">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => !processing && inputRef.current?.click()}
            className={[
              "circuit-dropzone relative flex flex-col items-center justify-center gap-4",
              "px-10 py-14 rounded-2xl cursor-pointer overflow-hidden",
              "bg-elevated/30 backdrop-blur-sm",
              "transition-all duration-300 ease-spring",
              dragOver
                ? "scale-[1.02] bg-sem-success/[0.06] shadow-[0_0_40px_-8px_rgb(var(--sem-success)/0.5)]"
                : "hover:bg-elevated/55",
              processing ? "opacity-70 cursor-wait" : "",
            ].join(" ")}
            data-dragging={dragOver ? "true" : undefined}
            data-processing={processing ? "true" : undefined}
          >
            {/* Borde animado — el ::before del .circuit-dropzone lo dibuja
                con un conic-gradient rotando. Sin contenido aquí, solo
                deja que el CSS haga su trabajo. */}

            {/* PCB-style icon */}
            <div className="relative" aria-hidden>
              <span
                className="absolute inset-0 -m-2 rounded-2xl blur-2xl"
                style={{
                  background: dragOver
                    ? "radial-gradient(circle, rgb(var(--sem-success)/0.4), transparent 70%)"
                    : "radial-gradient(circle, rgb(var(--orion-pri)/0.32), transparent 70%)",
                  transition: "background 220ms ease",
                }}
              />
              <PCBIcon
                size={56}
                accent={dragOver ? "rgb(var(--sem-success))" : "rgb(var(--orion-pri))"}
              />
            </div>

            <div className="text-center relative z-10">
              <div className="text-sm font-medium text-text">
                {processing
                  ? "Analizando circuito con Gemini Vision…"
                  : dragOver
                    ? "Suéltalo aquí"
                    : "Arrastrá una imagen o tocá para elegir"}
              </div>
              <div className="text-[11px] text-text-dim mt-1 max-w-sm mx-auto">
                Foto, screenshot o esquemático dibujado. Acepto PNG, JPG, WEBP y BMP.
              </div>
            </div>

            {/* Spinner overlay durante el procesamiento */}
            {processing && (
              <div className="absolute inset-0 grid place-items-center pointer-events-none">
                <span className="h-8 w-8 rounded-full border-2 border-pri/30 border-t-pri animate-spin-fast" />
              </div>
            )}
          </div>
        </section>

        {/* Último resultado */}
        {lastResult && (
          <section className="px-6 pb-4">
            <Subhead title="Último análisis" />
            <Surface className="p-4">
              <div className="text-sm text-text mb-3">{lastResult.summary}</div>
              <div className="flex flex-wrap gap-2">
                {lastResult.spice && (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon="paperclip"
                    onClick={() => copyPath(lastResult.spice!)}
                  >
                    Copiar ruta .cir
                  </Button>
                )}
                {lastResult.kicad && (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon="paperclip"
                    onClick={() => copyPath(lastResult.kicad!)}
                  >
                    Copiar ruta .kicad_sch
                  </Button>
                )}
              </div>
            </Surface>
          </section>
        )}

        {/* Lista histórica */}
        <section className="p-6 pt-2">
          <Subhead title="Circuitos generados" count={grouped.length} />
          {grouped.length === 0 ? (
            <Empty
              icon="cpu"
              title="Sin circuitos todavía"
              hint="Subí un esquemático o una foto del circuito y lo analizo: genero el .cir y el .kicad_sch."
            />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {grouped.map((g) => (
                <CircuitCard
                  key={g.base}
                  base={g.base}
                  spice={g.spice}
                  kicad={g.kicad}
                  onCopy={copyPath}
                  onDelete={deleteOne}
                  onAutodraw={autodrawInProteus}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

/* ─────────────────────── Subcomponents ─────────────────────── */

function Subhead({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-baseline gap-2 mb-3">
      <h3 className="text-sm font-medium tracking-tight text-text">{title}</h3>
      {typeof count === "number" && <span className="text-xs text-text-dim">· {count}</span>}
    </div>
  );
}

function CircuitCard({
  base,
  spice,
  kicad,
  onCopy,
  onDelete,
  onAutodraw,
}: {
  base: string;
  spice?: CircuitItem;
  kicad?: CircuitItem;
  onCopy: (path: string) => void;
  onDelete: (path: string) => void;
  onAutodraw: (cirPath: string, placeInCanvas: boolean) => void;
}) {
  const date = new Date(Math.max(spice?.modified ?? 0, kicad?.modified ?? 0) * 1000);
  const [placeInCanvas, setPlaceInCanvas] = useState(true);
  return (
    <Surface className="p-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="text-sm font-medium text-text truncate" title={base}>
            {base}
          </div>
          <div className="text-xs text-text-dim" title={date.toISOString()}>
            {humanizeTime(date)}
          </div>
        </div>
        <Icon name="cpu" size={18} className="text-text-dim shrink-0" />
      </div>

      <div className="flex flex-col gap-2">
        {spice && (
          <FileRow
            item={spice}
            label=".cir (Proteus / SPICE)"
            onCopy={onCopy}
            onDelete={onDelete}
          />
        )}
        {kicad && (
          <FileRow item={kicad} label=".kicad_sch (KiCad)" onCopy={onCopy} onDelete={onDelete} />
        )}
      </div>

      {spice && (
        <div className="mt-3 pt-3 border-t border-white/[0.05] flex flex-col gap-2">
          <label className="flex items-center gap-2 text-xs text-text-dim cursor-pointer select-none">
            <input
              type="checkbox"
              checked={placeInCanvas}
              onChange={(e) => setPlaceInCanvas(e.target.checked)}
              className="accent-pri"
            />
            Colocar componentes en el canvas (en grilla)
          </label>
          <Button
            variant="primary"
            size="sm"
            icon="bolt"
            onClick={() => onAutodraw(spice.path, placeInCanvas)}
            title="Abre Proteus en Schematic Capture y enfócalo. ORION añadirá los componentes y, si está activado, los colocará en el canvas."
          >
            Autodibujar en Proteus
          </Button>
        </div>
      )}
    </Surface>
  );
}

function FileRow({
  item,
  label,
  onCopy,
  onDelete,
}: {
  item: CircuitItem;
  label: string;
  onCopy: (path: string) => void;
  onDelete: (path: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 p-2 rounded-md bg-white/[0.02] border border-white/[0.05]">
      <div className="min-w-0">
        <div className="text-xs text-text">{label}</div>
        <div className="text-[10px] text-text-dim truncate" title={item.path}>
          {item.path}
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <Button
          size="icon"
          variant="ghost"
          icon="paperclip"
          title="Copiar ruta"
          onClick={() => onCopy(item.path)}
        />
        <Button
          size="icon"
          variant="ghost"
          icon="trash"
          title="Eliminar"
          onClick={() => onDelete(item.path)}
        />
      </div>
    </div>
  );
}

/* ── PCBIcon — ícono SVG estilo PCB esquemático ───────────────────────
   Trazas eléctricas + pads + chip central. Más "real" que el genérico
   crosshair que estaba antes. Stroke = `currentColor` para teñir según
   el estado (acento por defecto, verde live en drag-over). */
function PCBIcon({ size = 48, accent }: { size?: number; accent: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      style={{ color: accent }}
      aria-hidden
    >
      {/* trazas horizontales/verticales */}
      <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeOpacity="0.7">
        <path d="M4 16 L20 16 L20 28" />
        <path d="M60 22 L48 22 L48 32" />
        <path d="M4 48 L20 48 L20 36 L26 36" />
        <path d="M60 50 L44 50 L44 40" />
        <path d="M32 4 L32 14" />
        <path d="M32 50 L32 60" />
      </g>
      {/* pads en los bordes */}
      <g fill="currentColor" fillOpacity="0.9">
        <circle cx="4" cy="16" r="1.6" />
        <circle cx="4" cy="48" r="1.6" />
        <circle cx="60" cy="22" r="1.6" />
        <circle cx="60" cy="50" r="1.6" />
        <circle cx="32" cy="4" r="1.6" />
        <circle cx="32" cy="60" r="1.6" />
      </g>
      {/* Chip central */}
      <rect
        x="22"
        y="22"
        width="20"
        height="20"
        rx="3"
        fill="currentColor"
        fillOpacity="0.12"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      {/* Patitas del chip */}
      <g stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeOpacity="0.85">
        <path d="M22 27 L18 27" />
        <path d="M22 32 L18 32" />
        <path d="M22 37 L18 37" />
        <path d="M42 27 L46 27" />
        <path d="M42 32 L46 32" />
        <path d="M42 37 L46 37" />
      </g>
      {/* Marca del pin 1 */}
      <circle cx="25" cy="25" r="1.2" fill="currentColor" />
    </svg>
  );
}
