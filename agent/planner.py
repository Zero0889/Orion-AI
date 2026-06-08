import json
import re
import sys
from pathlib import Path

from config import get_api_key
from core.tool_registry  import ToolRegistry
from core.tools_bootstrap import register_builtin_tools

# Asegura que el registry esté poblado antes de renderizar el prompt.
register_builtin_tools()


def _build_agents_text() -> str:
    """Renderiza la orquesta de agentes para el prompt del Director.

    Import perezoso para evitar ciclos (registry → llm → config → ...).
    Si agents.json no existe o no hay agentes, devuelve string vacío y el
    Director sigue trabajando en modo single-agent como antes.
    """
    try:
        from agent.registry import list_agents
        agents = list_agents()
    except Exception as e:
        print(f"[Planner] ⚠️ Sin registro de agentes: {e}")
        return ""

    if not agents:
        return ""

    lines = ["AVAILABLE AGENTS (assign one to each step):", ""]
    for a in agents:
        tools = "all" if "*" in a.tools else ", ".join(a.tools)
        lines.append(f"- {a.id} ({a.role}): {a.description} [tools: {tools}]")
    lines.append("")
    return "\n".join(lines)


def _build_skills_text() -> str:
    """Cataloga las skills instaladas para que el Director sepa cuándo
    invocar ``use_skill``. Vacío si no hay skills."""
    try:
        from core.skills import build_skill_catalog_prompt
        cat = build_skill_catalog_prompt()
    except Exception as e:
        print(f"[Planner] ⚠️ Sin catálogo de skills: {e}")
        return ""
    if not cat:
        return ""
    return (
        "AVAILABLE SKILLS (load with use_skill BEFORE the step that needs them):\n"
        f"{cat}\n\n"
        "When a goal matches a skill description, plan TWO steps:\n"
        "  1) any agent | use_skill | skill_id: \"<id>\"   (loads the recipe)\n"
        "  2) coder | generated_code | description: \"<execute as the skill says>\"\n\n"
    )


def _build_planner_prompt() -> str:
    """Renderiza el system prompt del planner con la lista de tools
    autogenerada desde el ``ToolRegistry`` y la orquesta de agentes
    desde ``agent.registry``. Si añades una tool al bootstrap o un
    agente a ``config/agents.json``, aparece aquí sin tocar nada más.
    """
    tools_text  = ToolRegistry().to_planner_text()
    agents_text = _build_agents_text()
    skills_text = _build_skills_text()

    return f"""You are the Director of O.R.I.O.N, a personal AI assistant orchestra.
Your job: break any user goal into a sequence of steps using ONLY the tools
listed below, and assign the right SPECIALIST AGENT to each step.

ABSOLUTE RULES:
- NEVER use generated_code unless the assigned agent has it in its tools list.
- NEVER reference previous step results in parameters. Every step is independent.
- Use web_search for ANY information retrieval, research, or current data.
- Use file_controller to save content to disk.
- Max 5 steps. Use the minimum steps needed.
- Each step MUST include an "agent" field with the id of the specialist that runs it.

{agents_text}{skills_text}AVAILABLE TOOLS AND THEIR PARAMETERS:

{tools_text}EXAMPLES:

Goal: "research mechanical engineering and save it to a notepad file"
Steps:

researcher | web_search   | query: "mechanical engineering overview definition history"
researcher | web_search   | query: "mechanical engineering applications and future trends"
fileops    | file_controller | action: write, path: desktop, name: mechanical_engineering.txt, content: "MECHANICAL ENGINEERING RESEARCH\\n\\nThis file will be filled with web research results."

Goal: "What is the price of Bitcoin"
Steps:

researcher | web_search | query: "Bitcoin price today USD"

Goal: "List the files on the desktop and find the largest 5 files"
Steps:

fileops | file_controller | action: list, path: desktop
fileops | file_controller | action: largest, path: desktop, count: 5

Goal: "Install PUBG from Steam"
Steps:

director | game_updater | action: install, platform: steam, game_name: "PUBG"

Goal: "Send John a message on WhatsApp saying there is a meeting tomorrow"
Steps:

director | send_message | receiver: John, message_text: "There is a meeting tomorrow", platform: WhatsApp

Goal: "Solve 17x^2 - 4x + 9 = 0 and explain"
Steps:

mathematician | generated_code | description: "Solve quadratic 17*x**2 - 4*x + 9 = 0 with sympy, print roots and discriminant"

OUTPUT — return ONLY valid JSON, no markdown, no explanation, no code blocks:
{{
  "goal": "...",
  "steps": [
    {{
      "step": 1,
      "agent": "researcher",
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {{}},
      "critical": true
    }}
  ]
}}
"""


# Compatibilidad: expone PLANNER_PROMPT como antes para los call sites
# que ya lo importaban como constante.
PLANNER_PROMPT = _build_planner_prompt()


def _normalize_agent(step: dict) -> None:
    """Asegura que el paso tenga un campo ``agent`` válido. Si el Director
    omitió el campo o asignó un agente inexistente/inhabilitado, cae al
    primer agente habilitado capaz de usar la tool, y si no, al director."""
    try:
        from agent.registry import agent_for_tool, has_agent, agent_can_use, list_agents
    except Exception:
        return  # sin registro de agentes → modo legacy

    tool = step.get("tool", "")
    agent = step.get("agent")

    if agent and has_agent(agent) and agent_can_use(agent, tool):
        return

    fallback = agent_for_tool(tool)
    if fallback:
        step["agent"] = fallback
        return

    enabled = list_agents()
    if enabled:
        step["agent"] = enabled[0].id


def create_plan(goal: str, context: str = "") -> dict:
    from core import gemini

    model = gemini.model(
        "gemini-2.5-flash-lite",
        system_instruction=_build_planner_prompt()
    )

    user_input = f"Goal: {goal}"
    if context:
        user_input += f"\n\nContext: {context}"

    try:
        response = model.generate_content(user_input)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError("Invalid plan structure")

        for step in plan["steps"]:
            if step.get("tool") in ("generated_code",):
                # Solo lo permitimos si el agente asignado lo tiene en su lista.
                from agent.registry import has_agent, agent_can_use
                agent_id = step.get("agent", "")
                allowed  = has_agent(agent_id) and agent_can_use(agent_id, "generated_code")
                if not allowed:
                    print(f"[Planner] ⚠️ generated_code rechazado en step {step.get('step')} (agente {agent_id!r}) — replacing with web_search")
                    desc = step.get("description", goal)
                    step["tool"] = "web_search"
                    step["parameters"] = {"query": desc[:200]}
                    step["agent"] = "researcher"
            _normalize_agent(step)

        print(f"[Planner] ✅ Plan: {len(plan['steps'])} steps")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: <{s.get('agent','?')}> [{s['tool']}] {s['description']}")

        return plan

    except json.JSONDecodeError as e:
        print(f"[Planner] ⚠️ JSON parse failed: {e}")
        return _fallback_plan(goal)
    except (ValueError, RuntimeError) as e:
        print(f"[Planner] ⚠️ Planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    print("[Planner] 🔄 Fallback plan")
    step = {
        "step": 1,
        "tool": "web_search",
        "description": f"Search for: {goal}",
        "parameters": {"query": goal},
        "critical": True
    }
    _normalize_agent(step)
    return {"goal": goal, "steps": [step]}


def replan(goal: str, completed_steps: list, failed_step: dict, error: str) -> dict:
    from core import gemini

    model = gemini.model(
        "gemini-2.5-flash",
        system_instruction=_build_planner_prompt()
    )

    completed_summary = "\n".join(
        f"  - Step {s['step']} <{s.get('agent','?')}> ({s['tool']}): DONE" for s in completed_steps
    )

    prompt = f"""Goal: {goal}

Already completed:
{completed_summary if completed_summary else '  (none)'}

Failed step: <{failed_step.get('agent','?')}> [{failed_step.get('tool')}] {failed_step.get('description')}
Error: {error}

Create a REVISED plan for the remaining work only. Do not repeat completed steps."""

    try:
        response = model.generate_content(prompt)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan     = json.loads(text)

        for step in plan.get("steps", []):
            if step.get("tool") == "generated_code":
                from agent.registry import has_agent, agent_can_use
                agent_id = step.get("agent", "")
                if not (has_agent(agent_id) and agent_can_use(agent_id, "generated_code")):
                    step["tool"] = "web_search"
                    step["parameters"] = {"query": step.get("description", goal)[:200]}
                    step["agent"] = "researcher"
            _normalize_agent(step)

        print(f"[Planner] 🔄 Revised plan: {len(plan['steps'])} steps")
        return plan
    except (json.JSONDecodeError, ValueError, RuntimeError) as e:
        print(f"[Planner] ⚠️ Replan failed: {e}")
        return _fallback_plan(goal)
