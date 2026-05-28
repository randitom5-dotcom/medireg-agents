"""RAGFlow tools with retry, timeout, and session cleanup."""

import json
import os
import time
from typing import Callable, TypeVar

from langchain_core.tools import tool
from ragflow_sdk import RAGFlow

from app.api.monitor import monitor
from app.rawflow.rag_config import _load_ragflow_env

T = TypeVar("T")

RAGFLOW_MAX_RETRIES = int(os.getenv("RAGFLOW_MAX_RETRIES", "2"))
RAGFLOW_RETRY_BACKOFF_SECONDS = float(os.getenv("RAGFLOW_RETRY_BACKOFF_SECONDS", "1.5"))
RAGFLOW_CONNECT_TIMEOUT_SECONDS = float(os.getenv("RAGFLOW_CONNECT_TIMEOUT_SECONDS", "10"))
RAGFLOW_READ_TIMEOUT_SECONDS = float(os.getenv("RAGFLOW_READ_TIMEOUT_SECONDS", "120"))
RAGFLOW_TIMEOUT = (RAGFLOW_CONNECT_TIMEOUT_SECONDS, RAGFLOW_READ_TIMEOUT_SECONDS)

api_key, base_url = _load_ragflow_env()
ragflow_client = RAGFlow(api_key=api_key, base_url=base_url)


def _retry_call(label: str, operation: Callable[[], T]) -> T:
    last_error: Exception | None = None
    for attempt in range(RAGFLOW_MAX_RETRIES + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= RAGFLOW_MAX_RETRIES:
                break
            time.sleep(RAGFLOW_RETRY_BACKOFF_SECONDS * (attempt + 1))

    assert last_error is not None
    raise RuntimeError(f"[RAGFLOW_ERROR] {label} failed after retries: {last_error}") from last_error


def _post_with_optional_timeout(path: str, payload: dict, *, stream: bool):
    """Call ragflow_client.post and pass timeout when the SDK supports it."""
    try:
        return ragflow_client.post(path, payload, stream=stream, timeout=RAGFLOW_TIMEOUT)
    except TypeError:
        return ragflow_client.post(path, payload, stream=stream)


@tool
def get_assistant_list() -> str:
    """List available RAGFlow chat assistants."""
    monitor.report_tool(tool_name="ragflow.get_assistant_list")

    try:
        chat_list = _retry_call("list_chats", lambda: ragflow_client.list_chats())
        if not chat_list:
            return "RAGFlow 未返回可用聊天助手。"

        lines: list[str] = []
        for chat in chat_list:
            dataset_names = getattr(chat, "kb_names", []) or []
            description = getattr(chat, "description", "") or ""
            lines.append(
                f"助手名称: {chat.name}; 描述: {description}; 关联知识库: {', '.join(dataset_names)}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"[RAGFLOW_ERROR] 查询 RAGFlow 助手列表失败: {exc}"


@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """Ask a RAGFlow chat assistant and delete the temporary session afterwards."""
    monitor.report_tool(
        tool_name="ragflow.create_ask_delete",
        args={"chat_name": chat_name, "question": question},
    )

    use_chat = None
    session = None
    try:
        chats = _retry_call("list_chats_by_name", lambda: ragflow_client.list_chats(name=chat_name))
        if not chats:
            return f"[RAGFLOW_ERROR] 未找到名为 {chat_name} 的 RAGFlow 助手。"

        use_chat = chats[0]
        session = _retry_call(
            "create_session",
            lambda: use_chat.create_session(name=f"temp_session_ask_{int(time.time())}"),
        )

        response = _retry_call(
            "chat_completion",
            lambda: _post_with_optional_timeout(
                f"/chats/{use_chat.id}/completions",
                {
                    "messages": [{"role": "user", "content": question}],
                    "stream": True,
                    "session_id": session.id,
                },
                stream=True,
            ),
        )

        result = ""
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            line = line.removeprefix("data:").strip()
            if line == "[DONE]":
                break

            data = json.loads(line)
            chunk_data = data.get("data")
            if not isinstance(chunk_data, dict):
                continue

            answer = chunk_data.get("answer")
            if answer:
                if answer.startswith(result):
                    result = answer
                elif not result.startswith(answer):
                    result += answer

        if hasattr(response, "close"):
            response.close()

        return result or "[RAGFLOW_ERROR] RAGFlow 未返回有效答案。"
    except Exception as exc:
        return f"[RAGFLOW_ERROR] RAGFlow 问答失败: {exc}"
    finally:
        if use_chat is not None and session is not None:
            try:
                use_chat.delete_sessions(ids=[session.id])
            except Exception as exc:
                monitor.report_tool(
                    tool_name="ragflow.delete_temp_session_failed",
                    args={"session_id": getattr(session, "id", ""), "error": str(exc)},
                )
