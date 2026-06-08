<div align="center">

# O.R.I.O.N

### Operador de Redes Inteligentes y Optimización Neural

**Asistente de IA personal multimodal — voz en tiempo real, visión, control del sistema. Local, multiplataforma, sin suscripciones.**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/license-CC%20BY--NC%204.0-blue.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20React%20%7C%20Tauri-success.svg)]()
[![Last commit](https://img.shields.io/github/last-commit/Zero0889/O.R.I.O.N---IA.svg)](https://github.com/Zero0889/O.R.I.O.N---IA/commits/master)

<!-- Reemplaza esta línea con un GIF o screenshot de Orion en acción (assets/hero.gif) -->
<!-- ![Orion demo](assets/hero.gif) -->

</div>

---

## Tabla de contenidos

- [¿Qué es Orion?](#-qué-es-orion)
- [Capacidades](#-capacidades)
- [Novedades](#-novedades)
- [Quick Start](#-quick-start)
- [Interfaz web](#-interfaz-web)
- [Arquitectura](#-arquitectura)
- [Empaquetado nativo](#-empaquetado-nativo-tauri--pyinstaller)
- [Requisitos](#-requisitos)
- [Troubleshooting](#-troubleshooting)
- [Licencia](#-licencia)

---

## 🧠 ¿Qué es Orion?

Orion es un asistente de IA personal avanzado y multiplataforma que conecta tu sistema operativo con la intención humana. A través de diálogo natural, analiza tu pantalla, procesa documentos cargados y ejecuta flujos de trabajo complejos sobre una interfaz web adaptativa servida en local.

No es solo un asistente — es una extensión de tu vida digital.

---

## 🚀 Capacidades

| Feature | Descripción |
|---|---|
| 🎙️ Voz en tiempo real | Conversación con latencia ultra-baja en cualquier idioma |
| 🖥️ Control del sistema | Lanza apps, gestiona archivos, ejecuta comandos de terminal |
| 🧩 Tareas autónomas | Planificación de alto nivel para objetivos multi-paso |
| 👁️ Conciencia visual | Procesado de pantalla y webcam en tiempo real |
| 🧠 Memoria persistente | Recuerda proyectos, preferencias y contexto personal |
| ⌨️ Input híbrido | Cambia entre teclado y voz sin fricción |
| 🏠 IoT integrado | Control de dispositivos Wokwi/Arduino con admin CRUD |
| 🔌 Ecosistema MCP | Skills, Agents y Notifications conectables vía Model Context Protocol |

---

## 🆕 Novedades

- 📂 **Gestión avanzada de archivos** — Drop de PDFs, código o imágenes para análisis, resumen o edición instantánea.
- 🎨 **UI adaptativa** — Interfaz redimensionable y responsive, con transparencias y layouts customizables.
- 🐧🍎 **Estabilidad cross-platform** — Fixes mayores para macOS y Linux. Acciones del sistema consistentes en los tres OS.
- ⚡ **Motor optimizado** — 40% más rápido en tool-calling y generación de respuestas.
- 🔧 **Ecosistema MCP completo** — Skills + Agents + Notifications con paneles dedicados.

---

## ⚡ Quick Start

```bash
pip install -r requirements.txt
playwright install
python main.py
```

> ⚠️ **Nota de instalación:** para mantener el repo ligero, algunas dependencias específicas del SO no están en `requirements.txt`. Si te aparece un `ModuleNotFoundError`, instala el paquete que falta con `pip install <module_name>`.

---

## 🖥️ Interfaz web

Desde la **Fase 7** Orion es web-only: la UI vive en `web/` (React + TypeScript + Tailwind) y la sirve FastAPI desde el mismo puerto que la API. La antigua UI PyQt6 quedó en el historial de la rama `migration/web-ui`.

```powershell
python main.py
```

Esto:
1. Arranca el backend FastAPI en `http://127.0.0.1:8765`.
2. Lanza `OrionLive` en un thread daemon (Gemini Live + audio).
3. Abre tu navegador apuntando a la UI.

Para procesos sidecar (Tauri) o despliegues sin GUI, define `ORION_NO_BROWSER=1` y nada se autoabre.

### Desarrollo del frontend

Hot reload sobre cambios en `web/src/`:

```bash
cd web
npm install      # solo la primera vez
npm run dev      # http://localhost:5173 → backend en :8765
```

Para producción / Tauri: `npm run build` deja el bundle en `web/dist/` y el backend lo sirve bajo `/` automáticamente.

### Atajo `.bat` en el escritorio

Doble click sin abrir terminal:

```batch
@echo off
cd /d C:\Users\zahir\OneDrive\Desktop\O.R.I.O.N
call .venv\Scripts\activate.bat
python main.py
pause
```

Guárdalo como `Orion-Web.bat`. Para añadir ícono: click derecho → **Crear acceso directo** → **Propiedades** → **Cambiar icono** → `src-tauri/icons/icon.ico`.

---

## 🏗️ Arquitectura

```
┌─────────────── Tauri app (~5 MB Rust) ────────────────┐
│                                                       │
│  WebView del SO (Edge/WebKit) ── http://127.0.0.1:8765│
│                                          ▲            │
│                                          │ spawn      │
│                                          ▼            │
│  Sidecar: orion-backend (PyInstaller) ──────────────  │
│    ↳ main.py modo web                                 │
│    ↳ FastAPI + uvicorn + WS + actions/ + IoT          │
└───────────────────────────────────────────────────────┘
```

**Stack principal:**
- **Backend**: Python 3.11 · FastAPI · uvicorn · WebSocket
- **Frontend**: React · TypeScript · Tailwind · Zustand
- **Desktop**: Tauri 1.x (Rust) · PyInstaller (sidecar)
- **LLM**: Gemini Live (multiprovedor vía abstracción)
- **Extensiones**: MCP (Model Context Protocol) · Skills · Agents

---

## 📦 Empaquetado nativo (Tauri + PyInstaller)

Desde la **Fase 6** Orion puede distribuirse como aplicación de escritorio firmada con instalador `.msi` / `.dmg` / `.deb` / `.AppImage`.

### Prerequisitos

| Herramienta | Versión | Notas |
|---|---|---|
| Node.js | ≥ 18 | `npm` debe estar en el PATH |
| Python  | 3.11  | virtualenv `.venv` activado |
| Rust    | ≥ 1.70 | `rustup` lo más fácil — https://rustup.rs |
| `cargo-tauri` | 1.x | `cargo install tauri-cli --version "^1.6"` |
| Iconos | — | ver `src-tauri/icons/README.md` |

### Build

```powershell
# Windows
./scripts/build.ps1
```
```bash
# macOS / Linux
./scripts/build.sh
```

El script hace los 4 pasos en orden:
1. `npm run build` → `web/dist/`
2. `pyinstaller packaging/orion_backend.spec` (modo **onefile**) → `dist/orion-backend.exe`
3. Renombra el binario a `orion-backend-<target-triple>.exe` y lo copia a `src-tauri/binaries/`
4. `cargo tauri build` → instalador final en `src-tauri/target/release/bundle/`

> **Nota sobre onefile**: el backend va empaquetado como un único `.exe` autocontenido (~150 MB) con Python + todas las deps embebidas. PyInstaller lo extrae a `%TEMP%\_MEI*` la primera vez (3–5 s extra de arranque). Esto evita distribuir una carpeta `_internal/` aparte, que Tauri 1.x no maneja bien junto al `externalBin`.

### Distribución

- **Windows**: `.msi` o `.exe` (NSIS)
- **macOS**: `.dmg` con bundle `.app`
- **Linux**: `.deb` y `.AppImage`

El binario final lleva todo dentro: no necesita Python instalado en la máquina del usuario.

---

## 📋 Requisitos

| Requisito | Detalle |
|---|---|
| **SO** | Windows 10/11, macOS o Linux |
| **Python** | 3.11 o 3.12 |
| **Micrófono** | Necesario para interacción por voz |
| **API Key** | Clave gratuita de Gemini |

---

## 🐛 Troubleshooting

<details>
<summary>Problemas comunes de empaquetado y arranque</summary>

| Síntoma | Causa habitual | Solución |
|---|---|---|
| `orion-backend sidecar no encontrado` | Olvidaste renombrar al target-triple. | Verifica `src-tauri/binaries/orion-backend-<triple>.exe`. |
| Ventana se abre <1 s y desaparece, Edge se abre solo | Sidecar muere por path roto + el backend abre el navegador por defecto. | Asegúrate de que `RESOURCES_DIR` apunte a `sys._MEIPASS` en modo frozen, y que Tauri setea `ORION_NO_BROWSER=1` antes de spawnear (ya en `main.rs`). |
| `{"detail":"Not Found"}` al abrir | `web/dist/` no se encuentra dentro del bundle. | Mismo fix: usar `RESOURCES_DIR` (no `BASE_DIR`) para buscar el frontend. |
| `Set-ExecutionPolicy no se reconoce` | Estás en CMD, no en PowerShell. | Abre **PowerShell** (prompt empieza con `PS`), no `cmd.exe`. |
| `package.json not found` en step 4 | `beforeBuildCommand` resolvía mal el path. | Cambiado a `npm --prefix web run build` en `tauri.conf.json`. |
| `Acceso denegado` / `PermissionDenied` en `cargo tauri build` | Procesos viejos de Orion vivos, o OneDrive sincronizando `target/`. | `Stop-Process orion*`; pausa OneDrive; idealmente saca el proyecto de OneDrive. |
| Falta icono al hacer `cargo tauri build` | No has generado los iconos. | `cargo tauri icon ruta\a\logo.png` (PNG cuadrado 1024×1024). |
| PyInstaller no encuentra módulos de plugins | Carga dinámica que el análisis estático no detecta. | Ya añadido `collect_submodules("plugins")` en `packaging/orion_backend.spec`. |
| `TerminatorExpectedAtEndOfString` al correr el build script | PowerShell 5.1 lee UTF-8 sin BOM como Windows-1252 y rompe caracteres especiales. | Usa solo ASCII en los `.ps1`, guárdalos con BOM, o actualiza a PowerShell 7. |
| Pantalla blanca >30 s | Backend tardó demasiado en arrancar. | Mira logs del sidecar (Tauri los reenvía a stderr). |

</details>

---

## ⚠️ Licencia

Uso personal y no comercial.
Bajo licencia **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Créditos

Desarrollado como un asistente de IA personal de nueva generación.
