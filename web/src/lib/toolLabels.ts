/**
 * toolLabels — etiquetas amistosas para los nombres internos de tools.
 *
 * Compartido entre ToolBanner (chip global arriba del chat) y
 * ThinkingIndicator (indicador inline debajo del último mensaje del
 * usuario). Centralizado acá para que ambos componentes muestren la
 * misma cosa y no haya drift cuando se agregue una tool nueva.
 *
 * Para tools MCP (formato `<server>__<tool>`) intentamos un fallback
 * humano del estilo "MCP: <server> · <tool>".
 */

export interface ToolLabel {
  label: string;
  icon:  string;
}

const TOOL_LABELS: Record<string, ToolLabel> = {
  web_search:           { label: "Buscando en la web",          icon: "🔍" },
  notebooklm_research:  { label: "Investigando con NotebookLM", icon: "📚" },
  ask_user:             { label: "Esperando tu respuesta",      icon: "💬" },
  file_controller:      { label: "Trabajando con archivos",     icon: "📂" },
  bulk_delete:          { label: "Limpiando archivos",          icon: "🗑️" },
  generated_code:       { label: "Generando código",            icon: "💻" },
  file_processor:       { label: "Procesando archivo",          icon: "📄" },
  screen_process:       { label: "Analizando la pantalla",      icon: "👁️" },
  screen_processor:     { label: "Analizando la pantalla",      icon: "👁️" },
  weather_report:       { label: "Consultando el clima",        icon: "☁️" },
  reminder:             { label: "Programando recordatorio",    icon: "⏰" },
  send_message:         { label: "Enviando mensaje",            icon: "💬" },
  open_app:             { label: "Abriendo aplicación",         icon: "🪟" },
  browser_control:      { label: "Controlando navegador",       icon: "🌐" },
  computer_control:     { label: "Controlando el sistema",      icon: "🖥️" },
  computer_settings:    { label: "Ajustando el sistema",        icon: "⚙️" },
  iot_control:          { label: "Controlando IoT",             icon: "💡" },
  sensors:              { label: "Leyendo sensores",            icon: "📊" },
  google_drive:         { label: "Trabajando con Drive",        icon: "📦" },
  classroom:            { label: "Revisando Classroom",         icon: "📚" },
  youtube_video:        { label: "Buscando en YouTube",         icon: "▶️" },
  flight_finder:        { label: "Buscando vuelos",             icon: "✈️" },
  desktop_control:      { label: "Operando el escritorio",      icon: "🖱️" },
  game_updater:         { label: "Gestionando juego",           icon: "🎮" },
  code_helper:          { label: "Asistiendo con código",       icon: "🧰" },
  dev_agent:            { label: "Construyendo proyecto",       icon: "🏗️" },
  agent_task:           { label: "Delegando a un agente",       icon: "🤝" },
  use_skill:            { label: "Cargando skill",              icon: "📜" },
  quick_note:           { label: "Guardando nota",              icon: "📝" },
  save_memory:          { label: "Memorizando",                 icon: "🧠" },
  shutdown_orion:       { label: "Apagando",                    icon: "🛑" },
};

export function prettyToolName(name: string): ToolLabel {
  const known = TOOL_LABELS[name];
  if (known) return known;
  // Tools MCP: formato `<server>__<tool>` — desglosamos.
  if (name.includes("__")) {
    const [server, tool] = name.split("__", 2);
    const human = (tool ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    return { label: `MCP · ${server} · ${human}`, icon: "🔌" };
  }
  const human = name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return { label: human, icon: "🛠️" };
}
