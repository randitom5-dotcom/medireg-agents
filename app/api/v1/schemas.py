from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    code: str = "OK"
    message: str = "ok"
    data: T | None = None


class TaskStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    QA = "qa"
    REPORT = "report"
    INGEST = "ingest"


class TaskCreateRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question or report topic")
    thread_id: str | None = Field(default=None, description="Optional client supplied task id")
    dataset_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskInfo(BaseModel):
    task_id: str
    thread_id: str
    workspace_id: str
    user_id: str
    task_type: TaskType
    status: TaskStatus
    query: str
    created_at: str
    updated_at: str
    error: str | None = None


class TaskResult(BaseModel):
    task: TaskInfo
    files: list[dict[str, Any]] = Field(default_factory=list)


class ClientContext(BaseModel):
    workspace_id: str
    user_id: str


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    workspace_id: str
    user_id: str
    thread_id: str
    status: str
    size: int
    path: str


class DatasetInfo(BaseModel):
    id: str
    name: str
    description: str | None = None
    source: str = "ragflow"


class ReportInfo(BaseModel):
    report_id: str
    name: str
    path: str
    size: int
    mtime: float
