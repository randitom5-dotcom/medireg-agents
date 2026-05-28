"""Tavily internet search tool with retry and graceful degradation."""

import os
import time
from typing import Callable, Literal, TypeVar

from dotenv import load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient

from app.api.monitor import monitor

load_dotenv()

T = TypeVar("T")
TAVILY_MAX_RETRIES = int(os.getenv("TAVILY_MAX_RETRIES", "2"))
TAVILY_RETRY_BACKOFF_SECONDS = float(os.getenv("TAVILY_RETRY_BACKOFF_SECONDS", "1.5"))

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def _retry_call(label: str, operation: Callable[[], T]) -> T:
    last_error: Exception | None = None
    for attempt in range(TAVILY_MAX_RETRIES + 1):
        try:
            return operation()
        except Exception as exc:  # Tavily SDK wraps several HTTP exceptions.
            last_error = exc
            if attempt >= TAVILY_MAX_RETRIES:
                break
            time.sleep(TAVILY_RETRY_BACKOFF_SECONDS * (attempt + 1))

    assert last_error is not None
    raise RuntimeError(f"[TAVILY_ERROR] {label} failed after retries: {last_error}") from last_error


@tool
def internet_search(
    query: str,
    topic: Literal["news", "finance", "general"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False,
):
    """
    根据用户问题检索互联网公开信息

    注意：本工具只用于外部公开网页、新闻、政策等信息，不用于查询业务数据库或 RAGFlow 私有知识库
    :param query: 搜索关键词或自然语言问题
    :param topic: 搜索主题，可选 news、finance、general
    :param max_results: 返回的最大结果数
    :param include_raw_content: 是否返回网页原文内容；False 返回摘要，True 尝试返回更完整正文
    :return: Tavily 返回的结构化搜索结果
    """
    # 工具内部埋点比外层 stream 解析更直接：只要工具被调用，前端就能看到本次搜索参数
    # 这里只上报查询参数，不上报搜索结果正文，避免监控事件体过大
    monitor.report_tool(
        tool_name="网络搜索工具",
        args={
            "query": query,
            "topic": topic,
            "max_results": max_results,
            "include_raw_content": include_raw_content,
        },
    )

    try:
        # Tavily 返回 query、results、title、url、content 等结构化字段，后续由子智能体阅读并汇总
        return _retry_call(
            "网络搜索工具",
            lambda: tavily_client.search(
                query=query,
                topic=topic,
                max_results=max_results,
                include_raw_content=include_raw_content,
            ),
        )
    except Exception as exc:
        return {
            "error": str(exc),
            "query": query,
            "results": [],
            "message": "网络搜索暂时不可用，请优先使用本地知识库或稍后重试。",
        }


if __name__ == "__main__":
    from pprint import pprint

    # 本地调试入口：直接运行本文件可验证 TAVILY_API_KEY 和 Tavily API 是否可用
    pprint(
        internet_search.invoke(
            {"query": "2026中国法定节假日放假安排表，我天天都想要放假"}
        )
    )