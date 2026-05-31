"""
server.routes.agent — Cola de agentes autónomos
================================================
Endpoints:
  GET   /api/agent/tasks                 → lista de tareas con estado
  GET   /api/agent/tasks/{id}            → detalle de una tarea
  POST  /api/agent/tasks                 → submit {goal, priority?}
  POST  /api/agent/tasks/{id}/cancel     → cancelar

Cualquier mutación publica ``agent.task`` en el bus para que el panel
React refresque. El task queue es el mismo singleton que usa main.py
(:func:`agent.task_queue.get_queue`).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agent.task_queue import TaskPriority, get_queue

router = APIRouter()

PRIORITY_MAP = {
    "low":    TaskPriority.LOW,
    "normal": TaskPriority.NORMAL,
    "high":   TaskPriority.HIGH,
}


class TaskSubmit(BaseModel):
    goal:     str = Field(..., min_length=1, max_length=2000)
    priority: str = "normal"


@router.get("/tasks")
async def list_tasks() -> list[dict]:
    return get_queue().get_all_statuses()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    info = get_queue().get_status(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Tarea '{task_id}' no encontrada")
    return info


@router.post("/tasks", status_code=201)
async def submit_task(body: TaskSubmit, request: Request) -> dict:
    pr = PRIORITY_MAP.get(body.priority.lower(), TaskPriority.NORMAL)

    bus = getattr(request.app.state, "bus", None)
    # ``speak`` se usa para que el agente hable durante la ejecución.
    # En el modo web le pasamos un wrapper que también emite por el bus
    # como log; main.OrionLive.speak() ya está cableado al bus también.
    def _speak(text: str) -> None:
        if bus is not None:
            try:
                bus.write_log(f"ORION: {text}")
            except Exception:
                pass

    task_id = get_queue().submit(body.goal, priority=pr, speak=_speak)

    if bus is not None:
        try:
            bus.publish("agent.task", {
                "id":     task_id,
                "status": "pending",
                "goal":   body.goal,
            })
        except Exception:
            pass

    return {"task_id": task_id, "status": "pending", "goal": body.goal}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> dict:
    ok = get_queue().cancel(task_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"Tarea '{task_id}' no se pudo cancelar (no existe o ya terminó)",
        )
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        try:
            bus.publish("agent.task", {"id": task_id, "status": "cancelled"})
        except Exception:
            pass
    return {"ok": True, "id": task_id, "status": "cancelled"}
