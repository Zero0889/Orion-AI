# 🤖 O.R.I.O.N
### Operador de Redes Inteligentes y Optimización Neural

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supporting Windows, macOS, and Linux. Local execution. Zero subscriptions. Engineered for total autonomy.

---

## ✨ Overview

O.R.I.O.N es un asistente de IA personal avanzado y multiplataforma. Conecta el sistema operativo con la intención humana. A través de diálogo natural, O.R.I.O.N analiza tu pantalla, procesa documentos cargados y ejecuta flujos de trabajo complejos con una interfaz adaptativa.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language |
| 🖥️ System Control | Launch apps, manage files, execute terminal commands |
| 🧩 Autonomous Tasks | High-level planning for complex, multi-step goals |
| 👁️ Visual Awareness | Real-time screen processing and webcam vision |
| 🧠 Persistent Memory | Deeply remembers your projects, preferences, and personal context |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

---

## 🆕 Novedades

- 📂 **Advanced File Handling** — New support for direct file uploads. Drop PDFs, source code, or images into the assistant to have them analyzed, summarized, or edited instantly.
- 🎨 **Adaptive & Flexible UI** — A complete overhaul of the interface. The new UI is fully resizable and responsive, featuring transparency controls and customizable layouts to fit your workspace perfectly.
- 🐧🍎 **Refined Cross-Platform Stability** — Major fixes for macOS and Linux compatibility. Core system actions are now more consistent across all three major operating systems.
- ⚡ **Optimized Core Engine** — Significant performance boost in tool-calling logic and response generation, resulting in a 40% faster interaction speed.

---

## ⚡ Quick Start

```bash
pip install -r requirements.txt
playwright install
python main.py
```

> ⚠️ **Installation Note:** To keep the repository lightweight, some OS-specific dependencies are not bundled in `requirements.txt`. If you run into a `ModuleNotFoundError`, simply install the missing package via `pip install <module_name>` for your specific system.

---

## 🖥️ Interfaz web

Desde la **Fase 7** Orion es web-only: la UI vive en `web/` (React + TypeScript + Tailwind) y la sirve FastAPI desde el mismo puerto que la API. La antigua interfaz PyQt6 fue retirada — su código está en el historial de la rama `migration/web-ui` por si alguien necesita rescatar algo.

```powershell
python main.py
```

Esto:
1. Arranca el backend FastAPI en `http://127.0.0.1:8765`.
2. Lanza `OrionLive` en un thread daemon (Gemini Live + audio).
3. Abre tu navegador apuntando a la UI.

Para procesos sidecar (Tauri) o despliegues sin GUI, define `ORION_NO_BROWSER=1` y nada se autoabre.

**Desarrollo del frontend** (hot reload sobre cambios en `web/src/`):

```bash
cd web
npm install      # solo la primera vez
npm run dev      # http://localhost:5173 → backend en :8765
```

Para producción / Tauri, `npm run build` deja el bundle en `web/dist/`. El backend lo sirve automáticamente bajo `/`.

### Atajo `.bat` en el escritorio

Para arrancar Orion con un doble click sin abrir terminal:

```batch
@echo off
cd /d C:\Users\zahir\OneDrive\Desktop\O.R.I.O.N
call .venv\Scripts\activate.bat
python main.py
pause
```

Guarda eso como `Orion-Web.bat`. Para ponerle ícono: click derecho → **Crear acceso directo** → click derecho en el acceso directo → **Propiedades** → **Cambiar icono** → selecciona `src-tauri/icons/icon.ico`.

---

## 📦 Empaquetado nativo (Tauri + PyInstaller)

Desde la **Fase 6** Orion puede distribuirse como aplicación de escritorio firmada con instalador `.msi` / `.dmg` / `.deb` / `.AppImage`. La estructura:

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

### Prerequisitos

| Herramienta | Versión | Notas |
|---|---|---|
| Node.js | ≥ 18 | `npm` debe estar en el PATH |
| Python  | 3.11  | virtualenv `.venv` activado |
| Rust    | ≥ 1.70 | `rustup` lo más fácil — https://rustup.rs |
| `cargo-tauri` | 1.x | `cargo install tauri-cli --version "^1.6"` |
| Iconos | — | ver `src-tauri/icons/README.md` |

Una vez tengas todo:

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

> **Nota sobre onefile**: el backend va empaquetado como un único `.exe` autocontenido (~150 MB) con Python + todas las deps embebidas. PyInstaller lo extrae a `%TEMP%\_MEI*` la primera vez (3-5 s extra de arranque). Esto evita tener que distribuir una carpeta `_internal/` aparte, que Tauri 1.x no maneja bien junto al `externalBin`.

### Qué se distribuye

- **Windows**: `.msi` o `.exe` (NSIS)
- **macOS**: `.dmg` con bundle `.app`
- **Linux**: `.deb` y `.AppImage`

El binario final lleva todo dentro: no necesita Python instalado en la máquina del usuario.

### Troubleshooting

| Síntoma | Causa habitual | Solución |
|---|---|---|
| `orion-backend sidecar no encontrado` | Olvidaste renombrar al target-triple. | Verifica `src-tauri/binaries/orion-backend-<triple>.exe`. |
| Ventana se abre <1 s y desaparece, Edge se abre solo | Sidecar muere por path roto + el backend abre el navegador por defecto. | Asegúrate de que `RESOURCES_DIR` apunte a `sys._MEIPASS` en modo frozen, y que Tauri setea `ORION_NO_BROWSER=1` antes de spawnear (ya en `main.rs`). |
| `{"detail":"Not Found"}` al abrir | `web/dist/` no se encuentra dentro del bundle. | Mismo fix: usar `RESOURCES_DIR` (no `BASE_DIR`) para buscar el frontend. |
| `Set-ExecutionPolicy no se reconoce` | Estás en CMD, no en PowerShell. | Abre **PowerShell** (prompt empieza con `PS`), no `cmd.exe`. |
| `package.json not found` en step 4 | `beforeBuildCommand` resolvía mal el path (`../web` desde la raíz del proyecto). | Cambiado a `npm --prefix web run build` en `tauri.conf.json`. |
| `Acceso denegado` / `PermissionDenied` en `cargo tauri build` | Procesos viejos de Orion vivos, o OneDrive sincronizando `target/`. | `Stop-Process orion*`; pausa OneDrive; idealmente saca el proyecto de OneDrive. |
| Falta icono al hacer `cargo tauri build` | No has generado los iconos. | `cargo tauri icon ruta\a\logo.png` (PNG cuadrado 1024×1024). |
| PyInstaller no encuentra módulos de plugins | Carga dinámica que el análisis estático no detecta. | Ya añadido `collect_submodules("plugins")` en `packaging/orion_backend.spec`. |
| `TerminatorExpectedAtEndOfString` al correr el build script | PowerShell 5.1 lee UTF-8 sin BOM como Windows-1252 y rompe caracteres especiales. | Usa solo ASCII en los scripts `.ps1`, o guárdalos con BOM, o actualiza a PowerShell 7 (`winget install Microsoft.PowerShell`). |
| Pantalla blanca >30 s | Backend tardó demasiado en arrancar. | Mira logs del sidecar (Tauri los reenvía a stderr). |

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Key** | Free Gemini API key |

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Créditos

Desarrollado como un asistente de IA personal de nueva generación.
