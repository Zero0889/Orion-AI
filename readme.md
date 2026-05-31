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

## 🖥️ Modos de UI

Desde la Fase 5 de la migración web, Orion puede arrancar en tres modos seleccionables con la variable de entorno **`ORION_UI`**:

| Modo | Qué levanta | Cuándo usarlo |
|---|---|---|
| `both` *(default)* | UI Qt **+** backend FastAPI/WS en paralelo. Mismo proceso, mismo origen. | Día a día — tienes la ventana de escritorio y además puedes abrir `http://127.0.0.1:8765` en cualquier navegador. |
| `web` | Solo backend + frontend React. **No carga PyQt6**. Abre el navegador automáticamente. | Servidores headless, Tauri, Raspberry Pi, o cuando prefieras solo la UI web. |
| `qt` | Solo UI PyQt6 (modo legacy). Sin backend web. | Compatibilidad con flujos antiguos / debug aislado de la UI Qt. |

```powershell
# Windows PowerShell
$env:ORION_UI = "web"
python main.py
```

```bash
# macOS / Linux
ORION_UI=web python main.py
```

Si prefieres dejarlo fijo, edita `config/api_keys.json` y añade `"ui_mode": "web"`. La variable de entorno siempre tiene prioridad.

**Desarrollo del frontend** (hot reload sobre cambios en `web/src/`):

```bash
cd web
npm install      # solo la primera vez
npm run dev      # http://localhost:5173 → backend en :8765
```

Para producción / Tauri, `npm run build` deja el bundle en `web/dist/`. El backend lo sirve automáticamente bajo `/`.

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
2. `pyinstaller packaging/orion_backend.spec` → `dist/orion-backend/`
3. Renombra el binario a `orion-backend-<target-triple>` y lo copia a `src-tauri/binaries/`
4. `cargo tauri build` → instalador final en `src-tauri/target/release/bundle/`

### Qué se distribuye

- **Windows**: `.msi` o `.exe` (NSIS)
- **macOS**: `.dmg` con bundle `.app`
- **Linux**: `.deb` y `.AppImage`

El binario final lleva todo dentro: no necesita Python instalado en la máquina del usuario.

### Troubleshooting

| Síntoma | Causa habitual |
|---|---|
| `orion-backend sidecar no encontrado` | Olvidaste renombrar al target-triple. Verifica `src-tauri/binaries/orion-backend-<triple>`. |
| Pantalla blanca al abrir | El backend tardó >30 s en responder. Mira los logs del sidecar (Tauri los reenvía a stderr). |
| Falta icono al hacer `cargo tauri build` | Ejecuta `cargo tauri icon path/to/orion.png` con un PNG cuadrado 1024×1024. |
| PyInstaller no encuentra módulos de plugins | Añade `--collect-submodules plugins` o regístralos en `hiddenimports` del spec. |

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
