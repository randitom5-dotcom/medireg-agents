# MediReg Agents 数据库结构报告

## 1. 数据库概览

当前项目使用的 MySQL 数据库为：

```text
数据库名：medireg_db
用途：存储医疗器械注册业务中的结构化数据、文档元数据、RAGFlow 数据集映射、上传文件记录和智能体任务记录。
```

数据库与 RAGFlow 的职责分工如下：

| 类型 | 承载系统 | 说明 |
| --- | --- | --- |
| 结构化注册数据 | MySQL | 注册证、产品名称、注册人、管理类别、有效期、临床评价路径等 |
| 非结构化文档内容 | RAGFlow | 法规、指导原则、审评报告、共性问题、公告正文、上传资料正文等 |
| 文档元数据 | MySQL | 文档标题、来源、发布日期、本地路径、RAGFlow dataset 映射 |
| 任务和上传文件记录 | MySQL | 智能体任务、用户上传文件、会话线程等运行数据 |

## 2. 表清单

| 表名 | 说明 |
| --- | --- |
| `registered_medical_devices` | 医疗器械注册证和产品注册信息 |
| `registration_announcements` | 医疗器械注册批准公告 |
| `clinical_evaluation_paths` | 临床评价路径推荐和判断依据 |
| `regulatory_documents` | 法规、指导原则、审评报告、共性问题等文档元数据 |
| `knowledge_datasets` | RAGFlow 知识库数据集映射 |
| `documents` | 文档元数据简表，便于数据库工具调试 |
| `uploaded_files` | 用户上传文件记录 |
| `agent_tasks` | 智能体任务记录 |

## 3. 核心业务表

### 3.1 registered_medical_devices

用于保存医疗器械注册证和产品注册信息，是结构化查询的核心表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `registration_certificate_no` | `VARCHAR(80)` | 注册证编号，唯一 |
| `product_name` | `VARCHAR(255)` | 产品名称 |
| `registrant_name` | `VARCHAR(255)` | 注册人 |
| `agent_name` | `VARCHAR(255)` | 代理人 |
| `management_category` | `VARCHAR(20)` | 管理类别 |
| `classification_code` | `VARCHAR(50)` | 医疗器械分类编码 |
| `approval_date` | `DATE` | 批准日期 |
| `expiry_date` | `DATE` | 有效期 |
| `product_structure` | `TEXT` | 产品结构组成 |
| `intended_use` | `TEXT` | 适用范围或预期用途 |
| `approval_department` | `VARCHAR(100)` | 审批部门 |
| `status` | `VARCHAR(50)` | 注册证状态，默认 `valid` |
| `source_title` | `VARCHAR(255)` | 来源标题 |
| `source_url` | `VARCHAR(500)` | 来源 URL |
| `created_at` | `TIMESTAMP` | 创建时间 |
| `updated_at` | `TIMESTAMP` | 更新时间 |

典型问题：

```text
南京鼎世医疗器械有限公司有哪些注册产品？
某个注册证编号对应的产品名称、注册人和有效期是什么？
哪些三类医疗器械注册证即将到期？
```

### 3.2 registration_announcements

用于保存医疗器械注册批准公告，与注册证表通过注册证编号关联。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `announcement_no` | `VARCHAR(120)` | 公告编号 |
| `title` | `VARCHAR(255)` | 公告标题 |
| `source_org` | `VARCHAR(120)` | 发布机构 |
| `publish_date` | `DATE` | 发布日期 |
| `source_url` | `VARCHAR(500)` | 来源 URL |
| `file_name` | `VARCHAR(255)` | 文件名 |
| `local_path` | `VARCHAR(500)` | 本地路径 |
| `related_certificate_no` | `VARCHAR(80)` | 关联注册证编号 |
| `summary` | `TEXT` | 公告摘要 |
| `created_at` | `TIMESTAMP` | 创建时间 |

关系：

```text
registration_announcements.related_certificate_no
  -> registered_medical_devices.registration_certificate_no
```

### 3.3 clinical_evaluation_paths

用于保存不同产品类别的临床评价路径、是否通常需要临床试验及判断依据。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `product_category` | `VARCHAR(255)` | 产品类别 |
| `classification_code` | `VARCHAR(50)` | 分类编码 |
| `management_category` | `VARCHAR(20)` | 管理类别 |
| `recommended_path` | `VARCHAR(120)` | 推荐临床评价路径 |
| `clinical_trial_required` | `VARCHAR(50)` | 是否通常需要临床试验 |
| `comparison_basis` | `TEXT` | 同品种比对依据 |
| `evidence_requirements` | `TEXT` | 证据资料要求 |
| `risk_notes` | `TEXT` | 风险提示 |
| `basis_document_title` | `VARCHAR(255)` | 依据文件标题 |
| `basis_document_url` | `VARCHAR(500)` | 依据文件 URL |
| `effective_date` | `DATE` | 生效日期 |
| `created_at` | `TIMESTAMP` | 创建时间 |

典型问题：

```text
一次性使用无菌注射器通常需要开展临床试验吗？
医用外科口罩适合走哪种临床评价路径？
某类产品进行同品种比对时需要准备哪些证据？
```

## 4. 文档与知识库表

### 4.1 regulatory_documents

用于保存法规、指导原则、审评报告、共性问题等文档元数据。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `document_id` | `VARCHAR(80)` | 文档 ID，唯一 |
| `title` | `VARCHAR(255)` | 文档标题 |
| `source_org` | `VARCHAR(120)` | 来源机构 |
| `source_type` | `VARCHAR(80)` | 文档类型 |
| `publish_date` | `DATE` | 发布日期 |
| `effective_date` | `DATE` | 生效日期 |
| `source_url` | `VARCHAR(500)` | 来源 URL |
| `file_name` | `VARCHAR(255)` | 文件名 |
| `local_path` | `VARCHAR(500)` | 本地路径 |
| `ragflow_dataset_name` | `VARCHAR(120)` | 对应 RAGFlow 数据集 |
| `summary` | `TEXT` | 摘要 |
| `status` | `VARCHAR(50)` | 文档状态，默认 `effective` |
| `created_at` | `TIMESTAMP` | 创建时间 |

### 4.2 knowledge_datasets

用于维护 RAGFlow 数据集与业务范围的映射。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `dataset_name` | `VARCHAR(120)` | 数据集名称，唯一 |
| `dataset_scope` | `VARCHAR(50)` | 数据集范围，如 `public`、`workspace`、`private` |
| `owner_workspace_id` | `VARCHAR(120)` | 工作区 ID |
| `owner_user_id` | `VARCHAR(120)` | 用户 ID |
| `description` | `TEXT` | 数据集说明 |
| `source_types` | `VARCHAR(255)` | 数据来源类型 |
| `created_at` | `TIMESTAMP` | 创建时间 |
| `updated_at` | `TIMESTAMP` | 更新时间 |

关系：

```text
regulatory_documents.ragflow_dataset_name
  -> knowledge_datasets.dataset_name

documents.ragflow_dataset_name
  -> knowledge_datasets.dataset_name
```

### 4.3 documents

文档元数据简表，主要用于本地调试和数据库工具快速预览。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `document_id` | `VARCHAR(80)` | 文档 ID，唯一 |
| `title` | `VARCHAR(255)` | 标题 |
| `source_type` | `VARCHAR(80)` | 文档类型 |
| `ragflow_dataset_name` | `VARCHAR(120)` | 对应 RAGFlow 数据集 |
| `source_url` | `VARCHAR(500)` | 来源 URL |
| `local_path` | `VARCHAR(500)` | 本地路径 |
| `summary` | `TEXT` | 摘要 |
| `created_at` | `TIMESTAMP` | 创建时间 |

## 5. 运行数据表

### 5.1 uploaded_files

用于记录用户上传文件。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `file_id` | `VARCHAR(80)` | 文件 ID，唯一 |
| `workspace_id` | `VARCHAR(120)` | 工作区 ID |
| `user_id` | `VARCHAR(120)` | 用户 ID |
| `thread_id` | `VARCHAR(120)` | 会话线程 ID |
| `original_file_name` | `VARCHAR(255)` | 原始文件名 |
| `storage_path` | `VARCHAR(500)` | 存储路径 |
| `mime_type` | `VARCHAR(120)` | MIME 类型 |
| `file_size` | `BIGINT` | 文件大小 |
| `parse_status` | `VARCHAR(50)` | 解析状态 |
| `created_at` | `TIMESTAMP` | 创建时间 |

### 5.2 agent_tasks

用于记录智能体任务，后续可替代当前内存任务存储。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 主键 |
| `task_id` | `VARCHAR(120)` | 任务 ID，唯一 |
| `thread_id` | `VARCHAR(120)` | 会话线程 ID |
| `workspace_id` | `VARCHAR(120)` | 工作区 ID |
| `user_id` | `VARCHAR(120)` | 用户 ID |
| `task_type` | `VARCHAR(50)` | 任务类型 |
| `query_text` | `TEXT` | 用户问题或任务内容 |
| `status` | `VARCHAR(50)` | 任务状态 |
| `output_dir` | `VARCHAR(500)` | 输出目录 |
| `error_message` | `TEXT` | 错误信息 |
| `created_at` | `TIMESTAMP` | 创建时间 |
| `updated_at` | `TIMESTAMP` | 更新时间 |

关系：

```text
uploaded_files.thread_id
  -> agent_tasks.thread_id
```

## 6. 当前样例数据

当前初始化脚本已写入少量演示数据，便于数据库查询智能体测试。

### 6.1 注册产品样例

| 注册证编号 | 产品名称 | 注册人 |
| --- | --- | --- |
| `国械注准20243140001` | 一次性使用无菌注射器 带针 | 南京鼎世医疗器械有限公司 |
| `苏械注准20232140088` | 医用外科口罩 | 江苏康瑞医疗科技有限公司 |
| `国械注进20233070066` | 全自动生化分析仪 | Global Diagnostics GmbH |

### 6.2 临床评价路径样例

| 产品类别 | 推荐路径 | 是否通常需要临床试验 |
| --- | --- | --- |
| 一次性使用无菌注射器 | 同品种医疗器械临床评价 | 通常不需要 |
| 医用外科口罩 | 免于临床评价目录或同品种比对 | 通常不需要 |
| 全自动生化分析仪 | 同品种医疗器械临床评价 | 视差异情况确定 |

## 7. 查询智能体使用方式

数据库查询助手当前提供三个只读工具：

| 工具 | 作用 |
| --- | --- |
| `list_sql_tables` | 列出当前数据库中的可用表 |
| `get_table_data` | 查看指定表前 100 行，用于理解字段和样例数据 |
| `execute_sql_query` | 执行只读 SQL 查询，支持筛选、聚合、排序、联表 |

建议查询流程：

```text
1. 先调用 list_sql_tables 确认真实表名。
2. 再调用 get_table_data 预览相关表字段。
3. 最后调用 execute_sql_query 执行精确查询。
```

## 8. 后续建议

1. 将真实 NMPA/CMDE 抓取结果导入 `registered_medical_devices`、`registration_announcements` 和 `regulatory_documents`。
2. 将临床评价路径清洗结果导入 `clinical_evaluation_paths`。
3. 为 `agent_tasks` 和 `uploaded_files` 接入后端运行逻辑，替代当前部分内存状态。
4. 后续可增加 `answer_citations` 表，用于保存回答引用来源。
5. 后续可增加 `structured_table_rows` 表，用于承接从 Excel、公告附件中抽取出的结构化行数据。
