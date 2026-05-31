# Iconos de la app

Tauri necesita estos archivos en esta carpeta para empaquetar:

```
icons/
├── 32x32.png
├── 128x128.png
├── 128x128@2x.png
├── icon.icns          (macOS)
└── icon.ico           (Windows)
```

## Generación

La forma más rápida es partir de **un PNG cuadrado** (1024×1024 px,
fondo transparente) y dejar que Tauri genere todos los tamaños:

```bash
# Desde la raíz del repo
cargo install tauri-cli --version "^1.6"
cargo tauri icon path/to/source-icon.png
```

Eso escribe todos los archivos requeridos aquí mismo.

## Mientras no haya icono real

Tauri se quejará durante `cargo tauri build` si faltan estos archivos.
Para pruebas rápidas de la build se puede usar el icono que envía
Tauri en su template (`cargo tauri init` lo descarga). Cuando tengamos
arte definitivo de Orion, se reemplaza el PNG fuente y se vuelve a
correr `cargo tauri icon`.
