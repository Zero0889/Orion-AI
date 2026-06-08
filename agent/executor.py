import json
import re
import sys
import threading
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Callable

from config import get_api_key
from agent.planner       import create_plan, replan
from agent.error_handler import analyze_error, generate_fix, ErrorDecision

def _looks_non_python(code: str) -> bool:
    """Heurística rápida: ¿esto NO es Python?
    Detecta HTML, CSS, JS, JSON y SQL puros. Si tiene cualquier signo
    inequívoco de Python (def/import/print con paréntesis), False.
    """
    if not code:
        return False
    head = code.lstrip()[:300].lower()
    if head.startswith(("<!doctype", "<html", "<head", "<body", "<div", "<svg", "<style")):
        return True
    # JSON empieza con { o [ y no tiene = ni : de Python
    if head.startswith(("{", "[")) and ("def " not in code and "import " not in code):
        return True
    # CSS puro: bloque con selectores + llaves, sin sintaxis Python
    if "{" in code and "}" in code and ";" in code and "def " not in code and "import " not in code:
        # SQL
        if any(kw in head for kw in ("select ", "insert ", "update ", "create table")):
            return True
        return True
    # JS/TS típico
    if head.startswith(("function ", "const ", "let ", "var ", "export ", "import {")):
        return True
    return False


def _detect_lang(code: str) -> str:
    head = code.lstrip()[:200].lower()
    if head.startswith(("<!doctype", "<html", "<head", "<body", "<div")):
        return "html"
    if head.startswith("<svg"):
        return "svg"
    if head.startswith("<style") or (":" in head and "{" in head and "}" in head and "<" not in head):
        return "css"
    if head.startswith(("{", "[")):
        return "json"
    if head.startswith(("function ", "const ", "let ", "var ", "export ", "import {")):
        return "javascript"
    if any(kw in head for kw in ("select ", "insert ", "update ", "create table")):
        return "sql"
    return "text"


def _run_generated_code(
    description: str,
    speak: Callable | None = None,
    agent_id: str | None = None,
) -> str:
    """Escribe y ejecuta código Python en caliente.

    Si ``agent_id`` apunta a un agente registrado (típicamente ``coder``),
    se usa su proveedor LLM y su system prompt en lugar del Gemini por
    defecto. Esto permite que DeepSeek (vía OpenRouter) escriba el
    código mientras el Director sigue siendo Gemini.
    """
    if speak:
        speak("Escribiendo código personalizado para esta tarea, señor.")

    home      = Path.home()
    desktop   = home / "Desktop"
    downloads = home / "Downloads"
    documents = home / "Documents"

    if not desktop.exists():
        try:
            import winreg
            key     = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
        except Exception:
            pass

    paths_block = (
        f"SYSTEM PATHS:\n"
        f"  Desktop   = r'{desktop}'\n"
        f"  Downloads = r'{downloads}'\n"
        f"  Documents = r'{documents}'\n"
        f"  Home      = r'{home}'\n"
    )

    user_prompt = (
        f"{paths_block}\n"
        f"Write Python code to accomplish this task:\n\n{description}\n\n"
        f"Return ONLY the Python code. No explanation, no markdown, no backticks."
    )

    code = ""
    routed_via_agent = False
    if agent_id:
        try:
            from agent.registry import ask_agent, has_agent
            if has_agent(agent_id):
                code = ask_agent(agent_id, user_prompt)
                routed_via_agent = True
                print(f"[Executor] 🤝 generated_code via agent '{agent_id}'")
        except Exception as e:
            print(f"[Executor] ⚠️ agent '{agent_id}' falló, cayendo a Gemini directo: {e}")

    if not routed_via_agent:
        from core import gemini
        model = gemini.model(
            "gemini-2.5-flash",
            system_instruction=(
                "You are an expert Python developer. "
                "Write clean, complete, working Python code. "
                "Use standard library + common packages. "
                "Install missing packages with subprocess + pip if needed. "
                "Return ONLY the Python code. No explanation, no markdown, no backticks.\n\n"
                + paths_block
            )
        )
        response = model.generate_content(
            f"Write Python code to accomplish this task:\n\n{description}"
        )
        code = response.text or ""

    try:
        code = code.strip()
        # Quita fences de cualquier lenguaje (```python, ```html, ```css, …)
        code = re.sub(r"```[a-zA-Z]*", "", code).strip().rstrip("`").strip()

        # Si lo que vino no es Python (HTML/CSS/JS/JSON/…), no podemos
        # ejecutarlo con sys.executable — devolvemos el código como texto
        # para que se vea en el chat. El descriptor "genera código HTML"
        # cae aquí.
        if _looks_non_python(code):
            lang = _detect_lang(code)
            print(f"[Executor] 📄 Código no-Python detectado ({lang}); devolviendo como texto.")
            return f"```{lang}\n{code}\n```"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        print(f"[Executor] 🐍 Running generated code: {tmp_path}")
        # Loggeamos el código generado (truncado) para poder debuggear cuando
        # el coder LLM elige un comando equivocado.
        _code_preview = code if len(code) <= 800 else code[:800] + f"…[+{len(code)-800} chars]"
        print(f"[Executor] 📝 Code:\n{_code_preview}")

        # Prepend tools/<name>/ dirs al PATH para que el código que llama
        # a binarios auxiliares (gog, etc.) los encuentre sin que el
        # usuario haya tocado el PATH del sistema.
        env = os.environ.copy()
        try:
            from core.cli_installer import extra_path_dirs
            extras = extra_path_dirs()
            if extras:
                env["PATH"] = os.pathsep.join(extras + [env.get("PATH", "")])
        except Exception as e:
            print(f"[Executor] ⚠️ No pude inyectar tools/ al PATH: {e}")

        # Fuerza UTF-8 al subprocess Python para evitar mojibake en Windows:
        # por default usa cp1252 al decodificar stdout de subprocesses, lo
        # que rompe acentos/eñes y luego TTS se traba al leerlos.
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=120, cwd=str(Path.home()),
            env=env,
            encoding="utf-8", errors="replace",
        )

        output = result.stdout.strip()
        error  = result.stderr.strip()

        # Si rc=0 pero no imprimió nada, guardamos el .py para debug en vez
        # de borrarlo — así podemos abrirlo y ver qué escribió el coder.
        keep_for_debug = (result.returncode == 0 and not output)
        if keep_for_debug:
            print(f"[Executor] ⚠️ rc=0 pero stdout vacío. Código preservado en: {tmp_path}")
            if error:
                print(f"[Executor] 📥 stderr capturado:\n{error[:1000]}")
        else:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        if result.returncode == 0 and output:
            return output
        elif result.returncode == 0:
            # Output vacío: incluimos stderr (si lo hay) en el resultado para
            # que el on_complete y el modelo vean qué pasó realmente.
            if error:
                return f"El comando ejecutó sin error pero no produjo salida visible. stderr:\n{error[:2000]}"
            return (
                "El comando ejecutó sin error pero no imprimió nada. "
                "Posibles causas: no hay eventos en el rango, el script "
                "no llamó print(), o la salida fue capturada y no propagada."
            )
        elif error:
            raise RuntimeError(f"Error de código: {error[:400]}")
        return "Completado."

    except subprocess.TimeoutExpired:
        raise RuntimeError("El código generado excedió el tiempo límite de 120 segundos.")
    except RuntimeError:
        raise
    except (OSError, ValueError) as e:
        raise RuntimeError(f"El código generado falló: {e}")

def _inject_context(params: dict, tool: str, step_results: dict, goal: str = "") -> dict:
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(v) > 100 and v not in ("Done.", "Completed.")
            ]
            if all_results:
                combined = "\n\n---\n\n".join(all_results)
                translated = _translate_to_goal_language(combined, goal)
                params["content"] = translated
                print(f"[Executor] 💉 Injected + translated content")

    # generated_code: si un step previo cargó una skill (use_skill), inyectamos
    # SOLO las líneas del SKILL.md que matchean con el goal — el cuerpo completo
    # tiene decenas de ejemplos y el coder LLM agarra el primero que ve (patrón
    # de OpenClaw: el modelo razona sobre la skill, no se le sirve todo).
    if tool == "generated_code":
        skill_blobs = [
            v for v in step_results.values()
            if isinstance(v, str) and v.startswith("# Skill cargada:")
        ]
        if skill_blobs:
            desc = params.get("description", "")
            filtered = _filter_skill_for_goal(skill_blobs[0], goal, desc)
            params["description"] = (
                f"TASK: {desc}\n\n"
                f"GOAL CONTEXT: {goal}\n\n"
                f"=== RELEVANT SKILL RECIPES (filtered for this task) ===\n"
                f"{filtered}\n"
                f"=== END SKILL RECIPES ===\n\n"
                f"COMMAND STRUCTURE (CRITICAL — read carefully):\n"
                f"  The binary is `gog`. Its CLI is: `gog <SERVICE> <SUBCOMMAND> [POSITIONAL ARGS] [--flags VALUES]`.\n"
                f"  SERVICE is a POSITIONAL ARG (no dashes!): gmail, calendar, drive, contacts, sheets, docs.\n"
                f"  SUBCOMMAND is the next POSITIONAL ARG: search, send, events, create, get, list, etc.\n"
                f"  FLAGS use double-dash: --max, --from, --to, --subject, --body, --account, --json.\n"
                f"  CORRECT  : subprocess.run(['gog', 'gmail', 'search', 'newer_than:7d', '--max', '2'], ...)\n"
                f"  WRONG    : subprocess.run(['gog', '--gmail', 'search', ...])   # gmail is NOT a flag!\n"
                f"  WRONG    : subprocess.run(['gog gmail search', ...])           # don't merge into one string\n\n"
                f"INSTRUCTIONS FOR THE PYTHON YOU WRITE:\n"
                f"1. Pick the ONE shell command from RECIPES whose action matches the TASK. "
                f"Match by INTENT not by order (calendar→calendar events, gmail→gmail search, "
                f"sheets→sheets get, docs→docs cat, etc).\n"
                f"2. Replace ALL placeholders with REAL values:\n"
                f"   - <calendarId> → 'primary' (always, unless the task names a different one)\n"
                f"   - you@example.com → OMIT the --account flag entirely (default account is used)\n"
                f"   - from:ryanair.com / a@b.com / 'Hi' / sheetId / docId → use actual values from the task\n"
                f"   - <iso> dates → compute from today ({_today_iso()}). "
                f"   For 'this week' use Mon 00:00 UTC to Sun 23:59 UTC. Use Python's datetime+timedelta.\n"
                f"3. Wrap with subprocess.run([...], capture_output=True, text=True, "
                f"encoding='utf-8', errors='replace'). "
                f"The binary `gog` is on PATH. Use a LIST of args (no shell=True, no single-string command). "
                f"The encoding='utf-8' is MANDATORY to avoid mojibake on Windows (acentos, eñes).\n"
                f"4. ALWAYS check result.returncode. If !=0, print('ERROR:', result.stderr). Else print(result.stdout).\n"
                f"5. NEVER copy placeholder emails/IDs/queries verbatim — those are illustrative templates.\n"
                f"6. For 'latest N mails' / 'últimos N correos' use: `gog gmail search 'in:inbox' --max N` "
                f"(or 'is:unread' if user asks for unread)."
            )
            print(f"[Executor] 💉 Injected filtered skill recipes ({len(filtered)} chars) for goal: {goal[:60]}")

    return params


def _today_iso() -> str:
    """Fecha de hoy en ISO para que el coder calcule rangos relativos."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d (%A UTC)")


# Mapeo keyword → categorías que probablemente matcheen. La idea no es ser
# exhaustivo, sino angostar el SKILL.md a unas 5-10 líneas relevantes en lugar
# de las 30+ que tiene completo. Si no matcheamos nada, devolvemos el body
# completo (mejor mucho contexto que ninguno).
_SKILL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "calendar":  ("calendar",),
    "evento":    ("calendar",),
    "agenda":    ("calendar",),
    "cita":      ("calendar",),
    "reunion":   ("calendar",),
    "reunión":   ("calendar",),
    "mail":      ("gmail",),
    "correo":    ("gmail",),
    "email":     ("gmail",),
    "gmail":     ("gmail",),
    "bandeja":   ("gmail",),
    "draft":     ("gmail draft", "drafts"),
    "borrador":  ("gmail draft", "drafts"),
    "drive":     ("drive",),
    "archivo":   ("drive",),
    "contacto":  ("contacts",),
    "sheet":     ("sheets",),
    "hoja":      ("sheets",),
    "planilla":  ("sheets",),
    "spreadsheet": ("sheets",),
    "doc":       ("docs",),
    "documento": ("docs",),
}


def _filter_skill_for_goal(skill_body: str, goal: str, desc: str) -> str:
    """Devuelve solo las líneas del SKILL.md que matchean con el goal.
    Si nada matchea, devuelve el body completo (más vale tener contexto de
    sobra que ninguno).
    """
    haystack = (goal + " " + desc).lower()
    matched_categories: set[str] = set()
    for kw, cats in _SKILL_KEYWORDS.items():
        if kw in haystack:
            matched_categories.update(cats)

    if not matched_categories:
        return skill_body  # sin pistas → contexto completo

    # Filtramos líneas que mencionan alguna categoría matched. Mantenemos
    # cabeceras (#, ##) y la sección "Setup" porque suele ser relevante.
    out_lines: list[str] = []
    keep_section = False
    for line in skill_body.splitlines():
        lstripped = line.lstrip()
        # Cabeceras siempre se mantienen
        if lstripped.startswith("#"):
            section_text = lstripped.lower()
            keep_section = any(c in section_text for c in matched_categories) or "setup" in section_text or "common commands" in section_text
            if keep_section:
                out_lines.append(line)
            continue
        # Dentro de una sección match, mantenemos todo
        if keep_section:
            out_lines.append(line)
            continue
        # Líneas sueltas que mencionan la categoría
        ll = line.lower()
        if any(c in ll for c in matched_categories):
            out_lines.append(line)

    filtered = "\n".join(out_lines).strip()
    if len(filtered) < 100:
        # Filtro demasiado agresivo → fallback al body completo.
        return skill_body
    return filtered
def _detect_language(text: str) -> str:
    from core import gemini
    model = gemini.model("gemini-2.5-flash-lite")
    try:
        response = model.generate_content(
            f"What language is this text written in? "
            f"Reply with ONLY the language name in English (e.g. Turkish, English, French).\n\n"
            f"Text: {text[:200]}"
        )
        return response.text.strip()
    except Exception:
        return "English"


def _translate_to_goal_language(content: str, goal: str) -> str:
    if not goal:
        return content
    try:
        from core import gemini
        model = gemini.model("gemini-2.5-flash")

        target_lang = _detect_language(goal)
        print(f"[Executor] 🌐 Translating to: {target_lang}")

        prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}.\n"
            f"IMPORTANT:\n"
            f"- Translate EVERYTHING, leave nothing in English\n"
            f"- Keep all facts, numbers, and data intact\n"
            f"- Keep the structure and formatting\n"
            f"- Output ONLY the translated text, nothing else\n\n"
            f"Text to translate:\n{content[:4000]}"
        )
        response = model.generate_content(prompt)
        translated = response.text.strip()
        print(f"[Executor] ✅ Translation done ({target_lang})")
        return translated
    except Exception as e:
        print(f"[Executor] ⚠️ Translation failed: {e}")
        return content

def _call_tool(
    tool: str,
    parameters: dict,
    speak: Callable | None,
    agent_id: str | None = None,
) -> str:
    """Despacha una tool del plan.

    Antes era un if/elif que duplicaba el wiring de ``main.py``. Ahora
    delega en el ``ToolRegistry`` unificado (poblado por
    ``core.tools_bootstrap``). Si la tool no está registrada, cae al
    fallback histórico ``generated_code`` (escribir Python en caliente y
    ejecutarlo en un subprocess).

    ``agent_id`` se propaga a ``generated_code`` para que el código lo
    escriba el LLM del agente asignado (p. ej. Coder con DeepSeek) en
    lugar del Gemini por defecto.
    """
    from core.tool_registry  import ToolRegistry
    from core.tools_bootstrap import register_builtin_tools

    # Idempotente — si main.py ya lo llamó, no hace nada.
    register_builtin_tools()

    if tool == "generated_code":
        description = parameters.get("description", "")
        if not description:
            raise ValueError("generated_code requires a 'description' parameter.")
        return _run_generated_code(description, speak=speak, agent_id=agent_id)

    registry = ToolRegistry()
    if not registry.has(tool):
        print(f"[Executor] ⚠️ Unknown tool '{tool}' — falling back to generated_code")
        return _run_generated_code(
            f"Accomplish this task: {parameters}", speak=speak, agent_id=agent_id
        )

    return registry.call_sync(
        tool, parameters,
        player=None,         # executor corre headless, sin UI
        speak=speak,
    ) or "Done."

class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2

    def execute(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        print(f"\n[Executor] 🎯 Goal: {goal}")

        replan_attempts = 0
        completed_steps = []
        step_results    = {} 
        plan            = create_plan(goal)

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "No pude crear un plan válido para esta tarea, señor."
                if speak: speak(msg)
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak: speak("Tarea cancelada, señor.")
                    return "Tarea cancelada."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "generated_code")
                desc     = step.get("description", "")
                params   = step.get("parameters", {})
                agent_id = step.get("agent")

                params = _inject_context(params, tool, step_results, goal=goal)

                print(f"\n[Executor] ▶️ Step {step_num}: <{agent_id or '?'}> [{tool}] {desc}")

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = _call_tool(tool, params, speak, agent_id=agent_id)
                        step_results[step_num] = result
                        completed_steps.append(step)
                        # Log más generoso para steps que producen data real
                        # (typical: generated_code con stdout de un CLI). El
                        # truncado a 100 chars escondía si el resultado venía
                        # bien o no.
                        _r = str(result)
                        _preview = _r if len(_r) <= 1200 else _r[:1200] + f"…[+{len(_r)-1200} chars]"
                        print(f"[Executor] ✅ Step {step_num} done ({len(_r)} chars):\n{_preview}")
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[Executor] ❌ Step {step_num} attempt {attempt} failed: {error_msg}")

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            import time; time.sleep(2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[Executor] ⏭️ Skipping step {step_num}")
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"Tarea abortada, señor. {recovery.get('reason', '')}"
                            if speak: speak(msg)
                            return msg

                        else: 
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion and tool != "generated_code":
                                try:
                                    fixed_step = generate_fix(step, error_msg, fix_suggestion)
                                    if speak: speak("Intentando un enfoque alternativo, señor.")
                                    res = _call_tool(
                                        fixed_step["tool"],
                                        fixed_step["parameters"],
                                        speak,
                                        agent_id=fixed_step.get("agent", agent_id),
                                    )
                                    step_results[step_num] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception as fix_err:
                                    print(f"[Executor] ⚠️ Fix failed: {fix_err}")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "Máximo de reintentos alcanzado"
                    success      = False

                if not success:
                    break

            if success:
                # Si el último step produjo data sustanciosa (stdout de un CLI,
                # JSON de una API, etc.), devolvemos esa data CRUDA al caller
                # — Gemini Live la procesa nativamente vía tool_response y le
                # habla al usuario con datos reales.  Sin esto, el summarizer
                # LLM solo ve las descripciones (no la data) y escribe una
                # frase genérica donde el modelo upstream alucina.
                #
                # Heurística: el último step_result califica como "data" si
                # tiene ≥50 chars y no es uno de los strings genéricos que
                # devuelve el handler de generated_code cuando algo va mal.
                _GENERIC_RESULTS = (
                    "Listo.", "Done.", "Completed.", "Completado.",
                    "Tarea completada exitosamente.",
                )
                last_result = None
                if completed_steps and step_results:
                    last_idx = max(step_results.keys()) if step_results else None
                    if last_idx is not None:
                        last_result = step_results.get(last_idx)

                if (
                    isinstance(last_result, str)
                    and len(last_result.strip()) >= 50
                    and last_result.strip() not in _GENERIC_RESULTS
                    and not last_result.startswith("# Skill cargada:")  # ese es contexto, no data
                ):
                    # Concatenamos cualquier code block previo (HTML/JSON/etc.)
                    # con la data del último step para no perder nada.
                    code_blocks = [
                        str(r) for r in step_results.values()
                        if isinstance(r, str) and r.lstrip().startswith("```")
                    ]
                    if code_blocks:
                        return last_result + "\n\n" + "\n\n".join(code_blocks)
                    return last_result

                # Fallback: ningún step produjo data sustanciosa → summary LLM.
                summary = self._summarize(goal, completed_steps, speak)
                code_blocks = [
                    str(r) for r in step_results.values()
                    if isinstance(r, str) and r.lstrip().startswith("```")
                ]
                if code_blocks:
                    return summary + "\n\n" + "\n\n".join(code_blocks)
                return summary

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = f"La tarea falló después de {replan_attempts} intentos de replanificación, señor."
                if speak: speak(msg)
                return msg

            if speak: speak("Ajustando mi enfoque, señor.")

            replan_attempts += 1
            plan = replan(goal, completed_steps, failed_step, failed_error)

    def _summarize(self, goal: str, completed_steps: list, speak: Callable | None) -> str:
        fallback  = f"Listo, señor. Completé {len(completed_steps)} pasos para: {goal[:60]}."
        steps_str = "\n".join(f"- {s.get('description', '')}" for s in completed_steps)
        prompt    = (
            f'User goal: "{goal}"\n'
            f"Completed steps:\n{steps_str}\n\n"
            "Write a single natural sentence in Spanish summarizing what was accomplished. "
            "Address the user as 'señor'. Be direct and positive. Always respond in Spanish."
        )

        # 1ª opción: agente 'summarizer' del registry (editable desde la
        # UI de Orquesta). Si el usuario lo desactivó o no existe, caemos
        # al hardcoded por compatibilidad histórica.
        try:
            from agent.registry import has_agent, ask_agent
            if has_agent("summarizer"):
                summary = ask_agent("summarizer", prompt).strip()
                if summary:
                    if speak: speak(summary)
                    return summary
        except Exception as e:
            print(f"[Executor] ⚠️ Agente 'summarizer' falló, cayendo al default: {e}")

        # 2ª opción: Gemini directo (el camino que tenías). flash en vez
        # de flash-lite porque tiene 250 req/día gratis vs 20 del lite.
        try:
            from core import gemini
            model    = gemini.model("gemini-2.5-flash")
            response = model.generate_content(prompt)
            summary  = (response.text or "").strip()
            if summary:
                if speak: speak(summary)
                return summary
        except Exception as e:
            print(f"[Executor] ⚠️ Gemini summarize falló: {e}")

        if speak: speak(fallback)
        return fallback