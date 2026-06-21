import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import contextlib


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    LOW = 3
    NORMAL = 2
    HIGH = 1


@dataclass(order=True)
class Task:
    priority: int
    created_at: float = field(compare=False)
    task_id: str = field(compare=False)
    goal: str = field(compare=False)
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    result: Any = field(compare=False, default=None)
    error: str = field(compare=False, default="")
    speak: Any = field(compare=False, default=None)
    on_complete: Any = field(compare=False, default=None)
    cancel_flag: threading.Event = field(compare=False, default_factory=threading.Event)


class TaskQueue:
    def __init__(self, max_concurrent: int = 1):
        self._queue: list[Task] = []
        self._lock: threading.Lock = threading.Lock()
        self._condition: threading.Condition = threading.Condition(self._lock)
        self._tasks: dict[str, Task] = {}
        self._running: bool = False
        self._worker_thread: threading.Thread | None = None
        self._max_concurrent = max_concurrent
        self._active_count = 0
        self._executor = None

    def _get_executor(self):
        if self._executor is None:
            from orion.agent.executor import AgentExecutor

            self._executor = AgentExecutor()
        return self._executor

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="AgentTaskQueue"
        )
        self._worker_thread.start()
        print("[TaskQueue] ✅ Started")

    def stop(self) -> None:
        self._running = False
        with self._condition:
            self._condition.notify_all()
        print("[TaskQueue] 🔴 Stopped")

    # Máximo de tareas terminadas a recordar (evita fuga de memoria)
    _MAX_FINISHED_TASKS = 100

    def _cleanup_old_tasks(self) -> None:
        """Elimina tareas terminadas viejas para evitar fuga de memoria.
        Conserva las últimas _MAX_FINISHED_TASKS terminadas y todas las activas.
        """
        finished_states = (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        finished = [(tid, t) for tid, t in self._tasks.items() if t.status in finished_states]
        if len(finished) <= self._MAX_FINISHED_TASKS:
            return
        # Ordenar por más viejas primero
        finished.sort(key=lambda kv: kv[1].created_at)
        excess = len(finished) - self._MAX_FINISHED_TASKS
        for tid, _ in finished[:excess]:
            self._tasks.pop(tid, None)

    def submit(
        self,
        goal: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        speak: Callable | None = None,
        on_complete: Callable | None = None,
    ) -> str:

        task_id = str(uuid.uuid4())[:8]
        task = Task(
            priority=priority.value,
            created_at=time.time(),
            task_id=task_id,
            goal=goal,
            speak=speak,
            on_complete=on_complete,
        )

        with self._condition:
            self._queue.append(task)
            self._queue.sort(key=lambda t: (t.priority, t.created_at))
            self._tasks[task_id] = task
            self._cleanup_old_tasks()
            self._condition.notify()

        print(f"[TaskQueue] 📥 Task queued: [{task_id}] {goal[:60]}")
        return task_id

    def cancel(self, task_id: str) -> bool:

        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False

            task.cancel_flag.set()
            task.status = TaskStatus.CANCELLED
            print(f"[TaskQueue] 🚫 Task cancelled: [{task_id}]")
            return True

    def get_status(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "goal": task.goal,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
            }

    def get_all_statuses(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "task_id": t.task_id,
                    "goal": t.goal,  # completo, ya no cortamos a 50
                    "status": t.status.value,
                    "result": t.result,
                    "error": t.error,
                    "created_at": t.created_at,
                }
                for t in self._tasks.values()
            ]

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._queue if t.status == TaskStatus.PENDING)

    def _worker_loop(self) -> None:
        while self._running:
            task = None

            with self._condition:
                while self._running and not self._next_task():
                    self._condition.wait(timeout=1.0)
                task = self._next_task()
                if task:
                    task.status = TaskStatus.RUNNING
                    self._active_count += 1
                    with contextlib.suppress(ValueError):
                        self._queue.remove(task)

            if task:
                threading.Thread(
                    target=self._run_task,
                    args=(task,),
                    daemon=True,
                    name=f"AgentTask-{task.task_id}",
                ).start()

    def _next_task(self) -> Task | None:
        if self._active_count >= self._max_concurrent:
            return None
        for task in self._queue:
            if task.status == TaskStatus.PENDING and not task.cancel_flag.is_set():
                return task
        return None

    # Errores transitorios que justifican retry automático. Backoff
    # exponencial: 2s, 4s — total max ~6s antes de rendirse.
    _MAX_TRANSIENT_RETRIES = 2

    @staticmethod
    def _is_transient(err: BaseException) -> bool:
        """True si el error es típicamente recuperable reintentando
        unos segundos después (Gemini overloaded, NotebookLM RPC timeout,
        red transitoria)."""
        msg = str(err).lower()
        return (
            "503" in msg
            or "unavailable" in msg
            or "overloaded" in msg
            or "rate limit" in msg
            or "429" in msg
            or "deadline" in msg
            # NotebookLM-py: TransportServerError + "retries exhausted"
            # son típicamente recuperables si esperás unos segundos
            or "transportservererror" in msg
            or "retries exhausted" in msg
            or "transport server error" in msg
            # Network transient
            or "timed out" in msg
            or "timeout" in msg
            or "connection reset" in msg
            or "connection aborted" in msg
        )

    def _run_task(self, task: Task) -> None:
        print(f"[TaskQueue] ▶️ Running: [{task.task_id}] {task.goal[:60]}")
        should_callback = False
        callback_arg: Any = None
        executor = self._get_executor()
        last_err: Exception | None = None

        # Loop de retries solo para errores transitorios (Gemini 503,
        # 429, "overloaded"). Para errores reales (ValueError, KeyError,
        # etc) fallamos al primer intento — son bugs nuestros, no de red.
        for attempt in range(self._MAX_TRANSIENT_RETRIES + 1):
            if task.cancel_flag.is_set():
                break
            try:
                result = executor.execute(
                    goal=task.goal,
                    speak=task.speak,
                    cancel_flag=task.cancel_flag,
                )
                # éxito — salimos del loop
                with self._condition:
                    if task.cancel_flag.is_set():
                        task.status = TaskStatus.CANCELLED
                    else:
                        task.status = TaskStatus.COMPLETED
                        task.result = result
                    self._active_count -= 1
                    self._condition.notify_all()
                should_callback = not task.cancel_flag.is_set()
                callback_arg = result
                print(
                    f"[TaskQueue] ✅ Completed: [{task.task_id}]"
                    + (f" (tras {attempt} retries)" if attempt > 0 else "")
                )
                break

            except Exception as e:
                last_err = e
                if attempt < self._MAX_TRANSIENT_RETRIES and self._is_transient(e):
                    # Backoff: 2s, 4s
                    wait = 2 * (2**attempt)
                    print(
                        f"[TaskQueue] ⚠️ Transient error en [{task.task_id}] "
                        f"(intento {attempt + 1}/{self._MAX_TRANSIENT_RETRIES + 1}): "
                        f"{str(e)[:80]} — reintento en {wait}s"
                    )
                    # Aviso al usuario via speak si está disponible — UX:
                    # mejor que escuche "lo intento de nuevo" que ver
                    # silencio durante el backoff.
                    if task.speak and attempt == 0:
                        with contextlib.suppress(Exception):
                            task.speak("El servicio está saturado, lo intento de nuevo.")
                    if task.cancel_flag.wait(timeout=wait):
                        # cancelado durante el backoff
                        break
                    continue
                # No transitorio o se acabaron los retries — fallar
                err_msg = str(e)
                with self._condition:
                    task.status = TaskStatus.FAILED
                    task.error = err_msg
                    self._active_count -= 1
                    self._condition.notify_all()
                should_callback = True
                callback_arg = f"❌ Tarea falló: {err_msg}"
                print(f"[TaskQueue] ❌ Failed: [{task.task_id}] {err_msg}")
                break
        else:
            # else del for: solo entra si NO hicimos break — el loop
            # terminó por agotar retries en transient errors.
            err_msg = (
                f"Servicio no disponible tras {self._MAX_TRANSIENT_RETRIES} reintentos: {last_err}"
            )
            with self._condition:
                task.status = TaskStatus.FAILED
                task.error = err_msg
                self._active_count -= 1
                self._condition.notify_all()
            should_callback = True
            callback_arg = f"❌ Tarea falló: {err_msg}"
            print(f"[TaskQueue] ❌ Failed (sin retries): [{task.task_id}]")

        # on_complete corre FUERA del lock — un callback lento no debe
        # bloquear al worker de despachar la siguiente tarea.
        if task.on_complete and should_callback:
            try:
                task.on_complete(task.task_id, callback_arg)
            except Exception as cb_err:
                print(f"[TaskQueue] ⚠️ on_complete callback error: {cb_err}")


_queue = TaskQueue()
_queue_started = False
_queue_lock = threading.Lock()


def get_queue() -> TaskQueue:
    global _queue_started
    with _queue_lock:
        if not _queue_started:
            _queue.start()
            _queue_started = True
    return _queue
