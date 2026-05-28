"""
MySQL 数据库查询工具模块

封装数据库查询助手使用的三个 LangChain 工具：
list_sql_tables 用于发现真实表名，get_table_data 用于预览字段和样例数据，
execute_sql_query 用于在确认结构后执行只读自定义查询。
"""

import csv
import os
import re
from io import StringIO

from dotenv import load_dotenv
from langchain_core.tools import tool
from mysql.connector import Error, connect

from app.api.monitor import monitor

load_dotenv()

READ_ONLY_SQL_PREFIXES = ("select", "show", "describe", "desc", "explain", "with")
DANGEROUS_SQL_KEYWORDS = {
    "alter",
    "analyze",
    "call",
    "create",
    "delete",
    "drop",
    "execute",
    "grant",
    "insert",
    "kill",
    "load",
    "lock",
    "optimize",
    "rename",
    "replace",
    "revoke",
    "set",
    "truncate",
    "unlock",
    "update",
}
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff]+$")


# 集中读取数据库配置，后续三个工具都复用这份连接参数
def get_db_config():
    """
    从环境变量读取 MySQL 连接配置

    所有数据库工具都通过此函数拿到同一份连接参数，避免每个工具重复读取环境变量
    :return: mysql.connector.connect 可直接使用的连接参数
    """
    config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DATABASE"),
        "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
        "collation": os.getenv("MYSQL_COLLATION", "utf8mb4_unicode_ci"),
        "autocommit": True,
        "sql_mode": os.getenv("MYSQL_SQL_MODE", "TRADITIONAL"),
    }

    # 去掉未配置的可选项，避免把 None 传给 mysql.connector 造成连接参数异常
    config = {k: v for k, v in config.items() if v is not None}

    # user/password/database 是本教程工具能正常查询业务库的最小必要配置
    required_keys = ["user", "password", "database"]
    missing_keys = [k for k in required_keys if k not in config]
    if missing_keys:
        raise ValueError(f"缺失数据库核心配置：{', '.join(missing_keys)}")

    return config


def _csv_from_rows(columns, rows) -> str:
    """
    将查询结果转为 CSV 文本，避免字段里有逗号或换行时破坏格式。
    """
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue().strip()


def _normalize_sql(query: str) -> str:
    """
    规整 SQL 文本，便于做只读校验。
    """
    if not isinstance(query, str):
        raise ValueError("SQL 必须是字符串")

    normalized = query.strip()
    if not normalized:
        raise ValueError("SQL 不能为空")

    normalized = normalized.rstrip(";").strip()
    if ";" in normalized:
        raise ValueError("不允许执行多条 SQL 语句")

    return normalized


def _validate_read_only_sql(query: str) -> str:
    """
    工具层硬限制：只允许只读查询，不能只依赖提示词约束模型。
    """
    normalized = _normalize_sql(query)
    lowered = normalized.lower()
    first_word = lowered.split(None, 1)[0]

    if first_word not in READ_ONLY_SQL_PREFIXES:
        raise ValueError("只允许执行 SELECT、SHOW、DESCRIBE、EXPLAIN 等只读查询")

    tokens = set(re.findall(r"\b[a-zA-Z_]+\b", lowered))
    blocked = sorted(tokens & DANGEROUS_SQL_KEYWORDS)
    if blocked:
        raise ValueError(f"SQL 中包含不允许的关键字：{', '.join(blocked)}")

    return normalized


def _get_table_names(config) -> list[str]:
    """
    查询当前数据库中所有真实表名，用于白名单校验。
    """
    with connect(**config) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            return [row[0] for row in cursor.fetchall()]


def _quote_table_name(table_name: str, allowed_tables: list[str]) -> str:
    """
    校验并安全引用表名，避免模型把任意 SQL 片段塞进 table_name。
    """
    if not isinstance(table_name, str):
        raise ValueError("表名必须是字符串")

    normalized = table_name.strip().strip("`")
    if not normalized:
        raise ValueError("表名不能为空")

    if not IDENTIFIER_RE.match(normalized):
        raise ValueError("表名只能包含中文、字母、数字和下划线")

    if normalized not in allowed_tables:
        raise ValueError(f"表 {normalized} 不存在或不在可查询范围内")

    return f"`{normalized.replace('`', '``')}`"


@tool
def list_sql_tables() -> str:
    """
    查询当前数据库中所有可用表

    作用：让模型先识别真实可用的表名，方便后续预览表结构和编写自定义 SQL。
    :return: 有表：可用的表有：表1,表2,表3...
             没有表：没有可用的表
             出现异常：查询出现异常：异常信息
    """

    # 埋点：工具一被调用，前端可以展示当前正在查询数据库表名
    monitor.report_tool(tool_name="数据库表名查询工具：list_sql_tables", args={})

    # 加载数据库连接信息
    config = get_db_config()

    # MySQL 查询的固定步骤：
    # 1. 创建连接
    # 2. 创建 cursor
    # 3. 执行 SQL
    # 4. 获取返回结果
    # 5. 释放连接和 cursor 资源
    # 这里捕获异常并返回中文提示，避免工具报错直接中断 Agent 执行链路
    try:
        table_names = _get_table_names(config)
        if not table_names:
            return "没有可用的表"
        return f"可用的表有：{', '.join(table_names)}"
    except Error as e:
        return f"查询出现异常：{str(e)}"
    except ValueError as e:
        return f"查询被拒绝：{str(e)}"


@tool
def get_table_data(table_name) -> str:
    """
    查询指定表的前 100 行数据

    当前工具调用之前，应先调用 list_sql_tables 完成表名校验。
    此工具的作用：
    1. 完成单表样例数据查询
    2. 为多表查询提供表结构信息和数据格式参考
    :param table_name: 表名
    :return: CSV 格式数据
             1. 第一行是列信息，列之间使用英文逗号分隔
             2. 第二行开始是表数据，值之间也使用英文逗号分隔
             3. 行和行之间使用 \n 分隔
             4. 至多查询 100 条表数据
             例如：
                id,name,age\n -> 列头
                1,张三,18\n
                1,张三,18\n
                1,张三,18\n -> 至多查询 100 条
    """
    # 埋点：工具二被调用，前端可以展示当前正在预览哪张表
    monitor.report_tool(
        tool_name="数据库表数据查询工具：get_table_data",
        args={"table_name": table_name},
    )

    # 获取数据库参数
    config = get_db_config()

    # 查询流程同样是：连接 -> cursor -> 执行 SQL -> 获取列信息和数据 -> 自动释放资源
    try:
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                allowed_tables = _get_table_names(config)
                safe_table_name = _quote_table_name(table_name, allowed_tables)
                sql = f"SELECT * FROM {safe_table_name} LIMIT 100"
                cursor.execute(sql)

                # cursor.description 保存查询结果的列元信息
                # 例如：[("id", ...), ("name", ...), ("age", ...)]
                # 如果 SQL 没有结果集，description 可能为 None
                description = cursor.description
                if not description:
                    return f"数据表 {table_name} 暂无数据。"

                # 只取每个列信息元组的第一个元素，也就是列名
                # 例如：["id", "name", "age"]
                columns = [desc[0] for desc in description]

                # fetchall 返回表数据，形如：[(1, "张三", 18), (2, "李四", 20)]
                rows = cursor.fetchall()

                return _csv_from_rows(columns, rows)
    except Error as e:
        return f"查询出现异常：{str(e)}"
    except ValueError as e:
        return f"查询被拒绝：{str(e)}"


@tool
def execute_sql_query(query) -> str:
    """
    执行自定义只读 SQL 查询

    切记：执行之前，需要通过 list_sql_tables 明确真实表名，
    再通过 get_table_data 明确表结构和数据格式。
    适合多表关联、筛选、聚合、排序等复杂查询。
    :param query: 要执行的自定义 SQL 语句
    :return: CSV 格式数据
             1. 第一行是列信息，列之间使用英文逗号分隔
             2. 第二行开始是表数据，值之间也使用英文逗号分隔
             3. 行和行之间使用 \n 分隔
             例如：
                id,name,age\n -> 列头
                1,张三,18\n
                1,张三,18\n
    """
    try:
        safe_query = _validate_read_only_sql(query)

        # 埋点：记录模型最终生成的 SQL，便于观察是否真的落到了正确表字段上
        monitor.report_tool(
            tool_name="数据库表数据查询工具：execute_sql_query",
            args={"query": safe_query},
        )

        config = get_db_config()

        # 自定义查询和 get_table_data 的结果处理逻辑一致：
        # 执行 SQL -> 读取 description 得到列名 -> fetchall 得到数据 -> 拼成 CSV 返回
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(safe_query)

                # 非查询类 SQL 没有结果集描述，这里统一返回提示，避免工具调用直接抛错给模型
                description = cursor.description
                if not description:
                    return f"执行自定义 SQL 语句没有查询结果，SQL 为：{safe_query}"
                # description => [("列1", ...), ("列2", ...)]
                columns = [desc[0] for desc in description]

                # rows => [(值1, 值2), (值1, 值2)]
                rows = cursor.fetchall()

                return _csv_from_rows(columns, rows)
    except Error as e:
        return f"查询出现异常：{str(e)}"
    except ValueError as e:
        return f"查询被拒绝：{str(e)}"


if __name__ == "__main__":
    # 本地调试入口：直接运行本文件可验证 .env 中的 MySQL 连接配置是否可用
    print(
        execute_sql_query.invoke(
            {
                "query": "SELECT * FROM documents LIMIT 5"
            }
        )
    )
