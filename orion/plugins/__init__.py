"""
plugins — Sistema de plugins de O.R.I.O.N
==========================================
Auto-descubre y carga plugins desde este directorio.

Cada plugin es un archivo .py que define una clase que hereda de PluginBase.
Los plugins se registran automáticamente al importar este módulo.

Ejemplo de plugin (plugins/mi_plugin.py):

    from orion.plugins.base import PluginBase

    class MiPlugin(PluginBase):
        name = "mi_herramienta"
        description = "Does something cool"

        def get_tool_declaration(self) -> dict:
            return {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING", "description": "Input text"}
                    },
                    "required": ["text"]
                }
            }

        def execute(self, parameters: dict, player=None, **kwargs) -> str:
            text = parameters.get("text", "")
            return f"Procesado: {text}"
"""

from orion.plugins.base import PluginBase, PluginRegistry

__all__ = ["PluginBase", "PluginRegistry"]
