# MediReg Agents 医疗器械注册知识库问答助手

MediReg Agents 是一个面向医疗器械注册、法规审评、申报资料和企业知识治理的多智能体问答系统。项目基于 **FastAPI 业务编排层 + DeepAgents 多智能体 + RAGFlow 知识库检索 + MySQL 结构化数据 + React 前端** 构建，目标不是做一个简单聊天机器人，而是形成可检索、可追溯、可扩展的医疗器械注册业务助手。

系统支持从公开法规资料、RAGFlow 非结构化知识库、MySQL 结构化注册数据和用户上传文件中获取证据，并生成带来源依据的回答、Markdown 报告或 PDF 报告。

## 项目定位

本项目当前聚焦医疗器械注册知识库场景，核心能力包括：

1. 医疗器械注册法规、指导原则、审评要点和申报资料要求问答。
2. 审评报告、共性问题、交流园地和补正问题分析。
3. 临床评价路径、临床试验、同品种比对和免临床相关资料检索。
4. 注册证编号、产品名称、注册人、批准日期、有效期等结构化数据查询。
5. 用户上传 PDF、Word、Excel、Markdown、文本文件后的读取、总结和报告生成。
6. 工作区知识库、用户私有知识库和公共知识库的隔离设计。
7. 回答引用来源、URL、发布日期、章节、页码和原文片段，保证结论有迹可循。

## 总体架构

```text
用户浏览器
  |
  v
React 前端
  |
  | 问答 / 文件上传 / 报告下载 / 任务状态 / 引用查看
  v
FastAPI 业务编排层
  |
  |-- 用户会话
  |-- 任务管理
  |-- WebSocket 状态推送
  |-- 文件上传处理
  |-- 元数据管理
  |-- 权限控制
  |-- 审计日志
  |-- 智能体调度
  |
  |---> DeepAgents 主智能体
  |       |-- 注册数据查询智能体
  |       |-- 知识库检索智能体
  |       |-- 网络搜索智能体
  |       |-- 报告生成工具
  |
  |---> MySQL / RDS
  |       |-- 产品注册数据
  |       |-- 注册证数据
  |       |-- 临床评价路径
  |       |-- 结构化表格
  |       |-- 文档元数据
  |       |-- 任务与审计日志
  |
  |---> RAGFlow
  |       |-- 指导原则
  |       |-- 审评报告
  |       |-- 共性问题
  |       |-- 临床评价资料
  |       |-- 工作区资料
  |       |-- 用户上传资料
  |
  |---> Tavily / 公开数据源
          |-- 监管机构网页
          |-- 公开政策公告
          |-- 最新公开信息
```

核心分工：

| 层级 | 作用 |
| --- | --- |
| FastAPI | 统一接入、权限控制、任务管理、文件处理、状态推送 |
| DeepAgents | 负责问题拆解、工具选择、子智能体调度和结果汇总 |
| RAGFlow | 负责非结构化文档解析、切片、向量检索和重排 |
| MySQL | 负责注册证、产品公告、临床路径、表格和元数据精确查询 |
| Redis | 适合后续承接会话缓存、任务队列和限流计数 |
| React | 负责问答交互、上传、事件流展示和结果下载 |

## 智能体与工具

| 归属 | 能力 | 工具 |
| --- | --- | --- |
| 主智能体 | 任务规划、助手调度、结果汇总、文件交付 | `read_file_content`、`generate_markdown`、`convert_md_to_pdf` |
| 网络搜索助手 | 查询互联网公开监管信息、政策公告和网页资料 | `internet_search` |
| 数据库查询助手 | 查询结构化注册数据、表格数据和元数据 | `list_sql_tables`、`get_table_data`、`execute_sql_query` |
| RAGFlow 助手 | 查询非结构化知识库和用户上传资料 | `get_assistant_list`、`create_ask_delete` |

数据库工具层已经增加只读保护：

1. 只允许 `SELECT`、`SHOW`、`DESCRIBE`、`DESC`、`EXPLAIN`、`WITH` 等只读查询。
2. 拦截 `INSERT`、`UPDATE`、`DELETE`、`DROP`、`ALTER`、`CREATE`、`TRUNCATE` 等危险语句。
3. 禁止多语句执行。
4. `get_table_data` 会先校验真实表名，再安全查询。

提示词只负责约束智能体如何选择工具和如何回答，权限、只读 SQL、文件范围和 Dataset 范围必须由后端和工具层硬控制。

## 数据建库思路

抓取到的医疗器械注册资料不能直接全部上传到 RAGFlow，需要先预处理和分流。

```text
原文文档 -> RAGFlow
结构化表格 -> MySQL
manifest/json/url -> 元数据表
用户私有文件 -> 用户私有 dataset
工作区共享文件 -> 工作区 dataset
公共法规资料 -> 公共 dataset
```

推荐流程：

```text
1. 扫描文件，生成 inventory.csv
2. 抽取元数据：标题、URL、发布日期、来源栏目
3. 文件去重：hash、URL、标题 + 日期
4. 判断内容类型：正文、表格、混合、元数据、压缩包
5. 分流：RAGFlow / MySQL / metadata / pending / skip
6. 小批量导入验证
7. 全量导入
```


## 多用户隔离

系统建议采用逻辑隔离：

```text
public     公共法规资料
workspace  工作区共享资料
private    用户私有资料
```

后端根据用户身份计算可访问范围：

```text
可访问 Dataset =
  公共 Dataset
  + 用户所属工作区 Dataset
  + 用户个人私有 Dataset
```

前端不能直接传入 `ragflow_dataset_id`、数据库表名、对象存储路径或原始 SQL。真正的访问范围由后端和工具层决定。

## 回答可追溯

系统回答应基于证据包生成，而不是让模型自由发挥：

```text
用户问题
  -> RAG / MySQL 召回证据
  -> 证据带 document_id / chunk_id / table_row_id
  -> 大模型基于证据回答
  -> 回答中插入引用编号
  -> 后端保存 answer_citations
  -> 前端展示来源详情
```

引用来源至少应包含：

```text
标题
来源网站
发布日期
URL
页码 / 章节 / 表格行
原文片段
相似度或命中说明
```

如果资料是征求意见稿、草案或历史版本，回答中必须提示其状态和适用风险。

## 项目结构

```text
medireg-agents/
├── app/
│   ├── agent/
│   │   ├── subagents/              # 网络搜索、数据库查询、RAGFlow 子智能体
│   │   ├── llm.py                  # OpenAI 兼容模型初始化
│   │   ├── main_agent.py           # 主智能体组装与执行入口
│   │   └── prompts.py              # 读取 app/prompt/prompts.yml
│   ├── api/
│   │   ├── context.py              # ContextVar 保存 thread_id 和 session_dir
│   │   ├── monitor.py              # 工具调用、助手调用、结果和异常事件推送
│   │   ├── server.py               # FastAPI 主服务
│   │   └── v1/                     # 面向外包和外部系统的标准 API
│   ├── prompt/
│   │   └── prompts.yml             # 医疗器械注册场景提示词配置
│   ├── rawflow/                    # RAGFlow 配置
│   ├── tools/                      # Tavily、MySQL、RAGFlow、文件读取、Markdown、PDF 工具
│   ├── utils/                      # 路径解析、Markdown/PDF 转换等工具
│   ├── output/                     # 运行时生成文件，已忽略
│   └── updated/                    # 上传文件暂存目录，已忽略
├── docs/                           # 医疗器械知识库方案、验证和接口文档
├── reports/                        # 项目生成和归档报告
├── examples/                       # 示例脚本、RAGFlow SDK demo 和测试文档
├── frontend/                       # React + Vite 前端项目
├── scripts/                        # 数据预处理和导入脚本
├── .env.example                    # 环境变量示例
├── pyproject.toml                  # Python 项目依赖声明
└── uv.lock                         # uv 锁定文件
```

## 快速开始

### 1. 准备环境

- Python `3.12`
- `uv`
- Node.js 与 `pnpm`
- 可用的大模型 API Key
- Tavily API Key
- RAGFlow 服务与 API Key
- MySQL 或 RDS

### 2. 安装后端依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

按实际环境修改：

```bash
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=你的大模型_API_KEY
LLM_QWEN_MAX=qwen-max

TAVILY_API_KEY=你的_TAVILY_API_KEY

RAGFLOW_API_URL=http://your-ragflow-host
RAGFLOW_API_KEY=ragflow-your-api-key

MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=medireg_db
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_CHARSET=utf8mb4
MYSQL_COLLATION=utf8mb4_unicode_ci
MYSQL_SQL_MODE=TRADITIONAL
```

`.env` 已在 `.gitignore` 中忽略，不要提交真实密钥。

### 4. 准备 RAGFlow 知识库

RAGFlow 不在本仓库中直接启动，需要接入已有 RAGFlow 服务。建议按以下 Dataset 分组：

```text
mdr_public_guidelines
mdr_public_review_reports
mdr_public_common_questions
mdr_public_clinical_eval
mdr_public_draft_comments
mdr_public_regulatory_notices
mdr_workspace_{workspace_id}
mdr_user_{workspace_id}_{user_id}
```

上传前应先完成数据清洗清单，不建议把原始抓取目录直接全量上传。

### 5. 准备 MySQL

MySQL 用于存放结构化注册数据、文档元数据、Dataset 映射、表格抽取结果、任务和审计日志。建议表包括：

```text
documents
knowledge_datasets
workspace_members
uploaded_files
structured_tables
structured_table_rows
registered_medical_devices
clinical_evaluation_paths
answer_citations
audit_logs
agent_tasks
```

当前仓库已经提供只读查询工具保护，后续可继续补充 schema 和迁移脚本。

### 6. 启动后端

```bash
uv run uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload
```

主要接口：

| 接口 | 说明 |
| --- | --- |
| `POST /api/task` | 启动一次 DeepAgents 后台任务 |
| `POST /api/task/{thread_id}/cancel` | 取消指定会话任务 |
| `POST /api/upload` | 上传文件到当前会话 |
| `GET /api/files` | 列出当前会话输出文件 |
| `GET /api/download` | 下载输出文件 |
| `WebSocket /ws/{thread_id}` | 推送工具调用、助手调用、结果和异常事件 |
| `POST /api/v1/tasks/qa` | 标准问答任务接口 |
| `POST /api/v1/documents/upload` | 标准文档上传接口 |
| `GET /api/v1/datasets` | 查询可访问知识库 |

### 7. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

默认连接：

```text
API: http://localhost:8000
WS:  ws://localhost:8000
```

如需修改，可以在 `frontend/.env.local` 中配置：

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

## 示例任务

```text
查询医疗器械临床评价路径中，某类产品是否通常需要开展临床试验，并列出依据。
```

```text
根据指导原则和审评报告，总结无源植入器械注册申报资料的重点关注项。
```

```text
查询某个注册证编号对应的产品名称、注册人、批准日期和有效期。
```

```text
读取我上传的申报资料，整理一份注册资料缺口分析 Markdown 报告。
```

```text
结合共性问题和审评报告，总结某类产品常见补正问题，并给出引用来源。
```

## 当前能力边界

当前工程已经具备多智能体调度、RAGFlow 调用、MySQL 只读查询工具、文件上传读取、Markdown/PDF 生成、WebSocket 状态推送和外包对接 API 雏形。

仍需继续完善的生产能力包括：

1. MySQL schema 和迁移脚本。
2. 数据预处理后的全量导入和增量更新。
3. RAGFlow retrieve 级别的结构化证据返回。
4. `answer_citations` 引用落库和前端引用展开。
5. 用户登录、工作区、角色和权限系统。
6. Redis 队列、限流和任务持久化。
7. 自动化验证集和召回质量评估。
8. 生产监控、告警、备份和容灾。

## 开发约定

1. 不提交 `.env`、虚拟环境、构建产物、`app/output` 和用户上传文件。
2. 涉及数据库查询工具时，必须保持只读保护。
3. 涉及 RAGFlow 检索时，必须保留来源信息。
4. 涉及用户资料时，必须按公共、工作区、用户私有三层隔离。
5. 文档、提示词和接口说明要保持医疗器械注册知识库口径一致。
