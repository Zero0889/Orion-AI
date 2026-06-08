/**
 * Icon — centralized inline-SVG icon set (lucide-inspired strokes).
 *
 * Pure SVG so we don't add a dependency. All icons share a consistent
 * 24×24 viewBox + 1.6 stroke weight to keep the visual rhythm tight.
 */

import type { SVGProps } from "react";

export type IconName =
  | "chat" | "notes" | "memory" | "history" | "telemetry" | "agents"
  | "iot" | "settings" | "send" | "close" | "check" | "pin" | "edit"
  | "trash" | "plus" | "sparkles" | "paperclip" | "alert" | "wifi"
  | "wifi-off" | "mic" | "mic-off" | "stop" | "orbit" | "search"
  | "chevron-right" | "chevron-down" | "upload" | "download" | "shield"
  | "cpu" | "bolt" | "moon" | "sun" | "more" | "play" | "command"
  | "info" | "drag" | "circle-dot" | "panel-left"
  | "lightbulb" | "thermometer" | "droplet" | "gauge" | "motion"
  | "wind" | "tag" | "save" | "chart-line" | "plug" | "bell"
  | "add" | "arrow-left" | "arrow-right" | "arrow-down"
  | "compass" | "sigma" | "feather" | "chart" | "folder" | "sensors";

type Props = SVGProps<SVGSVGElement> & {
  name: IconName;
  size?: number;
};

export function Icon({ name, size = 18, strokeWidth = 1.6, className, ...rest }: Props) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}

const PATHS: Record<IconName, JSX.Element> = {
  chat: (
    <>
      <path d="M21 12a8.5 8.5 0 0 1-12.6 7.45L3 21l1.55-5.4A8.5 8.5 0 1 1 21 12Z" />
      <path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01" />
    </>
  ),
  notes: (
    <>
      <path d="M5 4.5h11l3 3V18a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 4 18V6A1.5 1.5 0 0 1 5.5 4.5Z" />
      <path d="M16 4.5V7a1.5 1.5 0 0 0 1.5 1.5H20" />
      <path d="M8 12h6M8 15.5h4" />
    </>
  ),
  memory: (
    <>
      <path d="M4 7c0-1.5 3.6-3 8-3s8 1.5 8 3-3.6 3-8 3-8-1.5-8-3Z" />
      <path d="M4 7v5c0 1.5 3.6 3 8 3s8-1.5 8-3V7" />
      <path d="M4 12v5c0 1.5 3.6 3 8 3s8-1.5 8-3v-5" />
    </>
  ),
  history: (
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v4h4" />
      <path d="M12 8v4l3 2" />
    </>
  ),
  telemetry: (
    <>
      <path d="M3 12h3.5l2-7 4 14 2-7H21" />
    </>
  ),
  agents: (
    <>
      <rect x="5" y="5" width="14" height="14" rx="3" />
      <rect x="9" y="9" width="6" height="6" rx="1.2" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
    </>
  ),
  iot: (
    <>
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5.5 10v9A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5v-9" />
      <path d="M10 20.5v-5h4v5" />
    </>
  ),
  plug: (
    <>
      {/* socket body */}
      <path d="M9 2v4" />
      <path d="M15 2v4" />
      <path d="M7 6h10v6a5 5 0 0 1-5 5 5 5 0 0 1-5-5V6Z" />
      <path d="M12 17v5" />
    </>
  ),
  settings: (
    <>
      <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1Z" />
    </>
  ),
  send: (
    <>
      <path d="M12 19V5" />
      <path d="m5 12 7-7 7 7" />
    </>
  ),
  close: <path d="M6 6 18 18M18 6 6 18" />,
  check: <path d="m5 12 4 4L19 7" />,
  pin: (
    <>
      <path d="M12 17v5" />
      <path d="M9 4h6l-1 5 3 3v2H7v-2l3-3-1-5Z" />
    </>
  ),
  edit: (
    <>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4Z" />
    </>
  ),
  trash: (
    <>
      <path d="M4 7h16" />
      <path d="M10 11v6M14 11v6" />
      <path d="M6 7h12l-1 12.5A1.5 1.5 0 0 1 15.5 21h-7A1.5 1.5 0 0 1 7 19.5Z" />
      <path d="M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  sparkles: (
    <>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
      <path d="M12 8.5 13 11l2.5 1L13 13l-1 2.5L11 13 8.5 12 11 11Z" />
    </>
  ),
  bell: (
    <>
      <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9z" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </>
  ),
  paperclip: (
    <path d="m21 12-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5L9.5 19a2 2 0 0 1-3-3l8.5-8.5" />
  ),
  alert: (
    <>
      <path d="M12 3 1.5 21h21Z" />
      <path d="M12 10v4M12 17.5h.01" />
    </>
  ),
  wifi: (
    <>
      <path d="M2 8.5a15 15 0 0 1 20 0" />
      <path d="M5 12a10 10 0 0 1 14 0" />
      <path d="M8.5 15.5a5 5 0 0 1 7 0" />
      <circle cx="12" cy="19" r="0.6" fill="currentColor" />
    </>
  ),
  "wifi-off": (
    <>
      <path d="M3 3l18 18" />
      <path d="M8.5 15.5a5 5 0 0 1 7 0" />
      <path d="M2 8.5a15 15 0 0 1 7-2.4" />
      <path d="M16 6a15 15 0 0 1 6 2.5" />
      <circle cx="12" cy="19" r="0.6" fill="currentColor" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="3" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </>
  ),
  "mic-off": (
    <>
      <path d="m3 3 18 18" />
      <path d="M9 9v3a3 3 0 0 0 5.12 2.12" />
      <path d="M15 9.34V6a3 3 0 0 0-5.94-.6" />
      <path d="M5 11a7 7 0 0 0 12 5" />
      <path d="M19 11a7 7 0 0 1-.34 2.16" />
      <path d="M12 18v3" />
    </>
  ),
  stop: <rect x="6.5" y="6.5" width="11" height="11" rx="2" />,
  orbit: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M21 12c0 4.97-4.03 9-9 9" strokeDasharray="3 3" />
      <path d="M3 12c0-4.97 4.03-9 9-9" strokeDasharray="3 3" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </>
  ),
  "chevron-right": <path d="m9 6 6 6-6 6" />,
  "chevron-down":  <path d="m6 9 6 6 6-6" />,
  upload: (
    <>
      <path d="M12 16V4" />
      <path d="m6 10 6-6 6 6" />
      <path d="M4 20h16" />
    </>
  ),
  download: (
    <>
      <path d="M12 4v12" />
      <path d="m6 14 6 6 6-6" />
      <path d="M4 22h16" />
    </>
  ),
  shield: <path d="M12 3 4 6v6c0 4.5 3.4 8.4 8 9 4.6-.6 8-4.5 8-9V6Z" />,
  cpu: (
    <>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
    </>
  ),
  bolt: <path d="M13 2 4 14h7l-2 8 9-12h-7Z" />,
  moon: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>
  ),
  more: (
    <>
      <circle cx="5"  cy="12" r="1" fill="currentColor" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
      <circle cx="19" cy="12" r="1" fill="currentColor" />
    </>
  ),
  play: <path d="M8 5v14l11-7z" />,
  command: <path d="M9 6a3 3 0 1 0 0 6h6a3 3 0 1 0 0-6 3 3 0 0 0-3 3v6a3 3 0 1 0 3-3H9a3 3 0 1 0 0 6 3 3 0 0 0 3-3V9" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8.5h.01M11 12h1v4.5h1" />
    </>
  ),
  drag: (
    <>
      <circle cx="9"  cy="6"  r="1" fill="currentColor" />
      <circle cx="9"  cy="12" r="1" fill="currentColor" />
      <circle cx="9"  cy="18" r="1" fill="currentColor" />
      <circle cx="15" cy="6"  r="1" fill="currentColor" />
      <circle cx="15" cy="12" r="1" fill="currentColor" />
      <circle cx="15" cy="18" r="1" fill="currentColor" />
    </>
  ),
  "circle-dot": (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </>
  ),
  "panel-left": (
    <>
      <rect x="3.5" y="4" width="17" height="16" rx="2.5" />
      <path d="M9.5 4v16" />
    </>
  ),
  lightbulb: (
    <>
      <path d="M9 18h6" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3Z" />
    </>
  ),
  thermometer: (
    <>
      <path d="M14 14.76V4.5a2.5 2.5 0 1 0-5 0v10.26a4.5 4.5 0 1 0 5 0Z" />
      <circle cx="11.5" cy="17" r="1.6" fill="currentColor" />
    </>
  ),
  droplet: (
    <path d="M12 3.5s-6 6.5-6 10.5a6 6 0 1 0 12 0c0-4-6-10.5-6-10.5Z" />
  ),
  gauge: (
    <>
      <path d="M12 14 18 8" />
      <circle cx="12" cy="14" r="1.6" fill="currentColor" />
      <path d="M3.5 18a9 9 0 1 1 17 0" />
    </>
  ),
  motion: (
    <>
      <circle cx="12" cy="5"  r="1.6" fill="currentColor" />
      <path d="M9 22V12l-2-2 3-4 3 4-2 2v10" />
      <path d="M15 13l3 3-2 5" />
      <path d="M7 13l-3 3 2 5" />
    </>
  ),
  wind: (
    <>
      <path d="M3 8h11a3 3 0 1 0-3-3" />
      <path d="M3 12h17a3 3 0 1 1-3 3" />
      <path d="M3 16h9a3 3 0 1 1-3 3" />
    </>
  ),
  tag: (
    <>
      <path d="M3 12V4.5A1.5 1.5 0 0 1 4.5 3H12l9 9-7.5 7.5L3 12Z" />
      <circle cx="7.5" cy="7.5" r="1" fill="currentColor" />
    </>
  ),
  save: (
    <>
      <path d="M5 4h11l3 3v12.5A1.5 1.5 0 0 1 17.5 21h-12A1.5 1.5 0 0 1 4 19.5v-14A1.5 1.5 0 0 1 5.5 4Z" />
      <path d="M7 4v5h9V4" />
      <path d="M7 14h10v7H7Z" />
    </>
  ),
  "chart-line": (
    <>
      <path d="M3 3v18h18" />
      <path d="M7 15l4-4 3 3 5-6" />
    </>
  ),
  add:       <path d="M12 5v14M5 12h14" />,
  "arrow-left":  <path d="M19 12H5m7-7-7 7 7 7" />,
  "arrow-right": <path d="M5 12h14m-7-7 7 7-7 7" />,
  "arrow-down":  <path d="M12 5v14m-7-7 7 7 7-7" />,
  compass: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M16.2 7.8l-2.4 6.6-6.6 2.4 2.4-6.6Z" />
    </>
  ),
  sigma:    <path d="M18 7V5H6v2l6 6-6 6v2h12v-2" />,
  feather:  <path d="M20.2 3 3 20.2M3 3l5.2 5.2M4.5 15.5l4 4" />,
  chart: (
    <>
      <path d="M18 20V10M12 20V4M6 20v-6" />
    </>
  ),
  folder: (
    <>
      <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v11Z" />
    </>
  ),
  sensors: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1Z" />
    </>
  ),
};
