/**
 * audioPlayer — reproduce los chunks PCM que el backend stream-ea por WS.
 *
 * Backend (orion/audio.py:_play_audio) publica cada chunk de Gemini Live
 * como evento `audio.chunk` con `pcm_b64` (PCM 16-bit mono @ 24 kHz,
 * base64-encoded). Acá los decodificamos y los reproducimos vía Web
 * Audio API.
 *
 * Decisiones:
 *
 * - **AudioContext singleton.** Crear uno por chunk es carísimo y los
 *   browsers tienen un límite de ~6 contextos vivos. Uno solo, reusado.
 *
 * - **Schedule absoluto con `nextPlayTime`.** Cada `BufferSource.start(t)`
 *   recibe el tiempo exacto donde debe empezar; concatenamos chunks
 *   contiguos para que no haya gaps audibles (clicks). Si el último
 *   chunk se quedó corto (audio terminado), `nextPlayTime` queda en el
 *   pasado y el próximo chunk arranca de inmediato.
 *
 * - **Autoplay policy: `arm()` bajo gesto.** Chrome/Safari NO permiten
 *   crear/resumir un AudioContext sin user gesture. App.tsx escucha el
 *   primer click/touch y llama `armAudioPlayer()`. Antes de eso los
 *   chunks se descartan (y se loggea una vez para que sea obvio).
 *
 * - **Sin decodeAudioData.** No estamos recibiendo WAV o MP3 sino PCM
 *   raw → no hace falta el decoder del browser. Construimos el
 *   `AudioBuffer` manualmente desde el Int16Array — mucho más barato.
 */

let ctx: AudioContext | null = null;
let nextPlayTime = 0;
let armed = false;
let warnedNotArmed = false;

function getCtx(): AudioContext | null {
  if (ctx) return ctx;
  if (typeof window === "undefined") return null;
  const Ctor =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  try {
    ctx = new Ctor();
  } catch {
    ctx = null;
  }
  return ctx;
}

/** Arma el player bajo gesto del usuario (resume el AudioContext).
 *  Idempotente. Llamar varias veces es seguro. */
export function armAudioPlayer(): void {
  const c = getCtx();
  if (!c) return;
  if (c.state === "suspended") {
    c.resume().catch(() => {});
  }
  armed = true;
}

/** True si ya hubo gesto del usuario y podemos reproducir. */
export function isAudioArmed(): boolean {
  return armed;
}

/** Decodifica + agenda un chunk PCM 16-bit mono. */
export function playPcmChunk(b64: string, sampleRate: number): void {
  if (!armed) {
    if (!warnedNotArmed) {
      // Una sola vez por sesión para no inundar la consola.
      console.warn(
        "[audioPlayer] chunk descartado: el AudioContext aún no recibió un gesto del usuario. " +
          "Tocá la pantalla o cualquier botón para activarlo.",
      );
      warnedNotArmed = true;
    }
    return;
  }
  const c = getCtx();
  if (!c) return;

  // 1) Base64 → Uint8Array (bytes raw del PCM).
  let bin: string;
  try {
    bin = atob(b64);
  } catch {
    return; // base64 inválido — descartamos.
  }
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);

  // 2) Reinterpretar como Int16Array little-endian. PCM little-endian es
  //    el formato que sale de Gemini Live. La byteLength debe ser par.
  if (u8.byteLength < 2) return;
  const sampleCount = Math.floor(u8.byteLength / 2);
  // Usamos DataView para forzar little-endian explícito — en x86/arm es
  // el host order, pero ser explícito evita sorpresas en otros archs.
  const dv = new DataView(u8.buffer, u8.byteOffset, sampleCount * 2);
  const f32 = new Float32Array(sampleCount);
  for (let i = 0; i < sampleCount; i++) {
    // Int16 LE → normalizado a [-1, 1) para Web Audio.
    f32[i] = dv.getInt16(i * 2, true) / 32768;
  }

  // 3) Construir AudioBuffer mono al sample-rate del chunk.
  let buf: AudioBuffer;
  try {
    buf = c.createBuffer(1, f32.length, sampleRate);
  } catch {
    return; // sample-rate fuera de rango o frame count inválido.
  }
  buf.copyToChannel(f32, 0);

  // 4) Schedule. `start(t)` toma tiempo absoluto del AudioContext.
  const src = c.createBufferSource();
  src.buffer = buf;
  src.connect(c.destination);
  const now = c.currentTime;
  const startAt = Math.max(now, nextPlayTime);
  src.start(startAt);
  nextPlayTime = startAt + buf.duration;
}

/** Marcador de fin de turno: el backend dejó de stream-ear audio. Sirve
 *  para que un eventual debug muestre "turno cerrado" sin asumir nada
 *  del estado del player (el browser drena los chunks ya agendados solo). */
export function markAudioTurnEnd(): void {
  // No-op por ahora — los chunks pendientes ya están schedulados en
  // `nextPlayTime` y se reproducen solos. Si en el futuro queremos
  // bajar la latencia al inicio del próximo turno, acá se podría
  // resetear `nextPlayTime = ctx.currentTime`.
}
