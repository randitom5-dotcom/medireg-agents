"""
RAGFlow 连接配置加载模块

集中读取 RAGFlow SDK 需要的 API Key 和服务地址，供原始调用示例与
LangChain 工具共用。这样后续如果 .env 字段或读取规则调整，只需要改这一处。
"""

import os
from typing import Optional, Tuple
from urllib.parse import urlparse

from dotenv import find_dotenv, load_dotenv


def _ensure_local_ragflow_bypasses_proxy(base_url: str | None) -> None:
    """Keep local RAGFlow traffic away from system HTTP proxies.

    requests, which is used by ragflow-sdk, honors HTTP_PROXY/HTTPS_PROXY from
    the environment. On Windows it is common for those variables to point at a
    local proxy port; localhost RAGFlow calls should bypass that proxy.
    """
    if not base_url:
        return

    host = urlparse(base_url).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        return

    bypass_hosts = ["localhost", "127.0.0.1", "::1"]
    for key in ("NO_PROXY", "no_proxy"):
        current = os.getenv(key, "")
        values = [item.strip() for item in current.split(",") if item.strip()]
        for host_item in bypass_hosts:
            if host_item not in values:
                values.append(host_item)
        os.environ[key] = ",".join(values)


def _load_ragflow_env() -> Tuple[Optional[str], Optional[str]]:
    """
    加载 RAGFlow 环境变量

    使用 python-dotenv 自动向上查找 .env，保持和项目其他配置加载方式一致。
    :return: (api_key, base_url)，缺失配置时对应位置返回 None
    """
    load_dotenv(find_dotenv())

    # RAGFlow SDK 初始化只需要这两个核心字段：认证 API Key 和服务基础地址
    api_key = os.getenv("RAGFLOW_API_KEY")
    base_url = os.getenv("RAGFLOW_API_URL")
    _ensure_local_ragflow_bypasses_proxy(base_url)
    return api_key, base_url
