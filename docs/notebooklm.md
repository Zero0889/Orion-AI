# NotebookLM Research — Tool del Investigador

Integra el research agent de Google NotebookLM como tool del agente
`researcher`. Permite delegar investigaciones profundas: O.R.I.O.N
recibe un objetivo en lenguaje natural, crea un notebook nuevo en
NotebookLM, dispara el research agent (fast/deep, web/drive) y devuelve
la URL del notebook listo para abrir.

## Setup (una sola vez)

```powershell
# Instala el extra de navegador (Playwright + Chromium ~170 MB)
.venv\Scripts\pip.exe install "notebooklm-py[browser]"

# Login con tu cuenta Google (abre Chromium visible)
.venv\Scripts\notebooklm.exe login

# Verifica
.venv\Scripts\notebooklm.exe auth check --test --json
```

La sesión queda guardada en
`%USERPROFILE%\.notebooklm\profiles\default\storage_state.json`.
Mientras la cookie viva, todas las llamadas son programáticas (sin navegador).

## Cómo invocarla

El Investigador la elige sola cuando el goal pide múltiples fuentes o
un dossier. Ejemplos de prompts del usuario:

- "Busca 20 fuentes sobre IoT entre 2020 y 2025, modo deep, solo web."
- "Hazme un notebook con investigación profunda sobre seguridad en MQTT."
- "Pregúntale a mi notebook `xyz` qué dice sobre Tailscale."

## Acciones

| action     | parámetros principales                                  | devuelve                                |
|------------|---------------------------------------------------------|------------------------------------------|
| `research` | `topic`, `n_sources`, `mode`, `source`, `notebook_name` | URL del notebook + nº de fuentes importadas |
| `list`     | `limit`                                                 | lista de notebooks del usuario           |
| `ask`      | `notebook_id`, `question`                               | respuesta grounded + citas               |
| `delete`   | `notebook_id`                                           | confirmación                             |

- `mode`: `fast` (minutos) o `deep` (~10-30 min, más exhaustivo).
- `source`: `web` o `drive`.
- `timeout`: por defecto 1800 s (30 min) para esperar el research.

## Notas

- API no oficial de Google. Puede romperse si cambian endpoints — actualiza
  `notebooklm-py` si pasa.
- Aplica rate-limit de NotebookLM (no es ilimitado).
- El LLM del `researcher` (Gemini/DeepSeek/otro) solo decide los
  parámetros. El motor de búsqueda es NotebookLM, que internamente usa
  Gemini en la nube de Google.
- Para pruebas: `python -c "from actions.notebooklm_research import
  notebooklm_research; print(notebooklm_research({'action': 'list'}))"`
