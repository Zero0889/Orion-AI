<div align="center">

# O.R.I.O.N

### Operador de Redes Inteligentes y Optimización Neural

**Asistente de IA personal multimodal — voz en tiempo real, visión, control del sistema. Local, web-only, sin suscripciones.**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/license-CC%20BY--NC%204.0-blue.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20React-success.svg)]()
[![Last commit](https://img.shields.io/github/last-commit/Zero0889/Orion-AI.svg)](https://github.com/Zero0889/Orion-AI/commits/master)

<!-- Reemplaza esta línea con un GIF o screenshot de Orion en acción (assets/hero.gif) -->
<!-- ![Orion demo](assets/hero.gif) -->

</div>

---

## Tabla de contenidos

- [¿Qué es Orion?](#-qué-es-orion)
- [Capacidades](#-capacidades)
- [Quick Start](#-quick-start)
- [Configuración](#-configuración)
- [Arquitectura](#-arquitectura)
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
| 🛡️ Acceso por huella | ESP32 + AS608 → Telegram con notificación por entrada |
| 📲 Telegram bot | Notificaciones por supergrupo con topics |
| 🔌 Ecosistema MCP | Skills, Agents y Notifications vía Model Context Protocol |
| 📁 Diagnóstico in-app | Panel para ver logs y rutas sin abrir el CMD |

---

## ⚡ Quick Start

### Prerrequisitos

- **Python 3.11 o 3.12** — `py -3 --version`
- **Node.js LTS** (18+) — `node --version`
- **Git**

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

La primera vez aparece un **wizard de bienvenida** pidiendo tu API key
de Gemini. Conseguila gratis en
[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).

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
| `ORION_PROJECTS_DIR` | `~/Desktop/OrionProjects` | Carpeta del agente Coder. |
| `ORION_UPLOADS_DIR` | `<repo>/uploads` | Drop-zone para uploads. |
| `ORION_GOOGLE_CLIENT_SECRET` | (auto) | Path al `client_secret.json` custom. |

---

## 🏗️ Arquitectura

```
       ┌────────────────────────────────────────────┐
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
       │  └─ Paneles: Chat, IoT, Acceso, MCP, …     │
       └────────────────────────────────────────────┘
```

Sin Tauri, sin .exe, sin .msi. Orion corre como `python -m orion` y se
abre en el navegador. Si querés acceder desde otros dispositivos
(celular, tablet) podés exponerlo vía Tailscale — el toggle "Compartir
vía Tailscale" en Ajustes lo hace bindeo seguro a tu tailnet.

**Stack principal:**

- **Backend**: Python 3.11+ · FastAPI · uvicorn · WebSocket · structlog
- **Frontend**: React 18 · TypeScript · Vite · Tailwind · Zustand · TanStack Query
- **LLM**: Gemini Live (multi-provider vía abstracción)
- **Extensiones**: MCP (Model Context Protocol) · Skills · Agents
- **Hardware**: ESP32 (sketches en `arduino/`) — sensores IoT, control de acceso por huella

---

## 📋 Requisitos

| Requisito | Detalle |
|---|---|
| **SO** | Windows 10/11 x64, macOS, o Linux |
| **Python** | 3.11 o 3.12 |
| **Node.js** | 18+ (para el frontend) |
| **RAM** | 4 GB mínimo, 8 GB recomendado |
| **Micrófono** | Opcional (solo si querés voz) |
| **API Key** | Clave gratuita de Gemini |

---

## 🐛 Troubleshooting

<details>
<summary>"Puerto 8765 ocupado"</summary>

Otro proceso de Orion (o cualquier app) está usando el puerto. Cerralo
con el Task Manager o cambiá el puerto si tu setup lo permite.

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
- **Archivo**: `logs/orion.log` en el repo.

Los logs rotan cada 5 MB con 3 archivos de backup.

</details>

<details>
<summary>"npm run build" falla con error de memoria</summary>

Node 18 a veces se queda corto con vendor-react + vendor-katex. Probá:

```bat
set NODE_OPTIONS=--max-old-space-size=4096
cd web && npm run build
```

</details>

---

## ⚠️ Licencia

Uso personal y no comercial.
Bajo licencia **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Créditos

Desarrollado como un asistente de IA personal de nueva generación.

Tecnologías:
[Gemini Live](https://ai.google.dev/) ·
[FastAPI](https://fastapi.tiangolo.com/) ·
[Vite](https://vitejs.dev/) ·
[React](https://react.dev/) ·
[Tailwind](https://tailwindcss.com/)
