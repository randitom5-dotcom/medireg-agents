"""Main DeepAgent orchestration entrypoint."""

import asyncio
import shutil
import traceback
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.llm import model
from app.agent.prompts import main_agent_content
from app.agent.subagents.database_query_agent import database_query_agent
from app.agent.subagents.knowledge_base_agent import knowledge_base_agent
from app.agent.subagents.network_search_agent import network_search_agent
from app.api.context import (
    reset_session_context,
    set_session_context,
    set_thread_context,
)
from app.api.monitor import monitor
from app.tools.markdown_tools import generate_markdown
from app.tools.pdf_tools import convert_md_to_pdf
from app.tools.upload_file_read_tool import read_file_content

main_agent = create_deep_agent(
    model=model,
    system_prompt=main_agent_content["system_prompt"],
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
    checkpointer=InMemorySaver(),
    subagents=[database_query_agent, network_search_agent, knowledge_base_agent],
)

project_root_path = Path(__file__).parents[1].resolve()


def _copy_uploaded_files(session_dir: Path, session_id: str, upload_dir: str | Path | None) -> str:
    updated_dir_path = (
        Path(upload_dir).resolve()
        if upload_dir
        else project_root_path / "updated" / f"session_{session_id}"
    )
    if not updated_dir_path.exists():
        return ""

    files = [item for item in updated_dir_path.iterdir() if item.is_file()]
    if not files:
        return ""

    for file_path in files:
        shutil.copy2(file_path, session_dir / file_path.name)

    file_lines = "\n".join(f"    - {file_path.name}" for file_path in files)
    return (
        "\n[Uploaded files copied into the current session directory]\n"
        f"{file_lines}\n"
        "Use read_file_content when the answer depends on uploaded files.\n"
    )


def _extract_tool_calls(message: Any) -> list[dict[str, Any]]:
    tool_calls = getattr(message, "tool_calls", None)
    return tool_calls if isinstance(tool_calls, list) else []


async def run_deep_agent(task_query: str, session_id: str, upload_dir: str | Path | None = None):
    print(f"[MainAgent] start session_id={session_id}")

    session_dir = project_root_path / "output" / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = session_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    session_dir_str = str(session_dir).replace("\\", "/")
    relative_session_dir_str = str(session_dir.relative_to(project_root_path)).replace("\\", "/")
    relative_reports_dir_str = str(reports_dir.relative_to(project_root_path)).replace("\\", "/")
    uploaded_info_prompt = _copy_uploaded_files(session_dir, session_id, upload_dir)

    session_dir_token = set_session_context(session_dir_str)
    session_id_token = set_thread_context(session_id)
    monitor.report_session_dir(session_dir_str)

    config = {"configurable": {"thread_id": session_id}}
    path_instruction = f"""

Session output directory: {relative_session_dir_str}
Session reports directory: {relative_reports_dir_str}
{uploaded_info_prompt}

Rules:
1. When generating Markdown or PDF reports, save them under: {relative_reports_dir_str}/filename.
2. If uploaded files are present and relevant, read them with read_file_content first.
3. Use local structured data or RAGFlow before internet search unless the user asks for latest/current web information.
4. If a tool returns an error marker such as [RAGFLOW_ERROR] or [TAVILY_ERROR], explain the degraded source and continue with available evidence when possible.
"""

    try:
        async for chunk in main_agent.astream(
            {"messages": [{"role": "user", "content": task_query + path_instruction}]},
            config=config,
        ):
            for node_name, state in chunk.items():
                if not state or "messages" not in state:
                    continue

                messages = state["messages"]
                if not isinstance(messages, list) or not messages:
                    continue

                last_msg = messages[-1]
                if node_name != "model":
                    continue

                tool_calls = _extract_tool_calls(last_msg)
                if tool_calls:
                    for tool_call in tool_calls:
                        if tool_call.get("name") != "task":
                            continue

                        args = tool_call.get("args") or {}
                        monitor.report_assistant(
                            args.get("subagent_type", "unknown"),
                            {"description": args.get("description", "")},
                        )
                    continue

                content = getattr(last_msg, "content", "")
                if content:
                    print(f"[MainAgent] final content preview: {content[:100]}")
                    monitor.report_task_result(content)

    except asyncio.CancelledError:
        monitor.report_task_cancelled()
        raise
    except Exception as exc:
        print("[MainAgent][ERROR]", traceback.format_exc())
        monitor._emit(
            "error",
            f"[MAIN_AGENT_ERROR] Main agent failed: {type(exc).__name__}: {str(exc)}",
        )
    finally:
        reset_session_context(session_dir_token, session_id_token)


if __name__ == "__main__":
    asyncio.run(run_deep_agent("生成一份医疗器械注册知识库测试报告", "test_session_001"))
