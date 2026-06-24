/**
 * BrainChip — indicador discreto del cerebro activo, arriba del ChatPanel.
 *
 * Le dice al usuario qué motor está respondiendo en cada momento. Click
 * abre el SettingsPanel en la pestaña "Cerebro" para cambiarlo.
 *
 * Si la query falla o todavía está cargando, no renderiza nada — el chip
 * es un nice-to-have, no algo que tenga que mostrar siempre.
 */

import { useQuery } from "@tanstack/react-query";

import { api, type BrainState } from "@/api/rest";
import { QUERY_KEYS } from "@/query/keys";
import { useViewStore } from "@/stores/view";
import { Icon } from "@/ui/Icon";

export function BrainChip() {
  const setView = useViewStore((s) => s.setView);
  const { data } = useQuery<BrainState>({
    queryKey: QUERY_KEYS.settingsBrain,
    queryFn: () => api.getBrain(),
    staleTime: 60_000,
  });

  if (!data) return null;

  const { provider, model, is_live } = data.active;
  const providerMeta = data.providers.find((p) => p.id === provider);
  const label = providerMeta?.label ?? provider;
  // Si el provider no es Live mostramos un dot ámbar para que el usuario
  // entienda visualmente "ojo, no hay voz acá".
  const tone = is_live ? "live" : "text";

  function openSettings() {
    setView("settings");
    // Disparamos un evento que el SettingsPanel pueda escuchar para
    // saltar a la pestaña correcta. Sin esto el usuario aterrizaba
    // en "Apariencia" y tenía que clickear la pestaña Cerebro a mano.
    window.dispatchEvent(new CustomEvent("orion:settings:tab", { detail: "brain" }));
  }

  return (
    <button
      type="button"
      onClick={openSettings}
      title={`Cerebro: ${label} / ${model}. Click para cambiar.`}
      className={[
        "absolute right-3 top-3 z-10 flex items-center gap-1.5",
        "px-2.5 h-7 rounded-full border text-[10px] uppercase tracking-[0.18em] font-mono",
        "bg-elevated/80 backdrop-blur-sm transition-all duration-200 ease-out-expo",
        tone === "live"
          ? "border-pri/30 text-pri/90 hover:border-pri/50 hover:bg-pri/10"
          : "border-warn/30 text-warn/90 hover:border-warn/50 hover:bg-warn/10",
      ].join(" ")}
    >
      <span
        className={[
          "h-1.5 w-1.5 rounded-full",
          tone === "live"
            ? "bg-pri shadow-[0_0_6px_rgb(var(--orion-pri))]"
            : "bg-warn shadow-[0_0_6px_rgb(var(--orion-warn))]",
        ].join(" ")}
      />
      <span>{label}</span>
      <Icon name="chevron-down" size={10} className="opacity-60" />
    </button>
  );
}
