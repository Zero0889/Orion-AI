"""
Ejemplo de plugin para O.R.I.O.N
=================================
Este plugin añade una herramienta "system_info" que retorna
información del sistema (CPU, RAM, disco, Python).

Para crear tu propio plugin:
1. Crea un archivo .py en este directorio (plugins/)
2. Define una clase que herede de PluginBase
3. Implementa get_tool_declaration() y execute()
4. Reinicia ORION — el plugin se carga automáticamente
"""

import platform
import sys
from typing import Any

import psutil

from plugins.base import PluginBase


class SystemInfoPlugin(PluginBase):
    name = "system_info"
    description = (
        "Returns detailed system information: OS, CPU, RAM, disk, Python version. "
        "Use when the user asks about their computer specs or system status."
    )
    version = "1.0.0"
    timeout = 15

    def get_tool_declaration(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "detail": {
                        "type": "STRING",
                        "description": "What to report: all | cpu | memory | disk | os (default: all)"
                    }
                },
                "required": []
            }
        }

    def execute(self, parameters: dict, player: Any = None, **kwargs) -> str:
        detail = parameters.get("detail", "all").lower()
        parts = []

        if detail in ("all", "os"):
            parts.append(
                f"OS: {platform.system()} {platform.release()} ({platform.machine()})"
            )
            parts.append(f"Python: {sys.version.split()[0]}")
            parts.append(f"Hostname: {platform.node()}")

        if detail in ("all", "cpu"):
            parts.append(f"CPU: {psutil.cpu_count()} cores, {psutil.cpu_percent()}% uso")
            try:
                freq = psutil.cpu_freq()
                if freq:
                    parts.append(f"Frecuencia: {freq.current:.0f} MHz")
            except Exception:
                pass

        if detail in ("all", "memory"):
            mem = psutil.virtual_memory()
            parts.append(
                f"RAM: {mem.used / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB "
                f"({mem.percent}%)"
            )

        if detail in ("all", "disk"):
            disk = psutil.disk_usage("/")
            parts.append(
                f"Disco: {disk.used / (1024**3):.1f} GB / {disk.total / (1024**3):.1f} GB "
                f"({disk.percent}%)"
            )

        return "\n".join(parts) if parts else "Detalle no reconocido. Usa: all, cpu, memory, disk, os"
