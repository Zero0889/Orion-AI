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
- **Historial limpio:** `config/api_keys.json`, `config/credentials.json`, `config/gdrive_token.json` removidos del git history via `git filter-repo` + force-push. Keys ya rotadas previamente en Google Cloud Console. SHAs del repo reescritos (commit pre-rewrite era `ed1fabe`, post-rewrite `0ab810f`). **Backup en remoto: branch `backup-pre-filter-repo` @ `ed1fabe49b5ca2b28233eaaf7ee7ccc5922b1a6b`** — preserva el state pre-rewrite por si necesitás restaurar algo. Borrarlo cuando estés seguro: `git push origin --delete backup-pre-filter-repo`.

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

### 🟡 Pendientes que NECESITAN acción del usuario
1. **Validación visual de los 4 god-files post-split + los 8 paneles
   migrados a TanStack Query + Eye/CommandPalette en su nueva
   ubicación.** Hacer en el primer `npm run dev` post-pull. Si algo
   rompe: screenshot + qué panel + qué interacción.
2. **Decidir si borrar `backup-pre-filter-repo` del remoto.** Quedó como
   safety net post-rewrite del history. Cuando estés seguro de que
   nada se rompió: `git push origin --delete backup-pre-filter-repo`.
3. **Migrar interfaces manuales en `web/src/api/rest.ts` a `Schemas["..."]`**
   (auto-generados desde OpenAPI por Fase 3D). Hacelo oportunístico cuando
   toques un panel — no vale la pena un PR dedicado.

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
    ├── package.json              # scripts: dev, build, lint, format, typecheck, test/test:run, gen:api, gen:api:check.
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
        ├── query/
        │   ├── client.ts         # QueryClient singleton — montado por main.tsx + importado por el bridge WS.
        │   └── keys.ts           # QUERY_KEYS central — usado por hooks de paneles y por el bridge.
        ├── components/           # Piezas reutilizables del shell (Sidebar, TopBar, Toaster, paneles). MCPPanel/, DeviceFormModal/, IoTPanel/, AgentsPanel/ son carpetas con index.tsx + subarchivos. Cada carpeta puede incluir `*.test.ts(x)` y `__snapshots__/`.
        ├── widgets/              # Features cohesivas auto-contenidas (vs. components/).
        │   ├── eye/              # Ojo de Orion: BackgroundEye + EyeCore + hooks + pulse store interno.
        │   └── command-palette/  # Cmd+K palette + useCommandPalette store inline.
        ├── stores/orion.ts       # Zustand store. Dedup de chat (post-fix `8664938`). Bridge WS→invalidateQueries en applyEvent.
        ├── test/
        │   ├── setup.ts          # Vitest setup global — registra matchers de jest-dom + cleanup() de RTL.
        │   └── renderWithQuery.tsx  # Helper RTL para componentes que usan useQuery (QueryClient fresco por test).
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
| **Web (Node 20)** | tsc, eslint `--max-warnings=0`, prettier `--check`, vitest (47 tests), vite build |
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
npm run test:run                               # 47 tests passing en 6 archivos
npm run gen:api:check                          # API types están al día
npm run build                                  # built in ~3s

# CI
gh run list --limit 3                          # último commit en verde
```

Si todo verde: el refactor mayor del audit está **completo** (Fases 1, 2, 3A, 3B, 3D, 4 cerradas). Las próximas sesiones se ocupan de features nuevas o lo que el user pida. Si CI rojo: ver §4.

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
