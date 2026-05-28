import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse

from app.api.monitor import manager
from app.api.v1.schemas import (
    ApiResponse,
    ClientContext,
    DatasetInfo,
    DocumentInfo,
    ReportInfo,
    TaskCreateRequest,
    TaskResult,
    TaskType,
)
from app.api.v1.task_store import list_output_files, task_store


router = APIRouter(prefix="/api/v1", tags=["integration-v1"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"
UPDATED_DIR = PROJECT_ROOT / "updated"
OUTPUT_DIR.mkdir(exist_ok=True)
UPDATED_DIR.mkdir(exist_ok=True)

ALLOWED_UPLOAD_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".md",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
}

DEFAULT_WORKSPACE_ID = "default"
DEFAULT_USER_ID = "anonymous"


def ok(data=None, message: str = "ok") -> ApiResponse:
    return ApiResponse(success=True, code="OK", message=message, data=data)


def sanitize_filename(filename: str) -> str:
    safe = Path(filename).name.strip().replace("\x00", "")
    if not safe:
        return f"upload-{uuid.uuid4().hex}"
    return safe


def sanitize_segment(value: str | None, default: str) -> str:
    """Normalize user-controlled path segments before using them in storage paths."""
    raw = (value or default).strip().replace("\\", "_").replace("/", "_").replace("\x00", "")
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw)
    return safe or default


def upload_workspace_dir(workspace_id: str, user_id: str, thread_id: str) -> Path:
    return (
        UPDATED_DIR
        / "workspaces"
        / sanitize_segment(workspace_id, DEFAULT_WORKSPACE_ID)
        / "users"
        / sanitize_segment(user_id, DEFAULT_USER_ID)
        / f"session_{sanitize_segment(thread_id, 'default-thread')}"
    )


def get_client_context(
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> ClientContext:
    """Resolve caller identity for private file/task isolation.

    The first version uses headers so the vendor frontend can integrate early.
    In production these values should come from a verified login token.
    """
    return ClientContext(
        workspace_id=sanitize_segment(x_workspace_id, DEFAULT_WORKSPACE_ID),
        user_id=sanitize_segment(x_user_id, DEFAULT_USER_ID),
    )


@router.get("/health")
async def health():
    return ok({"service": "integration-api", "status": "healthy"})


@router.post("/tasks/qa")
async def create_qa_task(
    request: TaskCreateRequest,
    ctx: Annotated[ClientContext, Depends(get_client_context)],
):
    task_thread_id = request.thread_id or str(uuid.uuid4())
    upload_dir = upload_workspace_dir(ctx.workspace_id, ctx.user_id, task_thread_id)
    task = await task_store.create_agent_task(
        query=request.query,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user_id,
        task_type=TaskType.QA,
        thread_id=task_thread_id,
        upload_dir=upload_dir,
    )
    return ok(task, "task created")


@router.post("/tasks/report")
async def create_report_task(
    request: TaskCreateRequest,
    ctx: Annotated[ClientContext, Depends(get_client_context)],
):
    report_query = f"Generate a structured Markdown report for this topic:\n{request.query}"
    task_thread_id = request.thread_id or str(uuid.uuid4())
    upload_dir = upload_workspace_dir(ctx.workspace_id, ctx.user_id, task_thread_id)
    task = await task_store.create_agent_task(
        query=report_query,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user_id,
        task_type=TaskType.REPORT,
        thread_id=task_thread_id,
        upload_dir=upload_dir,
    )
    return ok(task, "report task created")


@router.get("/tasks")
async def list_tasks(ctx: Annotated[ClientContext, Depends(get_client_context)]):
    return ok(await task_store.list_tasks(ctx.workspace_id, ctx.user_id))


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    ctx: Annotated[ClientContext, Depends(get_client_context)],
):
    task = await task_store.get_task(task_id, ctx.workspace_id, ctx.user_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task not found"})
    return ok(task)


@router.get("/tasks/{task_id}/result")
async def get_task_result(
    task_id: str,
    ctx: Annotated[ClientContext, Depends(get_client_context)],
):
    task = await task_store.get_task(task_id, ctx.workspace_id, ctx.user_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task not found"})
    return ok(TaskResult(task=task, files=list_output_files(OUTPUT_DIR, task.thread_id)))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    ctx: Annotated[ClientContext, Depends(get_client_context)],
):
    task = await task_store.get_task(task_id, ctx.workspace_id, ctx.user_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task not found"})
    task = await task_store.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task not found"})
    return ok(task, "task cancelled")


@router.websocket("/tasks/{task_id}/events")
async def task_events(websocket: WebSocket, task_id: str):
    await manager.connect(websocket, task_id)
    try:
        task = await task_store.get_task(task_id)
        if task:
            await websocket.send_json(
                {
                    "type": "task_status",
                    "event": task.status,
                    "message": "current task status",
                    "data": task.model_dump(),
                }
            )
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "message": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)
    except Exception:
        manager.disconnect(websocket, task_id)


@router.post("/documents/upload")
async def upload_documents(
    files: Annotated[list[UploadFile], File(...)],
    ctx: Annotated[ClientContext, Depends(get_client_context)],
    thread_id: Annotated[str | None, Form()] = None,
):
    doc_thread_id = thread_id or str(uuid.uuid4())
    safe_workspace_id = ctx.workspace_id
    safe_user_id = ctx.user_id
    target_dir = upload_workspace_dir(safe_workspace_id, safe_user_id, doc_thread_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    saved: list[DocumentInfo] = []
    for file in files:
        filename = sanitize_filename(file.filename)
        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_FILE_TYPE", "message": f"unsupported file type: {suffix}"},
            )

        doc_id = str(uuid.uuid4())
        file_path = target_dir / f"{doc_id}_{filename}"
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        saved.append(
            DocumentInfo(
                doc_id=doc_id,
                filename=filename,
                workspace_id=safe_workspace_id,
                user_id=safe_user_id,
                thread_id=doc_thread_id,
                status="uploaded",
                size=file_path.stat().st_size,
                path=str(file_path),
            )
        )

    return ok(
        {
            "workspace_id": safe_workspace_id,
            "user_id": safe_user_id,
            "thread_id": doc_thread_id,
            "documents": saved,
        },
        "documents uploaded",
    )


@router.get("/documents")
async def list_documents(
    ctx: Annotated[ClientContext, Depends(get_client_context)],
    thread_id: str | None = None,
):
    safe_workspace_id = ctx.workspace_id
    safe_user_id = ctx.user_id

    if thread_id:
        base_dir = upload_workspace_dir(safe_workspace_id, safe_user_id, thread_id)
    else:
        base_dir = UPDATED_DIR / "workspaces" / safe_workspace_id / "users" / safe_user_id

    docs: list[dict] = []
    if base_dir.exists():
        for file_path in base_dir.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                parts = file_path.relative_to(UPDATED_DIR).parts
                workspace = parts[1] if len(parts) > 1 and parts[0] == "workspaces" else DEFAULT_WORKSPACE_ID
                user = parts[3] if len(parts) > 3 and parts[2] == "users" else DEFAULT_USER_ID
                session = parts[4].removeprefix("session_") if len(parts) > 4 else ""
                docs.append(
                    {
                        "filename": file_path.name,
                        "workspace_id": workspace,
                        "user_id": user,
                        "thread_id": session,
                        "path": str(file_path),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "status": "uploaded",
                    }
                )
    docs.sort(key=lambda item: item["mtime"], reverse=True)
    return ok(docs)


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    ctx: Annotated[ClientContext, Depends(get_client_context)],
):
    safe_workspace_id = ctx.workspace_id
    safe_user_id = ctx.user_id
    base_dir = UPDATED_DIR / "workspaces" / safe_workspace_id / "users" / safe_user_id

    for file_path in base_dir.rglob(f"{doc_id}_*"):
        if file_path.is_file():
            stat = file_path.stat()
            parts = file_path.relative_to(UPDATED_DIR).parts
            workspace = parts[1] if len(parts) > 1 and parts[0] == "workspaces" else DEFAULT_WORKSPACE_ID
            user = parts[3] if len(parts) > 3 and parts[2] == "users" else DEFAULT_USER_ID
            session = parts[4].removeprefix("session_") if len(parts) > 4 else ""
            return ok(
                {
                    "doc_id": doc_id,
                    "filename": file_path.name,
                    "workspace_id": workspace,
                    "user_id": user,
                    "thread_id": session,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "status": "uploaded",
                }
            )
    raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_FOUND", "message": "document not found"})


@router.get("/datasets")
async def list_datasets():
    datasets: list[DatasetInfo] = []
    try:
        from app.tools.ragflow_tools import ragflow_client

        if hasattr(ragflow_client, "list_datasets"):
            for dataset in ragflow_client.list_datasets():
                datasets.append(
                    DatasetInfo(
                        id=str(getattr(dataset, "id", getattr(dataset, "name", ""))),
                        name=str(getattr(dataset, "name", "")),
                        description=getattr(dataset, "description", None),
                    )
                )
        else:
            for chat in ragflow_client.list_chats():
                datasets.append(
                    DatasetInfo(
                        id=str(getattr(chat, "id", getattr(chat, "name", ""))),
                        name=str(getattr(chat, "name", "")),
                        description=getattr(chat, "description", None),
                        source="ragflow_chat",
                    )
                )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "RAGFLOW_UNAVAILABLE", "message": str(exc)},
        ) from exc

    return ok(datasets)


@router.get("/reports")
async def list_reports(thread_id: str | None = None):
    reports = [
        ReportInfo(
            report_id=Path(item["path"]).stem,
            name=item["name"],
            path=item["path"],
            size=item["size"],
            mtime=item["mtime"],
        )
        for item in list_output_files(OUTPUT_DIR, thread_id)
        if Path(item["name"]).suffix.lower() in {".md", ".pdf"}
    ]
    return ok(reports)


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    for file_path in OUTPUT_DIR.rglob("*"):
        if file_path.is_file() and file_path.stem == report_id:
            stat = file_path.stat()
            return ok(
                ReportInfo(
                    report_id=report_id,
                    name=file_path.name,
                    path=str(file_path),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
            )
    raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "report not found"})


@router.get("/reports/{report_id}/download")
async def download_report(report_id: str):
    output_abs = OUTPUT_DIR.resolve()
    for file_path in OUTPUT_DIR.rglob("*"):
        if not file_path.is_file() or file_path.stem != report_id:
            continue
        resolved = file_path.resolve()
        if not resolved.is_relative_to(output_abs):
            break
        return FileResponse(resolved, filename=resolved.name)
    raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "report not found"})
