# CLAUDE.md — Handoff para próximas sesiones

> **Para Claude/Codex/cualquier asistente que entre nuevo:** este archivo se
> lee automáticamente al inicio de cada sesión. Contiene el estado actual
> del refactor en curso, qué se hizo, qué falta, cómo está estructurado
> el repo, y las convenciones establecidas. **Léelo entero antes de tocar
> nada.**

---

## 1. ¿Qué es O.R.I.O.N?

Asistente de IA personal multimodal (voz en tiempo real con Gemini Live + visión + control del sistema + IoT + MCP) servido localmente con backend FastAPI/Python y frontend React/Vite/Tailwind/Zustand. Web-only desde Fase 7 (la UI Qt vieja fue eliminada).

**Stack:**
- Backend: Python 3.11/3.12, FastAPI, uvicorn, SQLite (WAL), `google-genai`
- Frontend: React 18, Vite, Tailwind, Zustand, openapi-typescript
- Empaquetado: Tauri (dev) + PyInstaller (sidecar Python)
- CI: GitHub Actions (matriz Linux/Windows × Python 3.11/3.12 + Node 20/22)

---

## 2. Estado del refactor (Junio 2026)

### ✅ Fase 1 — Seguridad + gates de calidad (cerrado, CI verde)
- `actions/desktop.py`: removida la ejecución de código LLM-generado vía `exec()` (era RCE por voz).
- `actions/open_app.py`, `actions/dev_agent.py`: `shell=True` con input LLM reemplazado por listas + sanitizer (`_safe_app_name` rechaza metacaracteres).
- `core/logger.py`: `_SecretFilter` enmascara Google/OpenAI/Anthropic keys, Bearer tokens, JWTs antes de loggear.
- `pyproject.toml` + `ruff` + `mypy` (gradual, estricto solo en módulos críticos) + `pre-commit` con gitleaks.
- `.github/workflows/ci.yml`: 7 jobs (Python × matriz, Web × 2 Node, Gitleaks, API drift).
- `.gitleaks.toml`, `.gitattributes` (LF forzado en checkout).
- Tests de regresión: `tests/test_security_hardening.py` (22 tests), `tests/test_logger_secret_filter.py` (9 tests).
- **Acción del user pendiente eventualmente:** rotar 3 keys que están en commits viejos del historial git (commits `e709ef48`, `95fe264e`): `config/api_keys.json`, `config/credentials.json`, `config/gdrive_token.json`. El user ya las rotó manualmente en Google Cloud Console. Si quiere también borrar del historial: `git filter-repo --invert-paths --path ...` (destructivo, requiere force-push).

### ✅ Fase 2 — Deuda técnica visible (cerrado, CI verde)
- `ruff format` baseline aplicado (~120 archivos Python).
- `prettier --write` baseline aplicado al frontend.
- Reescritos 23 sitios `raise X` → `raise X from e` (B904).
- 65 SIM105 (`try/except/pass` → `contextlib.suppress`).
- 3 `react-hooks/exhaustive-deps` warnings — 1 bug real fixed en `DeviceFormModal` (`kind` faltaba en deps de `useCallback`), 2 documentados con `eslint-disable-next-line` + razón.
- 3 archivos de tests rotos por drift reescritos:
  - `test_tool_registry.py` → invariantes en lugar de listas hardcoded.
  - `test_event_bus_contract.py::test_subscribe_unsubscribe` → borrado (feature removido).
  - `test_phase3b_endpoints.py` → 5 tests de `/api/agent/tasks` borrados (reemplazado por Orchestra).
- `--max-warnings=0` reactivado en `npm run lint`.

### ✅ Fase 3A — Decoradores `@tool` (cerrado, CI verde)
- Nuevo: `core/tool_registry.py` con decoradores `@tool` y `@live_only_tool` + `auto_discover_tools("actions")`.
- 23 tools migradas: la declaración (schema + flags) vive **junto a su handler** en `actions/*.py`. Agregar una tool nueva ahora es **tocar 1 archivo** en lugar de 3.
- `core/tools_bootstrap.py` bajó de **1209 LOC → 174 LOC** (-86%). Solo registra `ask_user` + `use_skill` (handlers custom no-action) y llama al auto-discover.
- 4 stubs live-only (`agent_task`, `shutdown_orion`, `quick_note`, `save_memory`) viven en `actions/live_stubs.py`.
- El decorador:
  - **Lazy lookup** del handler en cada call (respeta `unittest.mock.patch`).
  - **Re-inspecciona la firma** en cada invocación (mocks con menos params no rompen).
  - **Honra los flags** (`needs_player`, `needs_speak`, `needs_current_file`).
  - `runs_in_thread=True` → el wrapper spawnea daemon Thread y devuelve fallback inmediato (caso `screen_process`).
  - **Cache `_DECORATED_TOOLS` + `_replay_decorated()`**: los decoradores Python solo se ejecutan UNA vez por proceso; tests que llaman `ToolRegistry._reset()` necesitan replay para re-popular el registry.

### ✅ Fase 3B — SQLite para state (cerrado, CI verde)
Los 4 stores plain-JSON migrados a SQLite con WAL:

| Store | Tabla(s) | Antes | Status |
|---|---|---|---|
| `actions/notifications/store.py` | `notifications` | 127KB JSON | ✅ |
| `memory/quick_notes.py` | `quick_notes` | 375B JSON | ✅ |
| `memory/conversations.py` | `conversations` + `conversation_messages` (FK CASCADE) | 2B JSON | ✅ |
| `memory/memory_manager.py` | `memory_entries` | 674B JSON | ✅ |

**Infraestructura nueva:** `storage/` package con `sqlite_db.py` (conexión singleton, WAL, busy_timeout 5s, `check_same_thread=False`, `override_db_path_for_tests()` para fixtures).

**Migración automática:** en el primer uso de cada store, si existe el JSON viejo se importa y se archiva como `*.json.migrated_to_sqlite_<ts>.bak`. Idempotente: si la tabla ya tiene data, no re-importa.

**API pública intacta** — los routes REST, panels frontend y el resto del código no necesitaron cambios.

### ✅ Fase 3D — Tipos TS desde OpenAPI (cerrado, CI verde)
- `scripts/dump_openapi.py`: dumpea `app.openapi()` → `web/src/api/openapi.json` con `sort_keys=True` + LF forzado (`newline="\n"`) y filtra rutas SPA-fallback (`/`, `/{full_path}`) que dependen de `web/dist/` existir.
- `web/src/api/generated.ts` (4538 LOC): tipos TS generados via `openapi-typescript`. COMMITED (un dev frontend no necesita Python).
- `npm run gen:api` — regenera ambos artifacts. `npm run gen:api:check` — drift detection con diff line-by-line.
- Nuevo job CI `api-types-fresh`: corre `gen:api:check`, rojo si el backend cambió un schema y nadie regeneró.
- `web/src/api/rest.ts` expone `Schemas = components["schemas"]` y `ApiPaths = paths` para usar en código nuevo. Los `interface` manuales se mantienen por compat hasta que se toque cada panel.

### ✅ Fix bonus — Bug de chat duplicado (cerrado en commit `8664938`)
User reportó: cada turno aparecía dos veces en el chat. **Root cause:** `main.py:919,932` emitía `chat.stream(final=True)` Y `write_log()` para el mismo contenido. El dedup del frontend (`web/src/stores/orion.ts`) solo miraba el último mensaje y fallaba cuando el orden era `[stream user, stream orion, log user, log orion]`.

**Fixes:** backend usa `persist_log_only` (persiste sin re-publicar al WS); frontend dedupea con walk-backwards buscando mensaje del mismo role con `turnId` no `confirmedByLog`.

### 🟡 Fase 3C / Fase 4 — Romper god-files frontend (pendiente)
Cuatro componentes >900 LOC:
- `web/src/components/MCPPanel.tsx` (1452 LOC) — 12 sub-componentes + 2 types
- `web/src/components/DeviceFormModal.tsx` (~1001)
- `web/src/components/AgentsPanel.tsx` (~955)
- `web/src/components/IoTPanel.tsx` (~921)

**Riesgo:** `tsc + lint + build` pueden pasar verde aunque el split introduzca bugs sutiles de runtime (stale closures, state que no se preserva al cambiar de tab, hook order, props mal pasados). **Necesita validación visual** con `npm run dev` corriendo y clickear cada tab/panel después de cada split.

**Plan recomendado para esta fase:**
1. Empezar por `MCPPanel.tsx` (el más grande). Split sugerido:
   - `MCPPanel/index.tsx` — el shell con tabs + `TabButton`
   - `MCPPanel/ExploreTab.tsx` — `RegistryRow` + `ServerCard` + `StatusPill` + `ServerFormModal`
   - `MCPPanel/CuratedTab.tsx` — `RecipeCard` + `StarBadge` + `RecipeInstallModal`
   - `MCPPanel/types.ts` — `Tab`, `PrefillFromRegistry`
2. Una vez validado MCPPanel en el browser, hacer los 3 restantes con el mismo patrón.
3. Migrar los `interface` manuales en `web/src/api/rest.ts` a `Schemas["..."]` (auto-generados) en el camino — Fase 3D dejó el sistema listo.

---

## 3. Mapa del repo (qué archivo hace qué)

```
O.R.I.O.N/
├── main.py                       # Entry point. Gemini Live session + audio loop.
│                                 # 1196 LOC, candidato a split en Fase 5.
├── pyproject.toml                # Config de ruff, mypy, pytest (Fase 1).
├── .pre-commit-config.yaml       # Hooks: ruff, gitleaks, prettier+eslint locales.
├── .github/workflows/ci.yml      # 7 jobs (ver §4 abajo).
├── .gitleaks.toml                # Allowlist mínima — NO whitelistear patrones.
├── .gitattributes                # `* text=auto eol=lf` — fuerza LF en checkouts.
│
├── actions/                      # Tools que Gemini puede invocar.
│   ├── live_stubs.py             # Stubs Live-only (agent_task, shutdown, quick_note, save_memory).
│   ├── notifications/store.py    # SQLite-backed (Fase 3B).
│   ├── iot/control.py            # iot_control() — entry point IoT.
│   └── *.py                      # Cada uno tiene @tool(...) sobre su entrypoint.
│
├── agent/                        # Planner + executor + task queue + orchestra.
├── core/
│   ├── tool_registry.py          # @tool, @live_only_tool, auto_discover_tools (Fase 3A).
│   ├── tools_bootstrap.py        # ~170 LOC — auto-discover + ask_user + use_skill.
│   ├── logger.py                 # `_SecretFilter` enmascara keys (Fase 1).
│   ├── llm/*.py                  # Provider abstraction (gemini, openai-compat).
│   └── mcp_*.py                  # MCP client + recipes.
│
├── server/
│   ├── app.py                    # FastAPI app builder. CORS limitado a localhost+Tailscale.
│   ├── event_bus.py              # OrionEventBus (in-proc + WS broadcast).
│   ├── sharing.py                # Middleware: 127/8 + Tailscale 100.64/10.
│   └── routes/                   # /api/* endpoints.
│
├── storage/                      # SQLite layer (Fase 3B).
│   ├── __init__.py
│   └── sqlite_db.py              # get_connection() singleton + override_db_path_for_tests().
│
├── memory/
│   ├── quick_notes.py            # SQLite (Fase 3B). API: list_notes/add/update/delete/count.
│   ├── conversations.py          # SQLite (Fase 3B). + ConversationSession (sesión activa).
│   └── memory_manager.py         # SQLite (Fase 3B). API: load/save/update/format_for_prompt.
│
├── config/                       # Schema JSONs + secretos gitignored.
│   ├── __init__.py               # BASE_DIR, MEMORY_PATH, SQLITE_DB_PATH, DATA_DIR, etc.
│   └── *.example.json            # Templates de los configs reales (gitignored).
│
├── data/                         # State runtime SQLite (gitignored).
│   ├── orion.sqlite              # Todas las tablas de Fase 3B.
│   └── .gitkeep                  # Para que la carpeta exista al clonar.
│
├── scripts/
│   └── dump_openapi.py           # → web/src/api/openapi.json (Fase 3D).
│
├── tests/
│   ├── conftest.py               # Fixture autouse: SQLite tmp + mock sounddevice + extend SAFE_ROOTS.
│   ├── test_security_hardening.py    # 22 tests (Fase 1).
│   ├── test_logger_secret_filter.py  # 9 tests (Fase 1).
│   ├── test_notification_store_sqlite.py  # 15 tests (Fase 3B).
│   └── test_*.py                 # 333 total al cierre de Fase 3B.
│
└── web/
    ├── package.json              # scripts: dev, build, lint, format, typecheck, gen:api, gen:api:check.
    ├── eslint.config.js          # ESLint flat config v9.
    ├── .prettierrc.json          # printWidth 100, single line endings (lf), trailing commas (all).
    ├── .prettierignore           # Excluye openapi.json (generado).
    ├── scripts/check-api-types-fresh.mjs  # CI drift detection (Fase 3D).
    └── src/
        ├── api/
        │   ├── rest.ts           # Cliente HTTP. Expone `Schemas`, `ApiPaths`.
        │   ├── ws.ts             # WS client (auto-reconnect).
        │   ├── openapi.json      # Generado — NO editar a mano.
        │   └── generated.ts      # 4538 LOC de tipos TS — NO editar.
        ├── components/           # ⚠️ MCPPanel, DeviceFormModal, AgentsPanel, IoTPanel son god-files (Fase 3C pendiente).
        ├── stores/orion.ts       # Zustand store. Dedup de chat (post-fix `8664938`).
        ├── types.ts              # ChatMessage, ConnectionStatus, etc.
        └── App.tsx
```

---

## 4. CI — qué corre y qué reporta

El push a `main` dispara `.github/workflows/ci.yml` con 7 jobs:

| Job | Cuándo se enoja |
|---|---|
| **Python (3.11 / ubuntu-latest)** | ruff lint/format, mypy strict en módulos críticos, pytest 333 tests |
| **Python (3.12 / ubuntu-latest)** | idem en Python 3.12 |
| **Python (3.11 / windows-latest)** | idem cross-platform (captura bugs de `os.replace` cross-volume, etc.) |
| **Python (3.12 / windows-latest)** | idem |
| **Web (Node 20)** | tsc, eslint `--max-warnings=0`, prettier `--check`, vite build |
| **Web (Node 22)** | idem |
| **Gitleaks** | escanea diff por API keys, OAuth tokens, JWTs |
| **API types fresh** | `gen:api:check` — falla si backend cambió un schema y nadie regeneró `generated.ts` |

**Cómo monitorear:**
```bash
gh run list --limit 3
gh run view <id>                    # vista general
gh run view --job <job-id> --log-failed   # detalle de un job en rojo
```

**Si CI se rompe después de un push:**
1. `gh run view <id>` muestra qué jobs fallaron.
2. `--log-failed` muestra el output del step que crashó.
3. Si es el drift check, mira las primeras 20 líneas con diff que el script imprime — te dice EXACTAMENTE qué cambió.
4. Fix local, verifica con `pytest -q` + `npm run typecheck && npm run lint && npm run format:check && npm run gen:api:check && npm run build`, commit, push.

---

## 5. Convenciones establecidas

### Commits
- Cada commit pasa por hooks de `pre-commit`: ruff (lint+format), gitleaks, prettier+eslint (locales, usan `web/node_modules/.bin`).
- Para mensajes multi-línea, escribir a `.git/COMMIT_EDITMSG_<tag>` y `git commit -F <archivo>` — `git commit -m "..."` con strings largos a veces cuelga en Windows.
- Una vez instalado pre-commit (`pre-commit install`), los hooks corren solos.
- **Nunca usar `--no-verify`** salvo emergencia.

### Push y CI
- Después de cada push, esperar el resultado del CI antes de seguir trabajando relacionado.
- Si CI rojo: arreglar, push, re-monitor. No acumular cambios sobre una rama rota.
- Notificación de CI llega via `Monitor` tool si está armado.

### Agregar una tool nueva (post Fase 3A)
1. Crear/editar el archivo en `actions/`.
2. Decorar la función entry con `@tool(name=..., description=..., parameters=..., fallback=..., needs_speak=..., etc.)`.
3. Listo. El auto-discover de `core.tools_bootstrap.register_builtin_tools()` la encuentra al arrancar.
4. **No hay que tocar `tools_bootstrap.py`** ni `executor.py`.

### Agregar un endpoint nuevo en backend
1. Crear el route en `server/routes/*.py` con Pydantic models para body/response.
2. **Después regenerar tipos TS**: `cd web && npm run gen:api`.
3. Commit ambos cambios juntos. CI rojo si te olvidás de regenerar.

### Storage nuevo (state que persiste)
- **Si va a crecer (>10KB o mutación frecuente):** SQLite vía `storage.get_connection()`. Schema en el módulo, `CREATE TABLE IF NOT EXISTS`.
- **Si es pequeño y casi-inmutable (config):** JSON en `config/`.
- **Nunca:** state grande en JSON con full-rewrite por mutación.

### Tests
- Toda lógica nueva debe tener test. Pattern: tests/test_<modulo>.py.
- Fixture autouse `_isolated_sqlite_db` (en `conftest.py`) garantiza DB fresco por test.
- Para mockear funciones que vienen de `actions/`: usar `monkeypatch` o `unittest.mock.patch("actions.xxx.func", mock)` — el wrapper del decorador hace lazy lookup, así que el patch funciona.

---

## 6. Gotchas conocidos (no volver a tropezar)

| Síntoma | Causa | Fix |
|---|---|---|
| CI Windows falla con `Access denied: \System Volume Information` | `\` line continuation en YAML no funciona en PowerShell (interpreta como `C:\`) | Un solo line para mypy step |
| CI Windows falla con `ruff format --check` pero local pasa | `core.autocrlf=true` convirtió LF→CRLF en checkout | `.gitattributes` con `eol=lf` |
| Tests en Linux fallan con `Acceso denegado: /tmp/...` | `actions.file_controller._SAFE_ROOTS` solo whitelistea `~` (en Windows tmpdir cae bajo home, en Linux no) | `conftest.py` extiende `_SAFE_ROOTS` con `tempfile.gettempdir()` |
| CI Linux: `ModuleNotFoundError: sounddevice` en test_ui_mode | Dep nativa (PortAudio) no instalada | `conftest.py` mockea `sys.modules["sounddevice"]` |
| Tests CRUD fallan en Windows con `assert 404 == 200` | `os.replace` cross-filesystem falla en Windows; tempfile en MEMORY_DIR ≠ destino en tmp_path | `_save_all` ahora deriva tempfile dir de `target.parent` |
| Drift check rojo con diff cosmético en `openapi.json` | Python `Path.write_text` convierte `\n` → `\r\n` en Windows | `open(path, newline="\n")` explícito |
| Drift check rojo con `"/"` vs `"/api/agent/orchestra"` en L861 | `root_spa` y `/{full_path}` se registran condicionalmente en server/app.py si `web/dist` existe | `dump_openapi.py` filtra rutas SPA antes de escribir |
| Pre-commit prettier difiere de `npm run format:check` | `mirrors-prettier` rev v4-alpha vs package.json prettier 3.4.2 | Hook local: `npx --no-install prettier ...` usa `web/node_modules` |
| Hook prettier reformatea `notifications_store.json` cada commit | Runtime mutator + auto-fix | `.pre-commit-config.yaml` excluye archivos de state runtime |
| Tools decoradas se "olvidan" tras `ToolRegistry._reset()` | Decoradores Python corren solo 1× por proceso | Cache `_DECORATED_TOOLS` + `_replay_decorated()` en `auto_discover_tools` |
| Mensajes de chat aparecen dos veces | `main.py` emitía `write_log` además de `chat.stream(final=True)` | `persist_log_only` + dedup frontend con walk-backwards (fix `8664938`) |

---

## 7. Cosas que el user me dijo y conviene recordar

- Quiere usar Orion desde **celular/reloj/tablet** eventualmente, no solo PC. Por eso R1 y R2 (sacar `exec()` y `shell=True` con input LLM) fueron innegociables.
- Acepta el trade-off "opción A" cuando la "opción B surgical" no vale el costo (ej: commitear format baseline mezclado con lógica en vez de hacer la cirugía git de separarlos).
- Quiere **honestidad sobre alcance**: prefiere "esto es trabajo de otra sesión" antes que apurar refactors riesgosos.
- Pide validación visual para cambios de UI (Fase 3C necesita `npm run dev` + browser).
- Las **transcripciones árabes/persas** en la voz son cosa de Gemini Live STT (no del código), no perder tiempo intentando arreglarlas en el código.

---

## 8. Para empezar la próxima sesión

Comandos para verificar que todo está sano:

```bash
# Backend
python -m pytest -q --no-header                # esperar 333+ passing
python -m ruff check .                         # All checks passed
python -m ruff format --check .                # already formatted
python -m mypy --follow-imports=silent core/logger.py core/tool_registry.py core/llm/base.py server/app.py server/event_bus.py server/sharing.py server/telemetry.py

# Frontend
cd web
npm run typecheck                              # ok
npm run lint                                   # 0 errors
npm run format:check                           # All matched files use Prettier code style!
npm run gen:api:check                          # API types están al día
npm run build                                  # built in ~3s

# CI
gh run list --limit 3                          # último commit en verde
```

Si todo verde: arrancar Fase 3C / Fase 4 (god-files frontend). Si rojo: ver §4.
