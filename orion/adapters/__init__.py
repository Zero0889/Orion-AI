"""orion.adapters — Tools que Gemini puede invocar, agrupadas por dominio.

Layout (Fase 3 R5):

  - ``orion.adapters.system``  — host PC (files, processes, screen,
    desktop, reminders, dev tooling, GOG, electronics, live stubs).
  - ``orion.adapters.google``  — APIs de Google (Drive, Classroom,
    NotebookLM, polling Gmail+Classroom para notifs).
  - ``orion.adapters.web``     — servicios web no-Google (browser,
    search, YouTube, weather, vuelos).
  - ``orion.adapters.iot``     — IoT (devices, scenes, sensores,
    transports MQTT/Serial).

El ``ToolRegistry`` los descubre via ``auto_discover_tools("orion.adapters")``
que recorre recursivamente todos los subpaquetes y dispara los
decoradores ``@tool`` / ``@live_only_tool`` al importarlos.
"""
