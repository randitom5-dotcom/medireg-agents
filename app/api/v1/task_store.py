import asyncio
import datetime as dt
import uuid
from pathlib import Path
from typing import Any

from app.agent.main_agent import run_deep_agent
from app.api.v1.schemas import TaskInfo, TaskStatus, TaskType


class InMemoryTaskStore:
    """Small in-memory task registry for v1 integration APIs.

    This is intentionally simple for the first vendor-facing skeleton. It gives
    frontend teams stable task/status/result contracts today, and can later be
    swapped for Redis without changing the external API.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def create_agent_task(
        self,
        query: str,
        workspace_id: str,
        user_id: str,
        task_type: TaskType = TaskType.QA,
        thread_id: str | None = None,
        upload_dir: str | Path | None = None,
    ) -> TaskInfo:
        task_id = thread_id or str(uuid.uuid4())
        now = self._now()
        async with self._lock:
            existing = self._running.get(task_id)
            if existing and not existing.done():
                existing.cancel()

            self._tasks[task_id] = {
                "task_id": task_id,
                "thread_id": task_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "task_type": task_type,
                "status": TaskStatus.QUEUED,
                "query": query,
                "created_at": now,
                "updated_at": now,
                "error": None,
                "upload_dir": str(upload_dir) if upload_dir else None,
            }

            task = asyncio.create_task(self._run_agent_task(task_id, query, upload_dir))
            self._running[task_id] = task

        return await self.get_task(task_id)

    async def _run_agent_task(
        self,
        task_id: str,
        query: str,
        upload_dir: str | Path | None = None,
    ) -> None:
        await self._set_status(task_id, TaskStatus.RUNNING)
        try:
            await run_deep_agent(query, task_id, upload_dir=upload_dir)
        except asyncio.CancelledError:
            await self._set_status(task_id, TaskStatus.CANCELLED)
            raise
        except Exception as exc:
            await self._set_status(task_id, TaskStatus.FAILED, str(exc))
        else:
            await self._set_status(task_id, TaskStatus.FINISHED)
        finally:
            self._running.pop(task_id, None)

    async def cancel_task(self, task_id: str) -> TaskInfo | None:
        task = self._running.get(task_id)
        if not task:
            task_info = self._tasks.get(task_id)
            if not task_info:
                return None
            if task_info["status"] not in {
                TaskStatus.FINISHED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                await self._set_status(task_id, TaskStatus.CANCELLED)
            return await self.get_task(task_id)

        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            await self._set_status(task_id, TaskStatus.CANCELLED)
        return await self.get_task(task_id)

    async def get_task(
        self,
        task_id: str,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> TaskInfo | None:
        data = self._tasks.get(task_id)
        if data and workspace_id and data.get("workspace_id") != workspace_id:
            return None
        if data and user_id and data.get("user_id") != user_id:
            return None
        return TaskInfo(**data) if data else None

    async def list_tasks(
        self,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> list[TaskInfo]:
        tasks = []
        for item in self._tasks.values():
            if workspace_id and item.get("workspace_id") != workspace_id:
                continue
            if user_id and item.get("user_id") != user_id:
                continue
            tasks.append(TaskInfo(**item))
        return tasks

    async def _set_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: str | None = None,
    ) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task["status"] = status
            task["updated_at"] = self._now()
            task["error"] = error

    @staticmethod
    def _now() -> str:
        return dt.datetime.now(dt.UTC).isoformat()


def list_output_files(output_dir: Path, thread_id: str | None = None) -> list[dict[str, Any]]:
    base_dir = output_dir / f"session_{thread_id}" if thread_id else output_dir
    if not base_dir.exists():
        return []

    files: list[dict[str, Any]] = []
    output_abs = output_dir.resolve()
    for file_path in base_dir.rglob("*"):
        if not file_path.is_file():
            continue
        resolved = file_path.resolve()
        if not resolved.is_relative_to(output_abs):
            continue
        stat = resolved.stat()
        files.append(
            {
                "name": resolved.name,
                "path": str(resolved),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    files.sort(key=lambda item: item["mtime"], reverse=True)
    return files


task_store = InMemoryTaskStore()
