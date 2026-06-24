/**
 * imageColor — extractor de color dominante de una imagen (dataURL).
 *
 * Estrategia liviana — sin libs externas:
 *   1. Cargo la imagen en un canvas a 50×50 (downsample agresivo).
 *   2. Itero los pixels y filtro los "poco interesantes":
 *      · alpha < 200          (transparentes)
 *      · luminosidad < 0.15   (negros que no aportan)
 *      · luminosidad > 0.92   (blancos / sobreexpuestos)
 *      · saturación < 0.20    (grises lavados)
 *   3. Acumulo los pixels que sobreviven y devuelvo el promedio.
 *   4. Si ningún pixel sobrevive el filtro (imagen monocromática
 *      desaturada), promedio TODOS los pixels como fallback —
 *      mejor un gris azulado que un crash.
 *
 * Es suficiente para fotos reales (paisajes, retratos, productos).
 * No es K-means ni Median-Cut, pero para auto-tintar un Ojo a un
 * wallpaper personal del usuario alcanza con creces.
 *
 * El resultado se devuelve en formato "R G B" (triplete con espacios)
 * para que conecte directo con el resto del sistema de tokens de ORION
 * (`rgb(var(--orion-pri) / 0.4)` etc).
 */

export interface RGBTriplet {
  /** "R G B" como string — drop-in para `rgb(VAR / X)`. */
  triplet: string;
  r: number;
  g: number;
  b: number;
}

const SAMPLE_SIZE = 50;

/**
 * Carga la imagen y devuelve el color dominante.
 *
 * Rechaza si la imagen no es decodificable (dataURL roto, formato no
 * soportado por el browser). El llamador debe envolver en try/catch.
 */
export async function extractDominantColor(dataUrl: string): Promise<RGBTriplet> {
  const img = await loadImage(dataUrl);
  const canvas = document.createElement("canvas");
  canvas.width = SAMPLE_SIZE;
  canvas.height = SAMPLE_SIZE;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) {
    throw new Error("No pude crear canvas 2D — el browser bloqueó getContext.");
  }
  ctx.drawImage(img, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE);
  const { data } = ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE);

  let r = 0;
  let g = 0;
  let b = 0;
  let n = 0;
  // Fallback paralelo: si nada sobrevive el filtro de vibrancia,
  // promediamos el set completo.
  let rAll = 0;
  let gAll = 0;
  let bAll = 0;
  let nAll = 0;

  for (let i = 0; i < data.length; i += 4) {
    const pr = data[i];
    const pg = data[i + 1];
    const pb = data[i + 2];
    const pa = data[i + 3];
    if (pa < 200) continue;

    rAll += pr;
    gAll += pg;
    bAll += pb;
    nAll++;

    const max = Math.max(pr, pg, pb);
    const min = Math.min(pr, pg, pb);
    const lightness = max / 255;
    const sat = max === 0 ? 0 : (max - min) / max;
    if (lightness < 0.15 || lightness > 0.92) continue;
    if (sat < 0.2) continue;

    r += pr;
    g += pg;
    b += pb;
    n++;
  }

  if (n === 0) {
    if (nAll === 0) {
      // Imagen completamente transparente — devolvemos un azul de marca
      // suave como último recurso para no romper el flujo.
      return { triplet: "96 99 236", r: 96, g: 99, b: 236 };
    }
    r = rAll;
    g = gAll;
    b = bAll;
    n = nAll;
  }

  const R = Math.round(r / n);
  const G = Math.round(g / n);
  const B = Math.round(b / n);
  return { triplet: `${R} ${G} ${B}`, r: R, g: G, b: B };
}

/**
 * A partir del color dominante, deriva un acento ligeramente más
 * "luminoso" o desplazado en hue para que el par primary/accent del
 * Ojo tenga algo de profundidad (sin esto, primary == accent y el
 * núcleo del iris se ve plano).
 *
 * Heurística: cambio la tonalidad un poco hacia el cian si el color
 * es cálido, hacia el ámbar si es frío. Esto evita acabar con un
 * "primary morado + accent morado" que se vería plano.
 */
export function deriveAccent(primary: RGBTriplet): RGBTriplet {
  const { r, g, b } = primary;
  // Lighten cada canal pero clampeando, manteniendo la dominancia.
  const lighten = (v: number) => Math.min(255, Math.round(v + (255 - v) * 0.35));
  let R = lighten(r);
  let G = lighten(g);
  let B = lighten(b);
  // Ajuste sutil de hue para que el acento no sea idéntico al primary
  // saturado: si el canal dominante es R, bajamos un poco R y subimos B.
  const max = Math.max(R, G, B);
  if (max === R) {
    R = Math.max(0, R - 18);
    B = Math.min(255, B + 18);
  } else if (max === B) {
    B = Math.max(0, B - 18);
    G = Math.min(255, G + 18);
  } else {
    G = Math.max(0, G - 18);
    R = Math.min(255, R + 18);
  }
  return { triplet: `${R} ${G} ${B}`, r: R, g: G, b: B };
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("No pude decodificar la imagen"));
    img.src = src;
  });
}
