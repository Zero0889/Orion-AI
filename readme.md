<div align="center">

# O.R.I.O.N

### Operador de Redes Inteligentes y Optimización Neural

**Asistente de IA personal multimodal — voz en tiempo real, visión, control del sistema. Local, web-only, sin suscripciones.**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/license-CC%20BY--NC%204.0-blue.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20React%20%7C%20Tauri-success.svg)]()
[![Last commit](https://img.shields.io/github/last-commit/Zero0889/Orion-AI.svg)](https://github.com/Zero0889/Orion-AI/commits/master)

<!-- Reemplaza esta línea con un GIF o screenshot de Orion en acción (assets/hero.gif) -->
<!-- ![Orion demo](assets/hero.gif) -->

</div>

---

## Tabla de contenidos

- [¿Qué es Orion?](#-qué-es-orion)
- [Capacidades](#-capacidades)
- [Quick Start (usuario final)](#-quick-start-usuario-final)
- [Quick Start (desarrollador)](#-quick-start-desarrollador)
- [Configuración](#-configuración)
- [Arquitectura](#-arquitectura)
- [Empaquetado nativo](#-empaquetado-nativo-tauri--pyinstaller)
- [Requisitos](#-requisitos)
- [Troubleshooting](#-troubleshooting)
- [Licencia](#-licencia)

---

## 🧠 ¿Qué es Orion?

Orion es un asistente de IA personal avanzado que conecta tu sistema operativo
con la intención humana. A través de diálogo natural, analiza tu pantalla,
procesa documentos cargados y ejecuta flujos de trabajo complejos sobre una
interfaz web adaptativa servida en local. No es solo un asistente — es una
extensión de tu vida digital.

---

## 🚀 Capacidades

| Feature | Descripción |
|---|---|
| 🎙️ Voz en tiempo real | Conversación con latencia ultra-baja (Gemini Live) |
| 🖥️ Control del sistema | Lanza apps, gestiona archivos, ejecuta comandos |
| 🧩 Tareas autónomas | Planificación multi-paso con agentes especializados |
| 👁️ Conciencia visual | Procesado de pantalla y webcam en tiempo real |
| 🧠 Memoria persistente | Recuerda proyectos, preferencias y contexto |
| 📬 Bandeja unificada | Gmail · Classroom · Drive (OAuth opcional) |
| 🏠 IoT integrado | Control de dispositivos ESP32/Arduino con CRUD |
| 🔌 Ecosistema MCP | Skills, Agents y Notifications vía Model Context Protocol |
| 📁 Diagnóstico in-app | Panel para ver logs y rutas sin abrir el CMD |

---

## ⚡ Quick Start (usuario final)

> Si solo querés usar Orion, bajá el instalador.

1. Bajá el último release desde
   [Releases](https://github.com/Zero0889/Orion-AI/releases) — elegí
   **`Orion_X.Y.Z_x64-setup.exe`** (NSIS, recomendado).
2. Ejecutalo y seguí los pasos. Se instala en `C:\Program Files\Orion\`.
3. Abrí Orion desde el menú Inicio.
4. La primera vez aparece un **wizard de bienvenida** pidiendo tu API key
   de Gemini. Conseguila gratis en
   [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
   y pegala.
5. (Opcional) Para Gmail / Classroom / Drive, seguí
   [`docs/SETUP_GOOGLE_OAUTH.md`](docs/SETUP_GOOGLE_OAUTH.md).

> Si la ventana queda en negro o ves "backend no respondió", el problema
> más común es el [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).
> La pantalla de error tiene un botón directo para descargarlo.

---

## 🛠️ Quick Start (desarrollador)

### Prerrequisitos

- **Python 3.11 o 3.12** — `py -3 --version`
- **Node.js LTS** (18+) — `node --version`
- **Git**
- (Opcional para builds) **Rust + `cargo-tauri`** — `cargo install tauri-cli --version "^1.6"`

### Setup en un solo comando

```bat
git clone https://github.com/Zero0889/Orion-AI.git
cd Orion-AI
setup.bat
```

`setup.bat` hace:

1. Crear `.venv` con Python.
2. `pip install -r requirements.txt + requirements-dev.txt`.
3. `cd web && npm install && npm run build`.
4. Avisarte qué hacer después.

### Arrancar Orion

```bat
orion.bat
```

`orion.bat` valida prerrequisitos en cada arranque — si falta `web/dist/` lo
compila, si falta `.venv` lo crea. **No hace falta volver a correr
`setup.bat`** salvo que borres algo a mano.

### Frontend con HMR

Si vas a tocar React, corré Vite en paralelo:

```bat
REM Terminal 1: backend
python -m orion

REM Terminal 2: frontend con HMR
cd web
npm run dev
```

Abrí `http://localhost:5173`. El proxy de Vite redirige `/api/*` y `/ws` al
backend en `:8765`.

---

## ⚙️ Configuración

| Modo | Ubicación |
|---|---|
| Desarrollo | `<repo>/config/`, `<repo>/data/` |
| Instalado (frozen) | `%APPDATA%\Orion\config\`, `%APPDATA%\Orion\data\` |

Forzá otra ubicación con `ORION_DATA_HOME=C:\Path`.

### API key de Gemini (obligatoria)

Tres formas (por prioridad):

1. Pegarla en el wizard de bienvenida (lo más fácil).
2. Env var `ORION_GEMINI_KEY` — tiene prioridad sobre el archivo.
3. Editar `config/api_keys.json` a mano:
   ```json
   { "gemini_api_key": "AIza..." }
   ```

Conseguila gratis en [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).

### Google OAuth (opcional)

Para Gmail / Classroom / Drive / Calendar / Sheets — setup completo (~5 min)
documentado en [`docs/SETUP_GOOGLE_OAUTH.md`](docs/SETUP_GOOGLE_OAUTH.md).

### Variables de entorno

| Var | Default | Uso |
|---|---|---|
| `ORION_GEMINI_KEY` | (vacía) | API key de Gemini. Prioridad sobre el archivo. |
| `ORION_DATA_HOME` | (auto) | Forzar ruta de config/data. |
| `ORION_NO_BROWSER` | (vacía) | Si `=1`, no abre el navegador (Tauri lo setea). |
| `ORION_PROJECTS_DIR` | `~/Desktop/OrionProjects` | Carpeta del agente Coder. |
| `ORION_UPLOADS_DIR` | `<repo>/uploads` | Drop-zone para uploads. |
| `ORION_GOOGLE_CLIENT_SECRET` | (auto) | Path al `client_secret.json` custom. |

---

## 🏗️ Arquitectura

```
┌─────────────── Tauri shell (Rust, ~5 MB) ──────────────┐
│ WebView del SO ── http://127.0.0.1:8765                │
│  ├─ spawnea orion-backend.exe (sidecar PyInstaller)    │
│  └─ pantalla de error si backend no responde en 30s    │
└──────────────────┬─────────────────────────────────────┘
                   │
       ┌───────────▼────────────────────────────────┐
       │ Backend Python (FastAPI + uvicorn, :8765)  │
       │  ├─ orion/server/    FastAPI app + WS      │
       │  ├─ orion/runtime.py  OrionLive (Gemini)   │
       │  ├─ orion/agent/      planner + executor   │
       │  ├─ orion/adapters/   tools por dominio    │
       │  ├─ orion/domain/     memory + notas       │
       │  └─ orion/storage/    SQLite (WAL)         │
       └───────────┬────────────────────────────────┘
                   │
       ┌───────────▼────────────────────────────────┐
       │ Frontend React (web/, servido por FastAPI) │
       │  ├─ Vite + Tailwind + Zustand + TanStack Q │
       │  ├─ Tipos autogenerados desde OpenAPI      │
       │  └─ 14 paneles (Chat, Notas, Diagnóstico…) │
       └────────────────────────────────────────────┘
```

**Stack principal:**

- **Backend**: Python 3.11+ · FastAPI · uvicorn · WebSocket · structlog
- **Frontend**: React 18 · TypeScript · Vite · Tailwind · Zustand · TanStack Query
- **Desktop**: Tauri 1.6 (Rust) · PyInstaller 6 (sidecar)
- **LLM**: Gemini Live (multi-provider vía abstracción)
- **Extensiones**: MCP (Model Context Protocol) · Skills · Agents

---

## 📦 Empaquetado nativo (Tauri + PyInstaller)

```powershell
# Windows
./scripts/build.ps1
```
```bash
# macOS / Linux
./scripts/build.sh
```

Pipeline (4 pasos):

1. `npm run build` → `web/dist/`
2. `pyinstaller packaging/orion_backend.spec` (modo **onefile**) → `dist/orion-backend.exe`
3. Renombra el binario a `orion-backend-<target-triple>.exe` y lo copia a `src-tauri/binaries/`
4. `cargo tauri build` → instalador final en `src-tauri/target/release/bundle/`:
   - `msi/Orion_X.Y.Z_x64_en-US.msi`
   - `nsis/Orion_X.Y.Z_x64-setup.exe`

> **Nota sobre onefile**: el backend va empaquetado como un único `.exe`
> autocontenido (~165 MB) con Python + deps embebidas. PyInstaller lo
> extrae a `%TEMP%\_MEI*` la primera vez (3–5 s extra de arranque). Esto
> evita distribuir una carpeta `_internal/` aparte.

---

## 📋 Requisitos

| Requisito | Detalle |
|---|---|
| **SO** | Windows 10/11 x64, macOS, o Linux |
| **Python** | 3.11 o 3.12 (solo para desarrollo) |
| **RAM** | 4 GB mínimo, 8 GB recomendado |
| **VC++ Redist** | 2015-2022 ([descarga](https://aka.ms/vs/17/release/vc_redist.x64.exe)) |
| **Micrófono** | Opcional (solo si querés voz) |
| **API Key** | Clave gratuita de Gemini |

---

## 🐛 Troubleshooting

<details>
<summary>La ventana queda en negro o muestra "backend no respondió"</summary>

- **VC++ Redistributable** faltante: bajá
  [`vc_redist.x64.exe`](https://aka.ms/vs/17/release/vc_redist.x64.exe) y
  reinstalá.
- **Puerto 8765 ocupado**: cerrá lo que esté usando el puerto.
- **Antivirus**: agregá `orion-backend.exe` a la whitelist. Algunos AV
  agresivos lo flaggean por usar OpenCV + sounddevice.

</details>

<details>
<summary>"deleted_client" o "invalid_client" en logs de Gmail/Classroom</summary>

El OAuth Client ID que registraste fue borrado/invalidado en Google Cloud
Console. Seguí los pasos del paso "Errores comunes" en
[`docs/SETUP_GOOGLE_OAUTH.md`](docs/SETUP_GOOGLE_OAUTH.md).

</details>

<details>
<summary>Quiero ver los logs</summary>

- **Desde la UI**: panel **Diagnóstico** (sidebar) muestra el tail vivo +
  botones para abrir la carpeta y copiar al portapapeles.
- **Modo desarrollo**: `logs/orion.log` en el repo.
- **Modo instalado**: `%APPDATA%\Orion\logs\orion.log`.

Los logs rotan cada 5 MB con 3 archivos de backup.

</details>

<details>
<summary>Problemas comunes de empaquetado y arranque (avanzado)</summary>

| Síntoma | Causa habitual | Solución |
|---|---|---|
| `orion-backend sidecar no encontrado` | Olvidaste renombrar al target-triple. | Verifica `src-tauri/binaries/orion-backend-<triple>.exe`. |
| `{"detail":"Not Found"}` al abrir | `web/dist/` no se encuentra dentro del bundle. | Asegúrate de que `RESOURCES_DIR` apunte a `sys._MEIPASS` en frozen. |
| `Set-ExecutionPolicy no se reconoce` | Estás en CMD, no en PowerShell. | Abrí **PowerShell** (prompt empieza con `PS`). |
| `Acceso denegado` en `cargo tauri build` | Procesos viejos vivos o OneDrive sincronizando `target/`. | `Stop-Process orion*`; pausá OneDrive. |
| PyInstaller no encuentra módulos de plugins | Carga dinámica que el análisis estático no detecta. | Ya está `collect_submodules("orion.plugins")` en el spec. |
| Pantalla blanca >30 s | Backend tardó demasiado en arrancar. | Mirá `%APPDATA%\Orion\logs\orion.log`. |

</details>

---

## ⚠️ Licencia

Uso personal y no comercial.
Bajo licencia **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Créditos

Desarrollado como un asistente de IA personal de nueva generación.

Tecnologías:
[`gog`](https://github.com/rclone/gog) ·
[Gemini Live](https://ai.google.dev/) ·
[Tauri](https://tauri.app/) ·
[FastAPI](https://fastapi.tiangolo.com/) ·
[Vite](https://vitejs.dev/) ·
[React](https://react.dev/) ·
[Tailwind](https://tailwindcss.com/)
