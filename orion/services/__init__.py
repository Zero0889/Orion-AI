"""orion.services — Capa de servicios entre routes HTTP y domain.

Las rutas FastAPI deberían quedar **thin**: parsean el body Pydantic,
llaman a un método de service, mappean el resultado a HTTP. Toda la
orquestación (call al domain + publicar evento al bus + validaciones
cross-cutting) vive en `services/`.

Beneficios:
  - Tests unitarios sin TestClient: mockear bus, llamar service.
  - Pattern central para publish-after-mutation (un solo lugar donde
    el try/except del bus se repite).
  - Las routes pueden cambiar de transport (REST → gRPC → CLI) sin
    duplicar lógica de negocio.

Servicios actuales (POC de Fase 3):
  - :class:`~orion.services.notes_service.NotesService`
  - :class:`~orion.services.memory_service.MemoryService`
  - :class:`~orion.services.conversations_service.ConversationsService`

Las rutas grandes (iot/mcp/agent/skills/notebooklm/circuit/files/
settings/integrations/notifications) siguen el patrón clásico y se
van migrando incrementalmente — cuando se toque una para arreglar un
bug o agregar feature, extraer su service en el mismo PR.
"""
