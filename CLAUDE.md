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
- Empaquetado: ninguno — Orion corre como `python -m orion` + frontend Vite servido por FastAPI. Sin .exe ni .msi (Tauri y PyInstaller fueron eliminados deliberadamente para ahorrar ~3 GB de cache y simplificar el repo).
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
- **Historial limpio:** `config/api_keys.json`, `config/credentials.json`, `config/gdrive_token.json` removidos del git history via `git filter-repo` + force-push. Keys ya rotadas previamente en Google Cloud Console. SHAs del repo reescritos (commit pre-rewrite era `ed1fabe`, post-rewrite `0ab810f`). **Backup en remoto: branch `backup-pre-filter-repo` @ `ed1fabe49b5ca2b28233eaaf7ee7ccc5922b1a6b`** — preserva el state pre-rewrite por si necesitás restaurar algo. Borrarlo cuando estés seguro: `git push origin --delete backup-pre-filter-repo`.

### ✅ Fase 2 — Higiene estructural (cerrado, CI verde, commit `21fda71`)

Reorganización completa del repo según el plan del audit. Antes había 7
top-level Python dirs sueltos en la raíz; ahora todo el código vive
bajo `orion/`. Estado actual:

```
project-root/
├── orion/                  # paquete principal (python -m orion)
│   ├── __main__.py         # was main.py (1245 LOC — R3 lo splitea en Fase 3)
│   ├── actions/  agent/  cli/  config/  core/
│   ├── domain/memory/      # was memory/*.py
│   ├── plugins/  server/  storage/  utils/
├── config/                 # data: .json (api_keys, mcp_servers, etc.)
├── data/                   # state: SQLite + iot_sensor_log.csv + conversations.json
├── tests/, scripts/, web/
```

**Movimientos clave:**
- 7 dirs Python top-level → `orion/` (actions, agent, core, server, storage, plugins, utils).
- `config/{__init__,theme,theme_tokens}.py` → `orion/config/` (los `.json` quedan en root `config/` como data).
- `memory/{__init__,config_manager,conversations,memory_manager,quick_notes}.py` → `orion/domain/memory/`.
- `memory/iot_sensor_log.csv` + `memory/conversations.json` → `data/`. Resto de `memory/` borrado (incluidos los `.bak.migrated` post-SQLite).
- `main.py` → `orion/__main__.py`. `run_debug.py` → `orion/cli/debug.py`.
- `setup.py` borrado (era pip-installer one-shot).
- `AUDIT_*.md` borrados (ya estaban en `.gitignore` como notes locales).

**Import rewrite:** 354 líneas en 104 archivos. Script one-shot
(`scripts/_rewrite_imports_oneshot.py`) hecho ad-hoc y borrado tras
aplicarse. 17 strings `patch("module.X")` en tests también actualizadas.

**Path adjustments críticos:**
- `orion/config/__init__.py` ahora usa `Path(__file__).parent.parent.parent` (3 niveles, antes eran 2) para que `BASE_DIR` siga apuntando al project root.
- `CORE_DIR = RESOURCES_DIR / "orion" / "core"`, `PLUGINS_DIR = RESOURCES_DIR / "orion" / "plugins"` para que prompt.txt y plugins se resuelvan post-rename.
- `MEMORY_DIR` queda como alias de `DATA_DIR` (back-compat para legacy callers).
- `actions/iot/sensor_log.py` y `sheets_sync.py` ahora usan `DATA_DIR / "iot_sensor_log.csv"`.

**Build/CI actualizados:**
- `pyproject.toml`: `packages.find.include = ["orion*"]`, `known-first-party = ["orion"]`, mypy overrides prefijo `orion.`, per-file-ignores `orion/__main__.py`.
- `.github/workflows/ci.yml`: paths de mypy.

**Side-effect:** pre-commit auto-normalizó CRLF→LF en ~10 archivos varios
(configs JSON, scripts) que tenían drift de line endings.
Quedó incluido en el mismo commit.

**Junio 2026 — Empaquetado eliminado:** Tauri (`src-tauri/`) + PyInstaller
(`packaging/orion_backend.spec`) + scripts de build (`scripts/build.sh`,
`scripts/build.ps1`) + outputs (`build/`, `dist/`) removidos del repo. Sin
.exe ni .msi. Orion ahora corre exclusivamente como `python -m orion` con
el frontend Vite servido por FastAPI desde `web/dist/`. Razón: el cache
ocupaba ~3 GB y el flujo desktop no se usaba.

**Sanity:** **333 tests passing** (mismo número que pre-refactor), ruff
ok, mypy ok, CI verde en los 8 jobs (run [27909820247](https://github.com/Zero0889/Orion-AI/actions/runs/27909820247)).

> Nota histórica: lo que esta sección decía antes ("ruff format baseline,
> B904, SIM105, exhaustive-deps") era cleanup de lint debt — útil pero
> NO era la Fase 2 del plan del audit. Ese trabajo está en el historial
> (commits previos a `21fda71`) y los warnings siguen apagados.

### ✅ Fase 3 — Modularización Python (cerrada, CI verde)

Los 5 sub-items del audit cerrados:

| Sub-item | Commit | Notas |
|---|---|---|
| **R4** — decoradores `@tool` + auto-discover | (anterior, era "3A") | `core/tools_bootstrap.py` 1209→170 LOC |
| **R3** — splittear `main.py` | `3310cb0` | 1245 LOC → 6 archivos (max 455) usando mixins |
| **R5** — `actions/` → `adapters/` por dominio | `fa72186` | 4 dominios: system / google / web / iot |
| **services/** entre routes y domain | `26959c0` | POC: 3 routes (notes, memory, conversations) + 5 helpers |
| **structlog + correlation-id** | `11f045c` + `ff1fc84` | Bridge stdlib + `corr_id` por request |

#### R3 — split `orion/__main__.py`
- `__main__.py`: 1245 → 24 LOC (thin entry `from .bootstrap import main`).
- `bootstrap.py` (170): UTF-8 fix + PATH + main() + uvicorn + spawn.
- `runtime.py` (455): `OrionLive(LiveSessionMixin, AudioMixin)`.
- `audio.py` (269): `AudioMixin` (send/listen/receive/play loops).
- `live_session.py` (375): `LiveSessionMixin` (config + handlers + watchdog).
- `_helpers.py` (94): helpers puros (`load_prompt`, `clean_transcript`).
- Patrón: cada mixin lee `self.<attr>` que setea `OrionLive.__init__`.

#### R5 — `actions/` → `adapters/` por dominio
- `orion/adapters/system/` — 16 archivos (host PC: files, processes, screen, dev tooling, GOG, electronics).
- `orion/adapters/google/` — 4 (classroom, drive, notebooklm, notifications/).
- `orion/adapters/web/` — 5 (browser, search, youtube, flights, weather).
- `orion/adapters/iot/` — subpaquete entero (devices/scenes/sensors/transports).
- `auto_discover_tools("orion.adapters")` walking recursivo (pkgutil.walk_packages) — descubre todo sin cambios al registry.

#### services/ POC
- `orion/services/{notes,memory,conversations}_service.py` + `_bus_publisher.py` helper compartido.
- Routes thin: parse Pydantic → `Depends(_service)` → call → map errors a `HTTPException`.
- Excepciones tipadas (`NoteNotFound`, `InvalidCategory`, etc.) — la route hace mapping 1:1 a HTTP codes.
- Las 10 routes pesadas restantes (iot/mcp/agent/skills/notebooklm/circuit/files/settings/integrations/notifications) siguen el patrón clásico — migrar incrementalmente cuando se toquen.

#### structlog + correlation-id
- `orion/core/correlation.py`: `ContextVar` `_correlation_id` (default `"-"`).
- `orion/core/logger.py` reescrito: `structlog.stdlib.BoundLogger` bridge — `log.info("event", k=v)` funciona, también `log.info("Hi %s", x)` printf classic.
- Processor chain: filter_by_level → positional formatter → `_add_correlation_id` → exc_info → `KeyValueRenderer`.
- `_SecretFilter` (Fase 1) sigue activo a nivel handler stdlib.
- Middleware en `server/app.py`: lee `X-Request-Id` inbound o genera UUID8, lo setea en el ContextVar, echo back en response header.
- Output format: `[orion.x] INFO: event='msg' corr_id='ab12' user='zahir'`.
- Para reconstruir un request: `grep corr_id=ab12cd34 logs/orion.log`.

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

### ✅ Fase 4 — Modularización frontend (cerrada)

| Sub-item | Estado |
|---|---|
| Romper MCPPanel/DeviceFormModal/AgentsPanel/IoTPanel a feature-folders | ✅ commits 822f524, ed8da18, 159b005, e78e8fd |
| R7 — generar `api/generated.ts` desde OpenAPI | ✅ (cubierto por Fase 3D) |
| Vitest + RTL — baseline de tests para los paneles | ✅ |
| TanStack Query — server-state fuera de Zustand | ✅ todos los paneles migrados, `rev.X` removido del store |
| widgets/eye/ + widgets/command-palette/ | ✅ ambos movidos a `web/src/widgets/` |

#### ✅ Vitest + RTL baseline
- Stack: `vitest ^2.1.9` + `jsdom ^25` + `@testing-library/react ^16` + `@testing-library/jest-dom ^6` + `@testing-library/user-event ^14`. Sin `globals: true` — los tests importan `describe/it/expect/vi` desde `vitest` explícitamente.
- Config: el bloque `test` vive en `web/vite.config.ts` (no archivo separado). `setupFiles: ["./src/test/setup.ts"]` registra los matchers de jest-dom + `cleanup()` manual en `afterEach` (sin `globals:true` RTL no auto-registra cleanup → tests acumulan DOM).
- Scripts: `npm test` (watch) y `npm run test:run` (one-shot, usado en CI).
- CI: nuevo step `Test (vitest)` en el job `web` entre `Format check` y `Build`. Corre en ambas Node 20/22.
- **Baseline actual:** 5 archivos de test, 44 tests, foco en helpers puros + componentes pequeños sin deps externas. NO hay tests todavía para los `index.tsx` top-level — esos requieren mockear `api/rest.ts` + `useOrionStore` + hooks custom (`useDeviceConfig`, `useSensorHistory`). Es trabajo de otra pasada.
- Archivos cubiertos: `DeviceFormModal/constants.test.ts` (slugify, kindFromDevice, isObj), `DeviceFormModal/controls.test.tsx` (NumInput clamp, QuickPick, CapChip, ReadOnlyBackendBadges), `AgentsPanel/types.test.ts` (agentIconTone, useProviderLabel, sessions persist + truncate a 80 msg), `MCPPanel/StarBadge.test.tsx` (k-format + snapshot), `IoTPanel/ExportMenu.test.tsx` (open/close + click-outside + hrefs).
- **Gotcha registrado:** los snapshots viven en `src/**/__snapshots__/*.snap`. NO están en `.prettierignore` ni `.gitignore` porque el glob de prettier solo cubre `.ts/.tsx/.css/.json/.md`. Quedan versionados como parte del repo.
- **Inputs controlados:** `userEvent.type()` no funciona como esperado en componentes controlados con `value` prop estático en el test — los keystrokes se acumulan sobre el value original porque el parent del test no re-renderea. Para testear lógica de clamp/validación usar `fireEvent.change(input, { target: { value: "X" } })` directo. Solo usar `user.type` cuando hay un harness con state real arriba.

#### ✅ TanStack Query (todos los paneles migrados)
**Infraestructura:**
- `@tanstack/react-query@^5.62.7` en deps. Su propio chunk Vite (`vendor-tanstack`, ~14kB gzip).
- `web/src/query/client.ts` — `QueryClient` singleton con defaults razonados (staleTime 30s, refetchOnWindowFocus false, retry 1). Razonamiento en el archivo.
- `web/src/query/keys.ts` — registro central de `QUERY_KEYS` (notes, memory, conversations, conversation(id), settingsTheme, notifications, notificationsList(unread), notificationsStatus, iot.{all,devices,scenes,sensors,paused}, orchestra, mcpServers). Mantener TODAS las keys acá: el bridge WS y los `useQuery` consumen el mismo objeto → renombre seguro.
- `main.tsx` monta `<QueryClientProvider client={queryClient}>` arriba de `<App />`.
- **Bridge WS → invalidación** en `stores/orion.ts` (`applyEvent`): cada `case` que afecta server-state cacheado llama `queryClient.invalidateQueries({ queryKey })` con la key correspondiente. Los paneles refetchean automáticamente.
- `web/src/test/renderWithQuery.tsx` — helper que envuelve un componente en un `QueryClientProvider` con un client fresco por test (retry false, staleTime 0).

**Paneles migrados:**
| Panel | Notas |
|---|---|
| `NotesPanel` | 1 query (`notes`). Sin store global. |
| `MemoryPanel` | 1 query (`memory`). |
| `HistoryPanel` | 2 queries — `conversations` (lista) + `conversation(id)` (detalle, `enabled:!!active`). Prefix-match de invalidación: invalidar `["conversations"]` pega también al detalle. `setDetail(null)` se eliminó — `enabled` desactiva la query. |
| `SettingsPanel` + `App.tsx` | Comparten cache de `settingsTheme` → un solo fetch por sesión. App lee el data y aplica `data-theme` al `<html>` cuando cambia. |
| `NotificationsPanel` | 2 queries (lista parametrizada por `unread` + status). Mutations (pollNow/markAllRead/authorize) invalidan `["notifications"]` (prefix). |
| `IoTPanel` | 4 queries (`iot.devices/scenes/sensors/paused`). `iotSensors` live sigue en Zustand (WS-state). togglePause y onSaved invalidan `iot.all`. |
| `AgentsPanel` | 2 queries (`orchestra` + `providers` con staleTime 5min). `mutationError` separado del `queryError` para que el dismiss del banner no afecte queries. |
| `MCPPanel` | 1 query (`mcpServers`). Sin bridge WS (no hay eventos MCP) — invalidación solo desde mutations. Toggle enabled optimista via `setQueryData`. |

**Patrón de migración:**
```ts
// Antes:
const rev = useOrionStore((s) => s.rev.notes);
const [notes, setNotes] = useState<NoteApi[]>([]);
useEffect(() => {
  api.listNotes().then(setNotes).catch((e) => toast.error(String(e)));
}, [rev]);

// Después:
const { data: notes = [], error } = useQuery({
  queryKey: QUERY_KEYS.notes,
  queryFn: () => api.listNotes(),
});
// Toast UNA vez por error nuevo via useRef + useEffect (ver NotesPanel).
```

**Gotchas registrados:**
- **Errors de query vs mutation:** los paneles con banner dismissable (Agents, IoT, MCP, Notifications, Settings) usan `mutationError` local + `queryError` derivado de la query. El render hace `pickError ?? (queryError ? String(queryError) : null)`. El dismiss solo limpia el local.
- **Detail queries:** usar `enabled: !!id` y dejar la cache. NO necesitamos limpiar `data` manualmente cuando `id` cambia a null — solo verificar `id` antes de renderear el detalle.
- **`useProviderLabel` y nombres con `use`-prefix:** aunque empiecen con `use`, NO son hooks (son funciones puras en `AgentsPanel/types.ts`). El compilador no se queja porque no llaman hooks adentro — pero conviene renombrarlas en algún futuro PR para no confundir lectores.
- **Optimistic updates:** usar `queryClient.setQueryData(key, updater)` antes del API call, luego `invalidateQueries(key)` después. Si el call falla, la invalidación refetchea y revierte (ver MCPPanel.handleToggleEnabled).
- **Prefix-match:** TanStack Query v5 invalida por defecto con prefix-match — `invalidateQueries({ queryKey: ["conversations"] })` pega a `["conversations"]` Y a `["conversations", id]`. Usar esto en vez de invalidar key por key.

**Test pattern** (ver `NotesPanel.test.tsx`): mockear `@/api/rest` y `@/stores/toast` con `vi.mock` ANTES del import del componente, usar `renderWithQuery`, asertar contenido + estado vacío + que no crashee al rechazar.

#### ✅ widgets/ — Eye y CommandPalette
Nueva capa estructural `web/src/widgets/` para features cohesivas (vs.
`components/` para piezas simples reutilizables). Cada widget es una
carpeta con `index.ts(x)` que expone la API pública via barrel.

```
web/src/widgets/
├── eye/
│   ├── index.ts            # barrel: BackgroundEye, EyeCore, EyeState, EyePalette,
│   │                       # useEyeState, DerivedEyeState, useEventPulses
│   ├── BackgroundEye.tsx   # wrapper de fondo ambiental
│   ├── EyeCore.tsx         # renderer SVG/canvas (459 LOC)
│   ├── useEyeState.ts      # deriva idle/listening/thinking/speaking del store
│   ├── useEventPulses.ts   # bridge mundo→pulsos (sensores/notifs/tools)
│   └── pulseStore.ts       # zustand interno (privado, NO re-exportado)
└── command-palette/
    └── index.tsx           # 432 LOC: render + useCommandPalette store + catálogos
```

**Migración hecha con `git mv`** para preservar blame de los 6 archivos.
Imports actualizados en 5 consumidores: `App.tsx`, `TopBar.tsx`,
`OrbHUD.tsx`, `ChatPanel.tsx`, `components/BackgroundEye` (interno al widget).

**Decisión: NO splitear CommandPalette internamente.** Tiene 432 LOC
pero el componente, sus catálogos (VIEW_ACTIONS/THEMES) y el store
inline (`useCommandPalette`) están tightly-coupled — splitearlo daría
3 archivos chicos sin ganancia real. Si supera ~600 LOC en el futuro,
re-evaluar (extraer `actions.ts` + `store.ts`).

**`pulseStore` queda privado a propósito.** Solo `EyeCore` y
`useEventPulses` lo consumen (ambos adentro del widget). Mantenerlo
fuera del barrel evita que consumidores externos disparen pulsos
saltándose la política de filtrado de `useEventPulses` (reglas: pulso
≠ tick, solo eventos significativos).

#### ✅ Romper god-files frontend
Los 4 componentes >900 LOC del audit migrados a feature-folders. Ningún
archivo nuevo > 1019 LOC, la mayoría < 400. API pública intacta —
`import { X } from "@/components/X"` sigue resolviendo a `index.tsx`
porque Vite/TS lo hacen automático.

| God-file antes | Commit | Después | Archivos en la carpeta |
|---|---|---|---|
| `MCPPanel.tsx` (1452 LOC) | `822f524` | 7 archivos, max 379 | `index.tsx` (shell+TabButton) · `InstalledTab.tsx` (ServerCard+StatusPill) · `ExploreTab.tsx` (RegistryRow+isOfficial) · `CuratedTab.tsx` (RecipeCard+RecipeInstallModal) · `ServerFormModal.tsx` · `StarBadge.tsx` (shared) · `types.ts` |
| `DeviceFormModal.tsx` (1183 LOC) | `ed8da18` | 3 archivos, max 1019 | `index.tsx` (forma cohesiva con ~40 useState) · `constants.ts` (catálogos + helpers puros) · `controls.tsx` (NumInput+QuickPick+CapChip+ReadOnlyBackendBadges) |
| `IoTPanel.tsx` (1032 LOC) | `159b005` | 4 archivos, max 356 | `index.tsx` (shell + 3 secciones + Subhead) · `DeviceCard.tsx` (memo'd + SensorReadout + RangeBar + Sparkline + QUICK_COLORS) · `SheetsPanel.tsx` (sync continuo + IntervalControl + formatAge) · `ExportMenu.tsx` (dropdown CSV/XLSX) |
| `AgentsPanel.tsx` (1150 LOC) | `e78e8fd` | 5 archivos, max 373 | `index.tsx` (state cross-vista + LoadingGrid) · `types.ts` (ChatMsg/ChatSession + agentIconTone + session persistence) · `AgentGrid.tsx` (grid + AgentCard) · `AgentChatView.tsx` (chat con sidebar) · `AgentEditorModal.tsx` (CRUD agente + inputCls) |

**Nota sobre `DeviceFormModal`** — el split es mucho más modesto (3
archivos vs 4-7 de los otros). Razón: es UN solo formulario con ~40
useState compartidos entre secciones. Romperlo por sección requeriría
prop-drilling masivo (15+ props por hijo) o un Context — más complejidad
accidental que beneficio. Solo se extrajeron los catálogos estáticos y
los controles UI puros (NumInput etc.).

**Validación visual obligatoria tras cualquier cambio futuro a estos
paneles:** `npm run dev` + browser + clickear cada tab/sección. `tsc +
lint + build` pueden estar verdes con bugs sutiles de runtime (stale
closures, state que no se preserva al cambiar de vista, hook order, props
mal pasados).

### 🟡 Pendientes acumulados
Ver lista consolidada en **§15 Pendientes acumulados (próximas sesiones)**
al final del documento. Incluye los pendientes históricos (validación
visual, `backup-pre-filter-repo`, migrar interfaces a `Schemas`) + los
nuevos de Fases 5/6/7 (flashar ESP32, fases 2/3 del supergrupo, push de
commits acumulados, decisión sobre `_design_brief/`).

---

## 3. Mapa del repo (qué archivo hace qué)

```
O.R.I.O.N/
├── pyproject.toml                # Config de ruff, mypy, pytest. packages.find = ["orion*"] (Fase 2).
├── .pre-commit-config.yaml       # Hooks: ruff, gitleaks, prettier+eslint locales.
├── .github/workflows/ci.yml      # 7 jobs (ver §4 abajo).
├── .gitleaks.toml                # Allowlist mínima — NO whitelistear patrones.
├── .gitattributes                # `* text=auto eol=lf` — fuerza LF en checkouts.
│
├── orion/                        # ← Paquete principal (Fase 2). Entry: `python -m orion`.
│   ├── __init__.py
│   ├── __main__.py               # was main.py. 24 LOC thin entry (Fase 3 R3).
│   ├── bootstrap.py              # main() + uvicorn build + _check_port_free (Fase 6).
│   ├── runtime.py                # OrionLive(LiveSessionMixin, AudioMixin).
│   ├── audio.py + live_session.py + _helpers.py  # Mixins de runtime (Fase 3 R3).
│   ├── actions/live_stubs.py     # Stubs Live-only (agent_task, shutdown, quick_note, save_memory).
│   ├── adapters/                 # Tools de cada dominio (Fase 3 R5).
│   │   ├── system/               # 16 archivos — host PC (files, processes, screen, dev tooling, etc.).
│   │   ├── google/
│   │   │   ├── classroom.py      # google-auth directo. token.json en tools/classroom/.
│   │   │   ├── notebooklm_research.py
│   │   │   ├── google_drive.py
│   │   │   └── notifications/
│   │   │       ├── gmail.py      # google-auth directo (Fase 7). token.json en tools/gmail/.
│   │   │       ├── classroom.py  # Idem patrón.
│   │   │       └── poller.py     # Loop genérico; tiene adapters Gmail+Classroom.
│   │   ├── web/                  # 5 (browser, search, youtube, flights, weather).
│   │   ├── iot/                  # devices/scenes/sensors/transports + sheets_sync.py (usa gog).
│   │   │   ├── access_control.py # Fase 5: tablas users + events + VIEW daily.
│   │   │   └── ...
│   │   └── messaging/
│   │       └── telegram.py       # TelegramClient + TelegramConfig + TelegramGroupConfig (Fase 6).
│   ├── agent/                    # Planner + executor + task queue + orchestra.
│   ├── cli/debug.py              # was run_debug.py.
│   ├── config/                   # Schema loaders + helpers (sin .json — esos en root config/).
│   │   ├── __init__.py           # BASE_DIR, MEMORY_PATH, SQLITE_DB_PATH, DATA_DIR, CONFIG_DIR.
│   │   └── theme*.py
│   ├── core/
│   │   ├── tool_registry.py      # @tool, @live_only_tool, auto_discover_tools (Fase 3A).
│   │   ├── tools_bootstrap.py    # ~170 LOC — auto_discover_tools("orion.adapters").
│   │   ├── logger.py             # `_SecretFilter` enmascara keys (Fase 1).
│   │   ├── correlation.py        # ContextVar corr_id (Fase 3).
│   │   ├── client_context.py     # set_last_client(ClientInfo) — usado por telegram_bridge.
│   │   ├── llm/*.py              # Provider abstraction (gemini, openai-compat, ollama, ollama_cloud).
│   │   ├── chat_brain.py         # is_live_brain() + invocación del cerebro configurable.
│   │   └── mcp_*.py              # MCP client + recipes.
│   ├── domain/memory/            # quick_notes / conversations / memory_manager — todos SQLite (Fase 3B).
│   ├── plugins/                  # Plugin system (base + example_plugin).
│   ├── server/
│   │   ├── app.py                # FastAPI app builder + middleware install.
│   │   ├── bootstrap.py
│   │   ├── event_bus.py          # OrionEventBus (in-proc + WS broadcast).
│   │   ├── sharing.py            # Middleware IP filter + bypass autenticado (Fase 5).
│   │   ├── access_auth.py        # Shared-secret + is_authed_request (Fase 5).
│   │   ├── telegram_bridge.py    # Long-poll inbound + outbound a chat/topics (Fase 6).
│   │   ├── ws.py                 # WS drain loop + heartbeat.
│   │   ├── telemetry.py          # Telemetry broadcaster.
│   │   └── routes/               # /api/* endpoints.
│   │       ├── access.py         # Fase 5: CRUD users + POST event + reports + export.
│   │       ├── telegram.py       # Fase 6: status + manage del bridge.
│   │       ├── notifications.py  # poller + mark-read + autorización Classroom.
│   │       └── *.py              # Resto (mcp, agent, skills, iot, memory, ...).
│   ├── storage/sqlite_db.py      # get_connection() singleton (Fase 3B).
│   └── utils/cache.py            # ttl_cache decorator.
│
├── arduino/                      # Sketches ESP32 (Arduino IDE).
│   ├── dht_bh1750_sensores/      # IoT sensores DHT22 + BH1750.
│   ├── access_control_fingerprint/  # Fase 5: huella AS608 → POST /api/access/event.
│   ├── focos_lm35/, gps_neo6m_bridge/, wifi_scanner/  # Otros.
│   └── *.ino
│
├── config/                       # Solo DATA: .json. Sin código (Fase 2).
│   ├── *.example.json            # Templates versionados.
│   ├── api_keys.json             # Secreto — gitignored.
│   ├── credentials.json          # Secreto — gitignored.
│   ├── telegram.json             # bot_token + chat_id + group{chat_id,topics} — gitignored.
│   └── access.json               # shared_secret para ESP32 — gitignored.
│
├── data/                         # State runtime (gitignored).
│   ├── orion.sqlite              # Todas las tablas (Fase 3B + Fase 5).
│   ├── iot_sensor_log.csv        # Sensor datalog.
│   └── conversations.json        # Legacy pre-SQLite, queda como export.
│
├── scripts/
│   ├── dump_openapi.py           # → web/src/api/openapi.json (Fase 3D).
│   └── audit_mobile.py           # Playwright audit del mobile 412×915 (Fase 6).
│
├── tools/                        # Binarios auxiliares + tokens OAuth (gitignored).
│   ├── gog/                      # CLI gog (auto-instalado por core.cli_installer).
│   ├── classroom/                # client_secret.json + token.json (google-auth).
│   └── gmail/                    # token.json (google-auth, Fase 7).
│
├── tests/
│   ├── conftest.py               # Fixture autouse: SQLite tmp + mock sounddevice + extend SAFE_ROOTS + access_control reset (Fase 5).
│   ├── test_security_hardening.py        # 22 tests (Fase 1).
│   ├── test_logger_secret_filter.py      # 9 tests (Fase 1).
│   ├── test_notification_store_sqlite.py # 15 tests (Fase 3B).
│   ├── test_access_event_auth.py         # 8 tests del bypass autenticado (Fase 5).
│   ├── test_telegram_topic_routing.py    # 15 tests del routing por topic (Fase 6).
│   └── test_*.py                 # 405 total al cierre de Fase 7.
│
└── web/
    ├── package.json              # scripts: dev, build, lint, format, typecheck, test/test:run, gen:api, gen:api:check.
    ├── eslint.config.js          # ESLint flat config v9.
    ├── .prettierrc.json          # printWidth 100, single line endings (lf), trailing commas (all).
    ├── .prettierignore           # Excluye openapi.json (generado).
    ├── public/
    │   ├── manifest.webmanifest  # PWA mobile (Fase 6).
    │   └── sw.js                 # Service worker básico.
    ├── scripts/check-api-types-fresh.mjs  # CI drift detection (Fase 3D).
    └── src/
        ├── api/
        │   ├── rest.ts           # Cliente HTTP. Expone `Schemas`, `ApiPaths`. Incluye `access*` helpers.
        │   ├── ws.ts             # WS client (auto-reconnect).
        │   ├── openapi.json      # Generado — NO editar a mano.
        │   └── generated.ts      # 4538+ LOC de tipos TS — NO editar.
        ├── query/
        │   ├── client.ts         # QueryClient singleton.
        │   └── keys.ts           # QUERY_KEYS central. Incluye `access.{users,events,daily,all}` (Fase 5).
        ├── components/           # Piezas del shell. MCPPanel/, DeviceFormModal/, IoTPanel/, AgentsPanel/, AccessPanel/ son carpetas con index.tsx + subarchivos.
        │   └── AccessPanel/      # Fase 5: index.tsx + DailyReportTab + EventsTab + UsersTab.
        ├── widgets/
        │   ├── eye/              # BackgroundEye + EyeCore + hooks + pulse store.
        │   └── command-palette/  # Cmd+K + useCommandPalette store.
        ├── stores/orion.ts       # Zustand. Bridge WS→invalidateQueries en applyEvent (incluye access.event y access.user_changed).
        ├── hooks/
        │   ├── useIsMobile.ts    # Hook responsive (Fase 6).
        │   └── useOrionSocket.ts
        ├── audio/audioPlayer.ts  # Audio mobile (Fase 6).
        ├── test/
        │   ├── setup.ts          # Vitest setup global.
        │   └── renderWithQuery.tsx
        ├── types.ts
        └── App.tsx               # Routea AccessPanel cuando view==="access".
```

---

## 4. CI — qué corre y qué reporta

El push a `main` dispara `.github/workflows/ci.yml` con 7 jobs:

| Job | Cuándo se enoja |
|---|---|
| **Python (3.11 / ubuntu-latest)** | ruff lint/format, mypy strict en módulos críticos, pytest 405 tests |
| **Python (3.12 / ubuntu-latest)** | idem en Python 3.12 |
| **Python (3.11 / windows-latest)** | idem cross-platform (captura bugs de `os.replace` cross-volume, etc.) |
| **Python (3.12 / windows-latest)** | idem |
| **Web (Node 20)** | tsc, eslint `--max-warnings=0`, prettier `--check`, vitest (71 tests), vite build |
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
| Telegram tira `HTTP 409 Conflict: terminated by other getUpdates request` cada 5s | 2 instancias de Orion polleando el mismo bot | `_check_port_free` en `bootstrap.py` aborta el arranque si :8765 ocupado (Fase 6) |
| `gog gmail search` falla con "OAuth client credentials missing" o "No auth for gmail" desde Orion pero funciona desde terminal | Bug ambiguo de propagación de env vars en subprocess en Windows con file-keyring backend de gog | Reescribir adapter en `google-auth` directo (`gmail.py` Fase 7). Mismo patrón sirve para Drive/Calendar si pasa lo mismo. |
| ESP32 en LAN recibe 403 al postear a `/api/access/event` | `SharingMiddleware` solo permite loopback + Tailscale | Header `X-Orion-Access-Token` con el secret de `config/access.json` hace bypass autenticado (Fase 5). |
| Drawer mobile no recibe clicks; backdrop intercepta todo | Stacking context: `<aside z-40>` adentro de wrapper `z-10`, backdrop `z-30` sibling del wrapper → backdrop arriba del aside | Sidebar mobile sale del wrapper como sibling fixed; `renderSidebarContents()` reutilizable (Fase 6). |
| Texto del SectionHeader se rompe letra-por-letra en mobile | Título flex con acción a la derecha → solo ~100px para el title | Stack vertical (`flex-col sm:flex-row`) + padding reducido en mobile (Fase 6). |
| Tests SQLite del access_control fallan con "no such table: access_events" | `_initialized = True` cacheado entre tests porque la fixture autouse reapunta el DB path pero no resetea el flag | `_reset_for_tests()` en `access_control.py` + registrado en `conftest.py::_isolated_sqlite_db` (Fase 5). |

---

## 7. Cosas que el user me dijo y conviene recordar

- Quiere usar Orion desde **celular/reloj/tablet** eventualmente, no solo PC. Por eso R1 y R2 (sacar `exec()` y `shell=True` con input LLM) fueron innegociables.
- Acepta el trade-off "opción A" cuando la "opción B surgical" no vale el costo (ej: commitear format baseline mezclado con lógica en vez de hacer la cirugía git de separarlos).
- Quiere **honestidad sobre alcance**: prefiere "esto es trabajo de otra sesión" antes que apurar refactors riesgosos.
- Pide validación visual para cambios de UI. `npm run dev` + browser real, los checks de tsc/lint/build pueden estar verdes con bugs sutiles de runtime.
- Las **transcripciones árabes/persas** en la voz son cosa de Gemini Live STT (no del código), no perder tiempo intentando arreglarlas en el código.
- **Caso de uso STEM:** Orion es asistente personal **+ sistema de seguridad doméstica** (huella ESP32 + Telegram). Para informes técnicos enfocarse en el ángulo de seguridad porque tiene métricas medibles (latencia ESP32→Telegram, tasa AS608, etc.). El resto del sistema queda como "plataforma donde se monta el caso".
- **Multi-recipient en Telegram:** preferencia validada por **supergrupo con topics** sobre lista global de chat_ids. Más flexible (agregar/sacar gente del grupo sin código) y permite separar tipos de notif (Acceso, Estado, Comandos, Chat) en topics distintos.
- **Privacidad:** **el `client_secret` de Desktop apps de Google es semi-público por diseño** (va embebido en binarios distribuidos). El user lo entendió y aceptó pegarlo en chat para configurarlo. El verdadero secreto es el refresh token, que vive en disco (`tools/<service>/token.json`).
- **Empaquetado:** decisión deliberada de NO mantener Tauri/PyInstaller. Si en algún futuro hay que recuperarlo, está en el git history pre-`4146ac3`.
- **`orion.bat` NO debe tener credenciales hardcoded.** Si algún día el bypass de google-auth (Fase 7) no alcanza y hay que volver a env vars, usar `config/<x>.env` gitignored — no editar `orion.bat`.

---

## 8. Para empezar la próxima sesión

Comandos para verificar que todo está sano:

```bash
# Backend
python -m pytest -q --no-header                # esperar 405 passing
python -m ruff check .                         # All checks passed
python -m ruff format --check .                # already formatted
python -m mypy --follow-imports=silent orion/core/logger.py orion/core/tool_registry.py orion/core/llm/base.py orion/server/app.py orion/server/event_bus.py orion/server/sharing.py orion/server/telemetry.py

# Frontend
cd web
npm run typecheck                              # ok
npm run lint                                   # 0 errors
npm run format:check                           # All matched files use Prettier code style!
npm run test:run                               # 71 tests passing en 9 archivos
npm run gen:api:check                          # API types están al día
npm run build                                  # built in ~10s

# CI
gh run list --limit 3                          # último commit en verde
```

Si todo verde: el refactor mayor del audit está **completo** (Fases 1, 2,
3A, 3B, 3D, 4) + **Fase 5** (acceso por huella) + **Fase 6** (Telegram
topics + bootstrap port-check + mobile UX) + **Fase 7** (Gmail vía
google-auth). Las próximas sesiones se ocupan de features nuevas o lo
que el user pida. Si CI rojo: ver §4.

### Checklist rápido al abrir la próxima sesión

1. `git log --oneline -10` — ver últimos commits para contexto.
2. `git status -s` — ver si hay cambios sin commitear (puede haber un
   `_design_brief/` untracked desde hace tiempo).
3. Si hay commits sin push: confirmar con user si quiere `git push origin main`.
4. Si el user pide algo nuevo:
   - Si toca **Gmail/Google**: usar el patrón `google-auth` directo (Fase 7), NO `gog`.
   - Si toca **un dispositivo nuevo (LAN)**: usar el patrón `shared-secret` (Fase 5).
   - Si toca **mobile**: re-correr `scripts/audit_mobile.py` después de los cambios.
   - Si toca **Telegram**: respetar el routing por topic (no hardcodear `default_chat_id`).

---

## 9. Patrón establecido para splittear componentes grandes

De los 4 god-files migrados en Fase 4 quedaron 2 patrones distintos según
la naturaleza del componente. **Reusarlos cuando algún componente nuevo
crezca a >900 LOC:**

### Patrón A — Componente con sub-vistas independientes (MCPPanel, IoTPanel, AgentsPanel)
Cuando el componente tiene tabs/secciones que comparten poco state:
- `index.tsx` — shell, state global cross-vista, routing entre vistas
- `XTab.tsx` (o equivalente) — una por sección, recibe handlers + state via props
- `types.ts` — tipos compartidos
- `Shared.tsx` — micro-componentes usados por >1 archivo (StarBadge en MCP)
- Carpeta queda en 4-7 archivos, ninguno >400 LOC.

### Patrón B — Componente con state ultra-acoplado (DeviceFormModal)
Cuando todas las "secciones" leen/escriben el mismo conjunto de useState
(formularios complejos, modales con muchos campos correlacionados):
- `index.tsx` — TODO el componente, sigue grande pero solo (sin más mezcla)
- `constants.ts` — catálogos estáticos + helpers puros (sin React)
- `controls.tsx` — controles UI puros sin lógica de negocio (inputs, chips, badges)
- Carpeta queda en 3 archivos. El `index` sigue grande pero ya no mezcla
  declaración de catálogos con lógica de formulario.

**Anti-patrón:** romper Patrón B en sub-componentes por sección requiere
prop-drilling de 15+ props por hijo o un Context. Ambas opciones son
complejidad accidental que no paga.

---

## 10. Fase 5 — Sistema de control de acceso por huella (Junio 2026)

Subsistema completo de **biometría doméstica**: ESP32 con sensor AS608 lee
huellas → POST a Orion → SQLite guarda evento → Telegram notifica al
topic correcto del supergrupo. Cubre el caso de uso "asistente personal
+ seguridad" que el user quiere para presentación STEM.

### Pipeline end-to-end

```
┌─────────────────┐    HTTP POST   ┌──────────────────────────────┐
│  ESP32 + AS608  │ ─────────────► │ POST /api/access/event        │
│  (LAN, no       │   header:      │  · SharingMiddleware bypass   │
│   Tailscale)    │   X-Orion-     │    si header válido           │
│                 │   Access-Token │  · Pydantic body validation   │
└─────────────────┘                └──────────┬───────────────────┘
                                              │
                       ┌──────────────────────┴────────────────────┐
                       │                                            │
                ┌──────▼───────┐                          ┌────────▼──────┐
                │ SQLite:      │                          │ Telegram      │
                │  access_     │                          │  bridge       │
                │   users      │                          │  · resolve_   │
                │  access_     │                          │    topic(     │
                │   events     │                          │     "access") │
                │  VIEW        │                          │  · message_   │
                │   access_    │                          │    thread_id  │
                │   daily      │                          │  · fallback a │
                └──────┬───────┘                          │    default_   │
                       │                                  │    chat_id    │
                       ▼                                  └───────────────┘
              ┌────────────────┐
              │ event_bus      │
              │  publish       │
              │  "access.event"│
              └────────┬───────┘
                       │
                  WS → frontend
                       │
              ┌────────▼───────┐
              │ AccessPanel:   │
              │  invalidación  │
              │  TanStack      │
              │  Query keys    │
              └────────────────┘
```

### Backend — commit `637bbea feat(access)`

**Adapter:** `orion/adapters/iot/access_control.py`
- Tablas SQLite (WAL, mismo singleton de Fase 3B):
  - `access_users (id, fingerprint_id UNIQUE, name, phone, active, created)`
  - `access_events (id, fingerprint_id, event_type, esp_id, confidence, timestamp)`
  - `VIEW access_daily` — agrupa GRANTED por usuario+fecha, calcula `entrada`
    (MIN timestamp), `salida` (MAX timestamp), `tiempo_minutos` (delta).
    Inferencia: primer GRANTED del día = entrada, último = salida. NO usamos
    columna `tipo` explícita — más robusto que pedirle estado al ESP32.
- API pública: `add_user`, `update_user`, `delete_user`, `list_users`,
  `record_event`, `list_events`, `count_events`, `daily_report`.
- DTOs frozen + `to_dict()` para serializar a JSON.
- `_reset_for_tests()` registrado en `conftest.py` para resetear el flag
  `_initialized` entre tests (igual patrón que los demás stores SQLite).

**Routes:** `orion/server/routes/access.py`
- CRUD `/api/access/users` — Pydantic models, errores tipados.
- `POST /api/access/event` — endpoint del ESP32. Llama a `record_event`,
  publica `access.event` al bus, dispara `_maybe_notify_telegram(ev)`.
- `GET /api/access/events` — listado paginado con filtros (`fingerprint_id`,
  `since`, `event_type`).
- `GET /api/access/daily?since=YYYY-MM-DD` — reporte agrupado.
- `GET /api/access/export.{csv,xlsx}` — descarga del reporte diario.
- `_maybe_notify_telegram(ev)` rutea:
  1. Si `cfg.resolve_topic("access")` devuelve `(chat_id, thread_id)` → topic.
  2. Sino fallback a `cfg.default_chat_id` (chat privado).

**Shared-secret auth:** `orion/server/access_auth.py`
- `config/access.json` (gitignored) contiene `{"shared_secret": "<32 bytes url-safe>"}`.
- Helper `is_authed_request(scope)` chequea: POST + path en `AUTHED_PATHS` +
  header `X-Orion-Access-Token` matches secret (comparación
  `hmac.compare_digest` para constant-time).
- `orion/server/sharing.py::SharingMiddleware` hace bypass al filtro de IP
  **solo** si `is_authed_request` devuelve True. Resto del backend sigue
  protegido por loopback + Tailscale.
- 8 tests en `tests/test_access_event_auth.py` cubren matriz completa
  (loopback OK, LAN sin/con/bad header, GET no bypassea, etc.).

### Frontend — commit `637bbea` (mismo)

**Panel:** `web/src/components/AccessPanel/`
- `index.tsx` — shell con 3 tabs + 3 queries TanStack + invalidación WS.
- `DailyReportTab.tsx` — la "tabla excel" (mobile cards, desktop table).
- `EventsTab.tsx` — registros crudos paginados.
- `UsersTab.tsx` — CRUD con `UserFormModal` (validación slot 0-127).
- Exporta hooks compartidos: `useCreateUser`, `useUpdateUser`, `useDeleteUser`.

**Bridge WS:** `web/src/stores/orion.ts::applyEvent` mapea
`access.event` y `access.user_changed` → `invalidateQueries(QUERY_KEYS.access.all)`.

**Sidebar entry:** `web/src/components/Sidebar.tsx` agregó
`{ id: "access", label: "Acceso", icon: "shield" }` en la sección
"Sistema". `App.tsx` lo routea con `<AccessPanel />` lazy-loaded.

**API helpers:** `web/src/api/rest.ts::api.access*` (createUser, updateUser,
deleteUser, listEvents, daily) + tipos en `web/src/api/generated.ts`.

### Hardware — `arduino/access_control_fingerprint/`

Sketch ESP32 (Arduino IDE) que:
- Lee huella vía `Adafruit_Fingerprint` por Serial2.
- POST JSON a `ORION_URL` con header `X-Orion-Access-Token`.
- LEDs verde/rojo + buzzer + relé.
- Reconexión WiFi automática + debounce de 1.5s.

El sketch tiene placeholders `WIFI_SSID`, `WIFI_PASS`, `ORION_URL`,
`ACCESS_TOKEN` que el user reemplaza antes de flashear.

### Tests

- `tests/test_access_event_auth.py` — 8 tests del bypass autenticado.
- `tests/test_telegram_topic_routing.py` — 15 tests del routing por topic
  (`resolve_topic`, `send_message(message_thread_id=...)`, integración con
  `_maybe_notify_telegram`).
- Total backend: **405 tests passing** (333 históricos + 23 nuevos
  access/telegram + 49 acumulados de sesiones intermedias).

---

## 11. Fase 6 — Telegram supergroup + topics + bootstrap fixes (Junio 2026)

### Telegram supergroup + topics — included en commit `637bbea`

**Antes:** todas las notifs caían al chat privado del user (`default_chat_id`).

**Ahora:** soporte para supergrupos con **forum topics** habilitados:
- `config/telegram.json` extendido con bloque opcional `group`:
  ```json
  {
    "group": {
      "chat_id": "-1004474820134",
      "topics": {
        "access": 4,
        "commands": 2,
        "status": 5,
        "chat": 11
      }
    }
  }
  ```
- `TelegramConfig.resolve_topic("access")` devuelve `(chat_id, thread_id)`
  si está mapeado, `None` si no.
- `TelegramClient.send_message(..., message_thread_id=N)` propaga al payload.
- `_maybe_notify_telegram` en `routes/access.py` rutea al topic; si no hay
  group/topic configurado, fallback al `default_chat_id` (back-compat).

**Setup en Telegram (manual por el user):** crear supergrupo →
habilitar Topics en settings → crear topics → agregar bot como admin →
mandar `/start@<bot>` en cada topic → el bridge loguea
`chat_id=X thread_id=Y text=...` que permite mapear nombre→thread_id
manualmente y escribir a config.

**Bridge update:** `orion/server/telegram_bridge.py::_handle_inbound` ahora
acepta `thread_id` y lo loguea junto al `chat_id`. `TelegramUpdate`
dataclass agregó campo `message_thread_id: int | None = None`.

### Bootstrap port-check — commit `513724a feat(bootstrap)`

**Síntoma original:** si el user arranca `orion.bat` 2 veces (o queda un
proceso huérfano), Telegram tira `HTTP 409 Conflict: terminated by
other getUpdates request` cada 5s en bucle. Spam horrible en los logs.

**Fix:** `_check_port_free(host, port)` en `orion/bootstrap.py`. Antes
de instanciar uvicorn, intenta `bind()` a 127.0.0.1:8765 con
`SO_REUSEADDR`. Si falla con `OSError`, imprime mensaje claro:
```
❌  Puerto 8765 ya está en uso.
    Probablemente hay otra instancia de Orion corriendo (o un
    proceso python.exe huérfano de una sesión anterior).
    Soluciones:
      · Cerrá la otra terminal de Orion (Ctrl+C).
      · O matá todos los python: taskkill /F /IM python.exe
      · Después volvé a correr orion.bat.
```
Y `SystemExit(1)`. Previene horas de debugging por instancia duplicada.

### Mobile UX audit — commit `0121f27 feat(mobile)`

Audit completo del viewport 412×915 (Pixel 7) con `scripts/audit_mobile.py`
(Playwright). 14 paneles auditados, 5 bugs reales encontrados + fixados:

| Bug | Fix |
|---|---|
| Backdrop del drawer mobile interceptaba clicks del sidebar | Sidebar sale del wrapper como sibling `<aside fixed z-40>`. Backdrop arriba como sibling. |
| SectionHeader rompía texto letra-por-letra (1-2 chars/línea) por título flex con acción a la derecha | Stack vertical en mobile (`flex-col` → `sm:flex-row`). |
| MemoryPanel composer (key + value + Guardar) en una row → "Guardar" empujado fuera del viewport | Mobile stacked: key full-width arriba, value + button lado a lado abajo. |
| HistoryPanel detail panel asomaba al lado derecho sin selección | Grid 1-columna en mobile; lista oculta cuando hay activo, detail con botón "Volver". |
| DiagnosticsPanel poll-rate buttons (100/200/500/1000) desbordaban | `flex-wrap` + header del log stack. |
| MCPPanel tabs cortados + badge "INACTIVO" pisando "Restart" | Tabs `overflow-x-auto whitespace-nowrap`. ServerCard mobile 2 filas (info, acciones). |
| SettingsPanel sub-nav 7 tabs → scroll-x molesto | `flex-wrap` (3+3+1). |

**Hook útil de automatización:** `window.__orion.setView(view)` expuesto
desde `main.tsx` — Playwright lo usa para cambiar de panel sin pelearse
con drawers y pointer-events. Útil también para debugging E2E.

`scripts/audit_mobile.py` queda en el repo para re-correr el audit en
futuros cambios al frontend mobile.

---

## 11A. Fase 6 bis — Telegram supergrupo Fases 2/3 (slash commands + chat libre LLM) (Junio 2026)

Continuación natural de la Fase 6 inicial. Antes el supergrupo solo
recibía notifs en topics. Ahora también acepta **comandos del user** y
**chat libre con el LLM**, todo desde Telegram.

### Fase 2 — Slash commands en topic Comandos (commit `a7242c6`)

**Nuevo módulo:** `orion/server/telegram_commands.py`
- `CommandSpec` (dataclass frozen) — `name`, `handler`, `description`,
  `requires_auth`.
- `CommandContext` (dataclass) — `sender_chat_id`, `args`, `raw_text`.
- Registry `_REGISTRY: dict[str, CommandSpec]` (dict preserva insertion
  order → afecta `/help`).
- `dispatch(text, *, sender_chat_id, authorized_chat_id)` — punto de
  entrada; nunca lanza (errores → texto al user).
- `parse(text)` — robusto: case-insensitive, soporta `/cmd@bot_username`,
  tolerante a whitespace.
- 6 comandos read-only (todos requieren auth excepto `/help`):
  - `/status` — usuarios + eventos hoy + último acceso.
  - `/usuarios` — lista con `🟢/⚪` activo/pausado.
  - `/pausar <slot>` — marca `active=False` (huella sigue en sensor pero
    DENIED en bridge).
  - `/activar <slot>` — reactiva.
  - `/log [hoy]` — últimos 10 eventos.
  - `/help` — público.

**Bridge wire (`telegram_bridge.py`):**
- `TelegramUpdate.from_user_id` agregado (separado de `chat_id` — en
  grupos `chat_id` es del grupo, `from_user_id` es del sender).
- `_should_dispatch_command(text, chat_id, thread_id)` matches:
  - Chat privado con bot (cualquier `/cmd`).
  - Supergrupo Y `thread_id == group.topics["commands"]`.
- `_dispatch_slash_command()`: ejecuta + responde al MISMO topic con
  `_send_async(..., thread_id=thread_id)`.

**Tests** (`tests/test_telegram_commands.py`, 35 tests):
- Parseo (incl. `/cmd@bot`, case-insensitive).
- Auth (sender == authorized, también acepta string), `/help` público,
  comandos desconocidos, slot fuera de rango, args inválidos.
- Round-trip pausar↔activar.
- Bridge: dispatch desde private chat + topic Comandos, NO desde otros
  topics, bypass del brain cuando matchea.

### Fase 3 — Chat libre con LLM en topic Chat (commit `a7242c6` + fix `c73c6a3` + fix `a96f461`)

**Filtro nuevo en bridge:**
- `_should_forward_to_brain(chat_id, thread_id)` — solo manda al brain
  si viene de chat privado O del topic `chat` del supergrupo. Otros
  topics (access/status/commands) **NO disparan brain** aunque manden
  texto libre.
- `_is_authorized_user(from_user_id)` — solo el `default_chat_id` (user
  autorizado) puede chatear. Otros miembros del supergrupo que escriban
  en topic Chat son **silenciosamente ignorados** (no gasta tokens, no
  responde).

**`_pending` deque cambió de tipo:**
- Antes: `deque[int]` (solo chat_id).
- Ahora: `deque[tuple[int, int | None]]` ((chat_id, thread_id)).
- Las respuestas del brain vuelven al MISMO topic de donde vino la
  pregunta, preservando `message_thread_id`.

**Fix crítico — listener `chat.stream`** (commit `c73c6a3`):

`chat_brain` emite respuestas via `bus.stream_chunk(role="orion", ...)`
que publica eventos `chat.stream`, y SOLO persiste el log con
`bus.persist_log_only(...)` (silencioso, sin publicar al bus). Esto se
hizo en commit `8664938` para fixar el bug del chat duplicado.

Resultado: el bridge solo escuchaba eventos `log` con prefijo "Orion:"
y nunca recibía las respuestas del brain. Síntoma reportado por el
user: "me sale en el apartado de conversación pero en la web, no me
sale en telegram".

Fix: `_handle_chat_stream(payload)` que acumula deltas por `turn_id`
y al cerrar (`final=True`) manda el texto completo. Buffer
`_stream_buffers: dict[turn_id, list[str]]` protegido por
`_stream_lock`. Pop al cerrar para no leakear memoria.

Soporta ambos patterns de emisión:
- `chat_brain`: UN chunk con texto completo + chunk vacío `final=True`.
- Live (Gemini): muchos chunks chicos token-por-token + `final=True`.

**Fix crítico — espacios en respuestas de Live** (commit `a96f461`):

Síntoma: "Hola. Sonlas11:31deldomingo,de juniode 2026." — palabras
pegadas en la respuesta de Live.

Causa: `_clean_transcript()` (en `orion/_helpers.py`) hace `.strip()`
sobre cada chunk de Live antes de emitir. Live emite cada palabra como
chunk separado, así que el `.strip()` borra los espacios entre
palabras. Un naive `"".join(chunks)` los concatena sin espacio.

Fix: nueva función `_smart_join(chunks)` que inserta un espacio entre
chunks adyacentes solo si:
- Último char del acumulado NO es whitespace, Y
- Primer char del chunk nuevo es alfanumérico (o `¿`/`¡`).

De ese modo:
- `chat_brain` (un solo chunk) → texto pasa intacto.
- Live (chunks sueltos sin espacios) → palabras separadas con `" "`.
- Puntuación de cierre (`,`, `.`, `?`) queda pegada al token previo.

**Tests** (`tests/test_telegram_chat_bridge.py`, 26 tests):
- Filtro: chat privado/topic Chat forwardea; access/commands/general
  NO; group sin topic chat configurado NO; legacy sin group NO.
- Auth: solo el authorized user puede; `from_user_id` distinto
  ignorado; `None` ignorado.
- Inbound: chat topic + private chat → brain + entry correcto en
  `_pending`; access topic + unauthorized → ignorado.
- Reply routing: log "Orion: ..." legacy path; `chat.stream` (ambos
  patterns chat_brain y Live); role="user" ignorado; buffer vacío NO
  manda; turnos interleaved con su buffer propio por turn_id.
- `_smart_join`: bug real reproducido y arreglado, preserva spaces
  existentes, no agrega espacio antes de puntuación.

### Setup que el user hizo en Telegram

Para usar Fases 2 y 3 el user necesitó:
1. **Crear topic Chat** en el supergrupo (no renombrar el General — el
   default tiene `thread_id=None` y el routing requiere int).
2. Mandar `/start@bot` adentro de cada topic nuevo.
3. El bridge logueó `chat_id=X thread_id=Y` permitiendo mapear nombre
   → thread_id manualmente.
4. Config final: `access=4, commands=2, chat=55` (los thread_ids son
   específicos a su grupo).

### Sanity al cierre

- Backend: **466 tests passing** (+54 nuevos: 35 commands + 26 chat
  bridge total tras todos los fixes).
- Frontend: 71 tests (sin cambio).
- 3 commits en main: `a7242c6` (feat), `c73c6a3` (fix listener),
  `a96f461` (fix spaces).

---

## 12. Fase 7 — Gmail vía google-auth (bypass de gog CLI) (Junio 2026)

Commit `1ed5ad9 refactor(notifications/gmail): usar google-auth directo, bypassear gog CLI`

### El bug que motivó el cambio

`orion/adapters/google/notifications/gmail.py` envolvía
`gog gmail search` por subprocess. En algunas instalaciones Windows el
subprocess heredaba env vars de forma inconsistente:

- Padre Python tenía `GOG_KEYRING_PASSWORD=...` (via `orion.bat set` o
  similar). Verificado vía log.
- `subprocess.run(cmd, env=env)` con env explícito conteniendo
  `GOG_KEYRING_PASSWORD`.
- gog corría pero devolvía `OAuth client credentials missing` (o
  `No auth for gmail`) consistentemente.
- El **mismo binario** ejecutado desde una terminal interactiva con las
  mismas env vars funcionaba perfecto.

Causa real nunca quedó clara. Hipótesis descartadas: APPDATA wrong
(diagnostic confirmó OK), threading (test desde thread funciona),
keyring locked (otros tests confirmaron unlocked), OneDrive lock
(keyring NO está en OneDrive). Posiblemente bug interno de gog v0.22 o
Windows env propagation con file keyring backend.

### La solución

Reescribir `gmail.py` con el mismo patrón que `classroom.py` (que SÍ
funciona): usar `google-auth` + `googleapiclient.discovery` directamente.
Cero subprocess, cero gog para Gmail.

**Files involucrados:**
- `orion/adapters/google/notifications/gmail.py` reescrito:
  - `_TOKEN_PATH = BASE_DIR / "tools" / "gmail" / "token.json"`.
  - `_load_creds()` lee el token, refresca via `Request()`, persiste.
  - `_is_revocation_error()` distingue `invalid_grant`/`revoked` (borra
    token) vs glitches transient (preserva).
  - `GmailAdapter.fetch()` llama Gmail API v1 vía `build("gmail","v1",
    credentials=creds)`. List threads → get metadata por thread →
    construye `NotificationItem`.
  - `is_configured()` devuelve `_TOKEN_PATH.exists()`.
- `tools/gmail/token.json` — formato google-auth:
  ```json
  {
    "token": null,
    "refresh_token": "...",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "...",
    "client_secret": "...",
    "scopes": ["https://www.googleapis.com/auth/gmail.modify", ...],
    "universe_domain": "googleapis.com"
  }
  ```
  Generado UNA vez con un script que lee el refresh token exportado de
  gog (`gog auth tokens export <email>`) + el `client_secret` del JSON
  descargado de GCP. Después de la primera vez google-auth se auto-mantiene.
- `tools/gmail/` agregado al `.gitignore`.

### Beneficios

- **Sin keyring file backend** ni env vars de password.
- **Sin subprocess** = sin problemas de propagación de env.
- **Refresh automático**: cuando access token expira, `creds.refresh(Request())`
  llama al token endpoint y persiste el nuevo access token.
- **Idéntico patrón** a Classroom — consistencia, menos APIs distintas
  que entender.
- El error "transient" del notif_poller desapareció. Panel Gmail OK.

### Migrar Drive o Calendar al mismo patrón (futuro)

Si en algún momento Drive o Calendar tienen el mismo problema con gog,
copiar el shape de `gmail.py`:
1. Crear `tools/<service>/token.json` con scopes correctos.
2. Adaptar `fetch()` para llamar la API del servicio (`build("drive","v3",...)`).
3. Mantener el patrón de `_load_creds()` + `_is_revocation_error()`.

---

## 13. Convenciones nuevas (post Fase 7)

### Agregar un adapter Google nuevo (Gmail, Classroom, Drive, …)

**Patrón establecido** (gmail.py + classroom.py):
1. Token JSON en `tools/<service>/token.json` (gitignored vía
   `tools/<service>/` en `.gitignore`).
2. Formato google-auth (refresh_token + client_id + client_secret +
   token_uri + scopes).
3. Adapter usa `google.oauth2.credentials.Credentials.from_authorized_user_file`.
4. Auto-refresh via `creds.refresh(Request())` + persist atómico con `.tmp`.
5. `_is_revocation_error()` distingue muerte real (`invalid_grant`) vs
   transient (red, 5xx) — solo borra token en muerte real.
6. **NO usar gog para servicios Google nuevos.** Gog queda para flujos
   de admin (autorizar cuenta inicial vía panel "Integraciones") y para
   features que no migramos todavía (sheets_sync, etc.).

### Agregar un endpoint que debe aceptar requests desde la LAN (ESP32, otros sensores)

**Patrón establecido** (`access_auth.py`):
1. Generar shared secret: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Guardarlo en `config/<service>.json` (gitignored).
3. Agregar el path a `AUTHED_PATHS` en `access_auth.py` (o crear módulo
   análogo si el patrón se expande).
4. El device manda header `X-Orion-Access-Token: <secret>` en cada POST.
5. `SharingMiddleware` ya hace el bypass — no tocar.
6. Tests de matriz: loopback OK / LAN sin header 403 / LAN bad header
   403 / LAN good header 201 / GET con header bueno 403 / POST otro
   path con header bueno 403.

---

## 14. Errores conocidos sin acción (no son bugs, son red)

| Síntoma | Por qué pasa | Acción |
|---|---|---|
| `[telegram.bridge] WARNING: getUpdates falló: _ssl.c:989: handshake timed out — reintentando en 5s` | Latencia/packet loss transient al hacer SSL handshake contra api.telegram.org. La retry logic del bridge lo maneja solo (5s backoff). | Ignorar si pasa esporádicamente. Si es crónico, chequear red. |
| `[notif_poller] WARNING: classroom falló (auth_required): Classroom sin token` | OAuth client de Google fue borrado o nunca se autorizó. | Re-crear OAuth client + click "Autorizar Classroom" en panel Notificaciones. Ver `docs/SETUP_GOOGLE_OAUTH.md`. |
| `[orion.classroom] WARNING: refresh transient falló (NO borro token): deleted_client` | Idem arriba — OAuth client deleted en GCP. NO borra el token local — esperando que el user re-cree el client. | Re-crear OAuth client. El refresh va a empezar a andar de nuevo. |

---

## 15. Pendientes acumulados (próximas sesiones)

### Acción del user (hardware / external)
- **Flashar el ESP32** con el sketch `arduino/access_control_fingerprint/`.
  Editar `WIFI_SSID`, `WIFI_PASS`, `ORION_URL` (IP de la PC en LAN o
  Tailscale), `ACCESS_TOKEN` (copiar de `config/access.json`). Después
  enrolar usuarios desde el panel Acceso → Usuarios.
- **`git push origin main`** cuando quieras sincronizar. Hay ~6 commits
  locales acumulados desde la última vez que pusheaste.
- **Decidir si `_design_brief/` va al repo o se gitignorea.** Untracked,
  ~0.4 MB de assets de diseño. Si va al repo: `git add _design_brief/`.
  Si no: agregar a `.gitignore`.
- **Decidir si borrar `backup-pre-filter-repo` del remoto** (sigue
  pendiente desde Fase 1).

### Features pendientes
- ✅ ~~Fase 2 del supergrupo Telegram (slash commands)~~ — **CERRADA**
  (commit `a7242c6`, ver §11A).
- ✅ ~~Fase 3 del supergrupo Telegram (chat libre LLM)~~ — **CERRADA**
  (commits `a7242c6` + `c73c6a3` + `a96f461`, ver §11A).
- **Fase 4 del supergrupo Telegram** — Topic Estado con resúmenes
  diarios + alertas IoT. Job nocturno que postea "Hoy entraron 4
  personas, último acceso 20:13. Temperatura promedio 22°C". Cron +
  adapter de resumen.
- **`/abrir` (extra)** — slash command futuro que activa el relé del
  ESP32 remotamente. Requiere endpoint inbound en el ESP32 (HTTP
  server o MQTT subscriber) — no factible con el sketch actual que es
  solo cliente HTTP.
- **Slash commands IoT** — `/temp`, `/humedad`, `/luz` que leen el
  último valor de los sensores. Reusar patrón de `_cmd_status`.

### Mejoras de plataforma
- **Migrar otros adapters Google a google-auth si fallan con gog** (Drive,
  Calendar). Solo si revientan; `gmail.py` ya es el patrón a copiar.
- **Migrar interfaces manuales en `web/src/api/rest.ts` a `Schemas["..."]`**
  (auto-generados desde OpenAPI por Fase 3D). Oportunístico cuando
  toques un panel — no vale la pena un PR dedicado.
- **Tests de los `index.tsx` top-level** (NotificationsPanel, IoTPanel,
  AgentsPanel, MCPPanel, AccessPanel) — requieren mockear hooks custom
  + `useOrionStore` + `useQuery`.
- **Validación visual de mobile** después de cualquier cambio al frontend.
  Re-correr `scripts/audit_mobile.py` + revisar screenshots en
  `%TEMP%\orion-audit\`.
- **Validación visual de god-files post-split** (MCPPanel, IoTPanel,
  AgentsPanel, DeviceFormModal, AccessPanel). `tsc + lint + build` pueden
  estar verdes con bugs sutiles de runtime (stale closures, state que no
  se preserva al cambiar de vista, hook order, props mal pasados).

### Limpieza histórica
- **Borrar `backup-pre-filter-repo` del remoto.** Quedó como safety net
  post-rewrite del history (Fase 1). Cuando estés seguro de que nada se
  rompió: `git push origin --delete backup-pre-filter-repo`.

---

## 16. Sesión Junio 2026 — LICENSE MIT + README shareable + paper STEM IEEE

Sesión enfocada en preparar O.R.I.O.N para presentación STEM
universitaria y para compartir el repo públicamente.

### 16.1 Licencia: cambio de CC BY-NC 4.0 → MIT (commit `1afd521`)

Razón: el user pidió poder distribuir el proyecto como open source de
verdad (no solo "código visible"). CC BY-NC bloquea uso comercial y
crea fricción legal en cualquier derivado. MIT es la licencia más
reconocida en proyectos académicos y compatible con todas las deps del
proyecto (FastAPI, React, SQLite, etc.).

Archivos tocados:
- `LICENSE` (nuevo) — texto canónico MIT, `Copyright (c) 2026 Zahir Padilla`.
- `readme.md` — badge actualizado a MIT verde, tagline reescrita
  ("local-first, open source, sin datos en cloud"), sección "¿Qué es
  Orion?" reescrita con los cinco principios de diseño (local-first,
  soberanía de datos, open source verificable, extensible, hardware
  propio), sección "Licencia" reescrita explicando las libertades MIT.

GitHub ahora reconoce el chip "MIT License" en la página principal del
repo y en la barra lateral derecha.

### 16.2 Paper STEM formato IEEE (local, gitignored)

Se inició la redacción del paper académico para presentación STEM
universitaria. Vive en `paper/` localmente y está en `.gitignore` para
no contaminar el repo público con drafts con marcadores `[TODO]` y
`[DATOS]`. Cuando esté listo para publicar, se untrackea.

**Archivos en `paper/`:**
- `outline.md` — estructura completa de 11 secciones + cronograma.
- `draft.md` — draft IEEE de ~8,200 palabras con secciones I-V
  completamente redactadas en español académico impersonal.

**Encuadre adoptado** tras iteración con el user:
- **Antes considerado**: "soberanía de datos + biometría" (caso acotado).
- **Antes considerado**: "asistente multimodal" (compite vs Gemini/Siri).
- **Adoptado**: **"asistente LLM agéntico local"** — la contribución es
  que el LLM **actúa** (no solo conversa) sobre el SO, archivos, IoT,
  hardware. La agencia abierta y auditable como diferenciador frente a
  asistentes propietarios.

**Estado por sección:**

| Sección | Estado | Bloqueante |
|---|---|---|
| Resumen, I (Introducción), II (Trabajos relacionados), III (Marco teórico), IV (Arquitectura con J ciclo de vida end-to-end), V (Implementación) | ✅ Completas | — |
| VI (Evaluación experimental — 3 ejes: benchmark de tareas, extensibilidad, biométrico) | ⏳ Pendiente | Datos del despliegue ESP32 |
| VII (Discusión), VIII (Limitaciones), IX (Conclusión) | ⏳ Pendiente | Sección VI |
| Apéndice, Reconocimiento, Referencias (19 IEEE), Biografía | Esqueleto o listo | Biografía requiere foto del user |

**Título final** (14 palabras, formato IEEE estándar):
*"O.R.I.O.N: Un Asistente Personal Agéntico Local Basado en Modelos de
Lenguaje a Gran Escala"*

**Decisiones de framing académico tomadas:**
- JARVIS eliminado del paper — reemplazado por formulación académica
  citando Stasko (*Communications of the ACM*, 2024, *"Beyond
  chatbots"*) como referencia [17] del campo.
- Voz impersonal ("se propone", "el sistema implementa") consistente.
- Citas formato IEEE `[N]` con lista alfabética por autor.
- Tabla I (comparación con Alexa/Siri/HA/Mycroft/LangChain) y Tabla II
  (catálogo de 25 herramientas por dominio).
- 19 referencias bibliográficas en formato IEEE canónico.

**Plantilla destino**: `Formato presentacion documentos IEEE ES (1).doc`
(la del user, está en su carpeta Downloads). El draft.md se pega en
esa plantilla aplicando los estilos preconfigurados (Title, Author,
Abstract, Heading 1, etc.) — Word aplica las dos columnas y Times New
Roman 10pt automáticamente.

### 16.3 Obsidian: implementado y descartado en la misma sesión

Se exploró integrar Obsidian como demo de "soberanía de datos
verificable" (notas en `.md` planos auditables). Se implementó:
- `orion/adapters/system/obsidian.py` con 3 tools (@tool decorated):
  `obsidian_save_note`, `obsidian_search_notes`, `obsidian_list_notes`.
- 20 tests passing (`tests/test_obsidian_adapter.py`).
- `config/obsidian.example.json` + `.gitignore` para `config/obsidian.json`.
- Integración end-to-end probada: nota real escrita en vault del user
  en `C:\Users\zahir\OneDrive\Documentos\OrionVault`.

**Decisión final**: el user prefiere usar **n8n** como plataforma de
visualización/automatización. Toda la integración Obsidian fue
borrada al final de la sesión:
- `rm orion/adapters/system/obsidian.py`
- `rm tests/test_obsidian_adapter.py`
- `rm config/obsidian.example.json`
- `rm config/obsidian.json`
- `.gitignore` revertido (sacada la línea `config/obsidian.json`).

Si en algún futuro se quiere volver a la integración Obsidian, el
patrón está en la historia de esta conversación. No hay deuda en el
repo.

### 16.4 Próximos pasos pendientes

- **Flashar ESP32** con sketch `arduino/access_control_fingerprint/` —
  esto desbloquea las secciones VI-IX del paper.
- **`paper/analyze_logs.py`** — script para parsear `logs/orion.log`
  por `corr_id` y calcular métricas (latencia, tasas) automáticamente.
- **`paper/benchmark.md`** — diseño de las 30-50 tareas para sección VI-A.
- **Decidir si seguir con n8n** y eventualmente integrar.
