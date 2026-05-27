"""
plugins.base — Clase base y registro para el sistema de plugins de O.R.I.O.N
"""

from __future__ import annotations

import importlib
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.logger import get_logger

log = get_logger("plugins")


class PluginBase(ABC):
    """Clase base abstracta para todos los plugins de O.R.I.O.N.

    Subclases deben definir:
        name        — nombre único de la herramienta (usado por Gemini)
        description — descripción corta para el LLM
    Y deben implementar:
        get_tool_declaration() — retorna el dict de declaración Gemini
        execute()              — ejecuta la herramienta y retorna resultado
    """

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    timeout: int = 60

    @abstractmethod
    def get_tool_declaration(self) -> dict:
        """Retorna la declaración de herramienta para Gemini (function_declarations)."""
        ...

    @abstractmethod
    def execute(self, parameters: dict, player: Any = None, **kwargs) -> str:
        """Ejecuta la herramienta con los parámetros dados.

        Args:
            parameters: Dict de parámetros enviados por Gemini.
            player: Referencia a la UI (para write_log, etc).
            **kwargs: Argumentos extra (speak, session, etc).

        Returns:
            String con el resultado para enviar de vuelta a Gemini.
        """
        ...

    def on_load(self) -> None:
        """Hook llamado al cargar el plugin. Override para inicialización."""
        pass

    def on_unload(self) -> None:
        """Hook llamado al descargar el plugin. Override para limpieza."""
        pass

    def __repr__(self) -> str:
        return f"<Plugin {self.name} v{self.version}>"


class PluginRegistry:
    """Registro singleton que descubre, carga y gestiona plugins."""

    _instance: PluginRegistry | None = None

    def __new__(cls) -> PluginRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
            cls._instance._loaded = False
        return cls._instance

    @property
    def plugins(self) -> dict[str, PluginBase]:
        return dict(self._plugins)

    def register(self, plugin: PluginBase) -> None:
        if not plugin.name:
            log.warning("Plugin sin nombre ignorado: %s", type(plugin).__name__)
            return
        if plugin.name in self._plugins:
            log.warning("Plugin duplicado '%s' — se reemplaza", plugin.name)
            self._plugins[plugin.name].on_unload()
        self._plugins[plugin.name] = plugin
        plugin.on_load()
        log.info("Plugin registrado: %s v%s", plugin.name, plugin.version)

    def unregister(self, name: str) -> None:
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.on_unload()
            log.info("Plugin eliminado: %s", name)

    def get(self, name: str) -> PluginBase | None:
        return self._plugins.get(name)

    def get_tool_declarations(self) -> list[dict]:
        """Retorna las declaraciones de herramientas de todos los plugins activos."""
        declarations = []
        for plugin in self._plugins.values():
            if plugin.enabled:
                try:
                    declarations.append(plugin.get_tool_declaration())
                except Exception as e:
                    log.error("Error obteniendo declaración de %s: %s", plugin.name, e)
        return declarations

    def get_tool_handlers(self) -> dict[str, PluginBase]:
        """Retorna un dict name→plugin para los plugins activos."""
        return {
            name: plugin
            for name, plugin in self._plugins.items()
            if plugin.enabled
        }

    def get_tool_timeouts(self) -> dict[str, int]:
        """Retorna dict name→timeout para plugins con timeout personalizado."""
        return {
            name: plugin.timeout
            for name, plugin in self._plugins.items()
            if plugin.enabled and plugin.timeout != 60
        }

    def discover_and_load(self, plugins_dir: Path | None = None) -> int:
        """Auto-descubre y carga plugins desde el directorio dado.

        Busca archivos .py en plugins_dir, importa cada uno,
        e instancia toda clase que herede de PluginBase.

        Returns:
            Número de plugins cargados.
        """
        if plugins_dir is None:
            from config import PLUGINS_DIR
            plugins_dir = PLUGINS_DIR

        if not plugins_dir.exists():
            log.debug("Directorio de plugins no existe: %s", plugins_dir)
            return 0

        loaded = 0
        for py_file in sorted(plugins_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            module_name = f"plugins.{py_file.stem}"
            try:
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                else:
                    module = importlib.import_module(module_name)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, PluginBase)
                        and attr is not PluginBase
                    ):
                        try:
                            instance = attr()
                            self.register(instance)
                            loaded += 1
                        except Exception as e:
                            log.error(
                                "Error instanciando plugin %s.%s: %s",
                                py_file.stem, attr_name, e
                            )

            except Exception as e:
                log.error("Error importando plugin %s: %s", py_file.stem, e)

        self._loaded = True
        log.info("Plugins cargados: %d de %s", loaded, plugins_dir)
        return loaded
