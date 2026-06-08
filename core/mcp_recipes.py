"""
core.mcp_recipes — Recetas curadas para servidores MCP populares
=================================================================
El registry público (``registry.modelcontextprotocol.io``) NO contiene
los servers oficiales de Anthropic — esos se publican directo a npm
desde el monorepo ``modelcontextprotocol/servers`` sin pasar por el
registry. Para que el usuario los pueda instalar con un click sin tener
que conocer el nombre exacto del paquete, mantenemos acá una lista
hardcoded.

Cada receta declara:

  - ``recipe_id``     — identificador estable
  - ``title``         — nombre legible
  - ``description``   — qué hace este server
  - ``category``      — para agrupar en la UI (files, dev, web, ai, system)
  - ``repo_url``      — link al código fuente (para mostrar stars)
  - ``command``       — binario a ejecutar
  - ``args_template`` — args con placeholders ``{NOMBRE}`` que la UI
                        sustituye por valores del usuario
  - ``prompts``       — qué pedirle al usuario (un input por placeholder)
  - ``env_required``  — variables de entorno que el server necesita
  - ``suggested_id``  — id sugerido para el server en mcp_servers.json
  - ``official``      — True si lo mantiene Anthropic
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class RecipePrompt:
    """Campo que la UI pregunta al usuario al instalar la receta."""
    key:         str                          # placeholder name, e.g. "ROOT_PATH"
    label:       str                          # input label
    description: str = ""                     # hint debajo
    default:     str = ""                     # valor sugerido
    required:    bool = True


@dataclass
class RecipeEnv:
    name:        str
    description: str = ""
    required:    bool = True


@dataclass
class Recipe:
    recipe_id:     str
    title:         str
    description:   str
    category:      str
    command:       str
    args_template: list[str]                  # puede tener "{PROMPT_KEY}"
    suggested_id:  str
    repo_url:      str = ""
    prompts:       list[RecipePrompt] = field(default_factory=list)
    env_required:  list[RecipeEnv]    = field(default_factory=list)
    official:      bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ── Catálogo ────────────────────────────────────────────────────────────

_HOME = str(Path.home()).replace("\\", "/")


RECIPES: list[Recipe] = [
    # ── Anthropic official (no están en registry, solo npm) ──────────────
    Recipe(
        recipe_id="filesystem",
        title="Filesystem",
        description=(
            "Acceso a archivos con sandbox por ruta. Lee, escribe, lista, "
            "busca y mueve archivos dentro de las carpetas que le permitas."
        ),
        category="files",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-filesystem", "{ROOT_PATH}"],
        suggested_id="fs",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        prompts=[
            RecipePrompt(
                key="ROOT_PATH",
                label="Carpeta raíz",
                description="ORION solo podrá leer/escribir dentro de esta carpeta.",
                default=_HOME,
            ),
        ],
        official=True,
    ),
    Recipe(
        recipe_id="git",
        title="Git",
        description=(
            "Operaciones sobre un repo local: log, status, diff, branches, "
            "commits. No hace push/pull al remoto."
        ),
        category="dev",
        command="uvx",
        args_template=["mcp-server-git", "--repository", "{REPO_PATH}"],
        suggested_id="git",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/git",
        prompts=[
            RecipePrompt(
                key="REPO_PATH",
                label="Ruta al repo",
                description="Carpeta raíz del repositorio git.",
                default=_HOME,
            ),
        ],
        official=True,
    ),
    Recipe(
        recipe_id="memory",
        title="Memory (knowledge graph)",
        description=(
            "Memoria persistente como knowledge graph. Útil para que ORION "
            "recuerde entidades y relaciones entre conversaciones."
        ),
        category="ai",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-memory"],
        suggested_id="memory",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
        env_required=[
            RecipeEnv(
                name="MEMORY_FILE_PATH",
                description="Dónde persistir el grafo (JSON).",
                required=False,
            ),
        ],
        official=True,
    ),
    Recipe(
        recipe_id="time",
        title="Time",
        description="Conversión de tiempo y zonas horarias. Sin red, instantáneo.",
        category="system",
        command="uvx",
        args_template=["mcp-server-time"],
        suggested_id="time",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/time",
        official=True,
    ),
    Recipe(
        recipe_id="fetch",
        title="Fetch",
        description=(
            "Descarga contenido web y lo convierte a Markdown limpio. Útil "
            "para que ORION lea una URL sin abrir el navegador."
        ),
        category="web",
        command="uvx",
        args_template=["mcp-server-fetch"],
        suggested_id="fetch",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
        official=True,
    ),
    Recipe(
        recipe_id="sequential-thinking",
        title="Sequential Thinking",
        description=(
            "Resolución de problemas en pasos estructurados. El modelo "
            "razona paso a paso y revisa su trabajo."
        ),
        category="ai",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        suggested_id="thinking",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
        official=True,
    ),
    Recipe(
        recipe_id="everything",
        title="Everything (test)",
        description=(
            "Server de prueba con TODOS los tipos de capabilities (tools, "
            "resources, prompts). Útil para verificar que tu cliente MCP "
            "funciona end-to-end."
        ),
        category="dev",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-everything"],
        suggested_id="everything",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/everything",
        official=True,
    ),

    # ── Populares de la comunidad ─────────────────────────────────────
    Recipe(
        recipe_id="github",
        title="GitHub",
        description=(
            "Issues, PRs, commits, búsqueda de código, archivos. Necesita un "
            "Personal Access Token con scope repo."
        ),
        category="dev",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-github"],
        suggested_id="gh",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/github",
        env_required=[
            RecipeEnv(
                name="GITHUB_PERSONAL_ACCESS_TOKEN",
                description="https://github.com/settings/tokens — scope: repo, read:user, read:org",
                required=True,
            ),
        ],
        official=True,
    ),
    Recipe(
        recipe_id="brave-search",
        title="Brave Search",
        description=(
            "Búsqueda web independiente. API tier gratis: 2000 queries/mes. "
            "Alternativa más confiable que scrapeo."
        ),
        category="web",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-brave-search"],
        suggested_id="brave",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search",
        env_required=[
            RecipeEnv(
                name="BRAVE_API_KEY",
                description="https://api.search.brave.com/app/keys",
                required=True,
            ),
        ],
        official=True,
    ),
    Recipe(
        recipe_id="postgres",
        title="Postgres",
        description=(
            "Consultas SQL en read-only sobre una base local o remota. "
            "ORION puede traducir lenguaje natural a SELECT."
        ),
        category="dev",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-postgres", "{CONNECTION_STRING}"],
        suggested_id="pg",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        prompts=[
            RecipePrompt(
                key="CONNECTION_STRING",
                label="Connection string",
                description="postgresql://user:pass@host:port/db",
                default="postgresql://postgres:postgres@localhost:5432/mydb",
            ),
        ],
        official=True,
    ),
    Recipe(
        recipe_id="slack",
        title="Slack",
        description=(
            "Leer canales, mandar mensajes, buscar conversaciones. Necesita "
            "un Bot Token de una app de Slack instalada en el workspace."
        ),
        category="web",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-slack"],
        suggested_id="slack",
        repo_url="https://github.com/modelcontextprotocol/servers/tree/main/src/slack",
        env_required=[
            RecipeEnv(name="SLACK_BOT_TOKEN", description="xoxb-..."),
            RecipeEnv(name="SLACK_TEAM_ID",   description="T..."),
            RecipeEnv(
                name="SLACK_CHANNEL_IDS",
                description="Canales separados por coma. Ej: C123,C456",
                required=False,
            ),
        ],
        official=True,
    ),
]


def list_recipes() -> list[dict]:
    """Serializa el catálogo a dicts (lo que sirve la route HTTP)."""
    return [r.to_dict() for r in RECIPES]


def get_recipe(recipe_id: str) -> Recipe | None:
    for r in RECIPES:
        if r.recipe_id == recipe_id:
            return r
    return None
