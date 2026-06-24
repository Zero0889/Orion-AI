/**
 * WallpaperLayer — fondo personalizado del usuario.
 *
 * Se monta detrás del NeuralBackground (z-[-1] dentro de su contenedor)
 * cuando el usuario subió una imagen. Aplica el blur y el overlay oscuro
 * configurables desde Ajustes para que el contenido siga siendo legible.
 *
 * Si no hay wallpaper, no rendereamos nada — el NeuralBackground sigue
 * siendo el fondo por defecto (regla del prompt.md punto 4).
 */

import { usePersonalization } from "@/stores/personalization";

export function WallpaperLayer() {
  const wallpaper = usePersonalization((s) => s.wallpaper);
  const blur = usePersonalization((s) => s.wallpaperBlur);
  const overlay = usePersonalization((s) => s.wallpaperOverlay);

  if (!wallpaper) return null;

  return (
    <div
      aria-hidden
      className="absolute inset-0 pointer-events-none overflow-hidden"
      style={{ zIndex: 0 }}
    >
      {/* Imagen del usuario — cover + escala un poco mayor que viewport
          para que el blur no muestre bordes transparentes en los extremos. */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `url(${wallpaper})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
          filter: `blur(${blur}px)`,
          transform: `scale(${1 + blur / 200})`,
          transformOrigin: "center",
          transition: "filter 200ms ease-out, transform 200ms ease-out",
        }}
      />
      {/* Capa oscura encima del wallpaper para legibilidad. Va al % que
          el usuario eligió en el slider. */}
      <div
        className="absolute inset-0"
        style={{
          background: `rgb(var(--orion-bg) / ${overlay / 100})`,
          transition: "background 200ms ease-out",
        }}
      />
    </div>
  );
}
