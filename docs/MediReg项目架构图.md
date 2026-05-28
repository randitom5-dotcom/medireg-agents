# MediReg Agents 项目架构图

## 1. 总体架构

```mermaid
flowchart TB
    User[用户 / 注册业务人员]

    subgraph Frontend[前端层 React + Vite + Ant Design]
        UI[医疗器械注册问答工作台]
        UploadPanel[文件上传面板]
        ChatPanel[对话与结果展示]
        FileDock[报告与附件下载]
        EventView[工具调用 / 子智能体事件流]
    end

    subgraph API[后端接入层 FastAPI]
        RestAPI[HTTP API\n任务提交 / 文件上传 / 文件列表 / 下载]
        WsAPI[WebSocket\n实时推送执行状态]
        V1API[/api/v1 标准集成接口]
        Monitor[monitor 事件总线]
        TaskStore[任务状态管理\n当前为内存存储]
    end

    subgraph Agent[智能体编排层 DeepAgents]
        MainAgent[主智能体 main_agent\n任务规划 / 工具选择 / 汇总输出]
        DBAgent[数据库查询子智能体]
        KBAgent[RAGFlow 知识库子智能体]
        WebAgent[网络搜索子智能体]
    end

    subgraph Tools[工具层]
        DBTools[MySQL 查询工具\nlist_sql_tables / get_table_data / execute_sql_query]
        RagflowTools[RAGFlow 工具\nget_assistant_list / create_ask_delete]
        TavilyTool[网络搜索工具\nTavily]
        ReadFileTool[上传文件读取工具\nPDF / DOCX / Excel / Markdown / Text]
        MarkdownTool[Markdown 报告生成工具]
        PdfTool[Markdown 转 PDF 工具]
    end

    subgraph Data[数据与文件层]
        MySQL[(MySQL medireg_db\n结构化注册数据)]
        RAGFlow[(RAGFlow datasets\n法规 / 指导原则 / 审评报告 / 共性问题)]
        Uploaded[(app/updated\n上传文件暂存)]
        Output[(app/output/session_xxx\n会话输出目录)]
        Reports[(reports\n运行生成报告 / 阶段分析)]
        Docker[(Docker MySQL\n本地结构化数据库)]
    end

    User --> UI
    UI --> UploadPanel
    UI --> ChatPanel
    UI --> FileDock
    UI --> EventView

    UploadPanel --> RestAPI
    ChatPanel --> RestAPI
    FileDock --> RestAPI
    EventView --> WsAPI

    RestAPI --> TaskStore
    RestAPI --> MainAgent
    WsAPI --> Monitor
    V1API --> TaskStore
    V1API --> MainAgent

    MainAgent --> DBAgent
    MainAgent --> KBAgent
    MainAgent --> WebAgent
    MainAgent --> ReadFileTool
    MainAgent --> MarkdownTool
    MainAgent --> PdfTool

    DBAgent --> DBTools
    KBAgent --> RagflowTools
    WebAgent --> TavilyTool

    DBTools --> MySQL
    RagflowTools --> RAGFlow
    ReadFileTool --> Uploaded
    ReadFileTool --> Output
    MarkdownTool --> Output
    PdfTool --> Output
    Reports -.项目文档归档.-> UI
    Docker --> MySQL

    MainAgent --> Monitor
    DBAgent --> Monitor
    KBAgent --> Monitor
    WebAgent --> Monitor
    Tools --> Monitor
    Monitor --> WsAPI
```

## 2. 智能体结构

```mermaid
flowchart LR
    UserTask[用户任务]
    Main[主智能体\nmain_agent.py]

    subgraph Subagents[子智能体]
        DB[数据库查询助手\ndatabase_query_agent.py]
        KB[RAGFlow 知识库助手\nknowledge_base_agent.py]
        Web[网络搜索助手\nnetwork_search_agent.py]
    end

    subgraph MainTools[主智能体直属工具]
        Read[read_file_content\n读取上传文件]
        MD[generate_markdown\n生成 Markdown]
        PDF[convert_md_to_pdf\n转换 PDF]
    end

    subgraph DBTools[数据库工具]
        ListTables[list_sql_tables]
        Preview[get_table_data]
        SQL[execute_sql_query]
    end

    subgraph KBTools[RAGFlow 工具]
        ListAssistants[get_assistant_list]
        AskRagflow[create_ask_delete]
    end

    subgraph WebTools[网络工具]
        Search[internet_search / Tavily]
    end

    UserTask --> Main

    Main --> DB
    Main --> KB
    Main --> Web
    Main --> Read
    Main --> MD
    Main --> PDF

    DB --> ListTables
    DB --> Preview
    DB --> SQL

    KB --> ListAssistants
    KB --> AskRagflow

    Web --> Search
```

## 3. 数据流

```mermaid
sequenceDiagram
    participant U as 用户
    participant FE as React 前端
    participant API as FastAPI
    participant MA as 主智能体
    participant DB as 数据库子智能体
    participant KB as RAGFlow 子智能体
    participant WEB as 网络搜索子智能体
    participant OUT as output/reports
    participant WS as WebSocket

    U->>FE: 输入注册业务问题或上传资料
    FE->>API: POST /api/task 或 /api/v1/tasks/qa
    API->>MA: run_deep_agent(query, thread_id)
    API-->>FE: 返回 thread_id
    FE->>WS: 订阅 /ws/{thread_id}

    MA->>DB: 结构化注册数据查询
    DB->>DB: list_sql_tables / get_table_data / execute_sql_query
    DB-->>MA: 注册证、产品、临床评价路径等结构化结果

    MA->>KB: 法规、指导原则、审评资料检索
    KB-->>MA: RAGFlow 召回内容和依据

    MA->>WEB: 必要时检索公开网页
    WEB-->>MA: 网络搜索结果

    MA->>OUT: 生成 Markdown / PDF 报告
    MA-->>API: 最终回答或报告路径
    API->>WS: 推送工具调用、子智能体进度和结果
    WS-->>FE: 实时展示执行过程
    FE-->>U: 展示回答、引用和可下载文件
```

## 4. 数据库结构关系

```mermaid
erDiagram
    registered_medical_devices {
        bigint id PK
        varchar registration_certificate_no UK
        varchar product_name
        varchar registrant_name
        varchar management_category
        varchar classification_code
        date approval_date
        date expiry_date
        text intended_use
    }

    registration_announcements {
        bigint id PK
        varchar announcement_no
        varchar title
        varchar source_org
        date publish_date
        varchar related_certificate_no FK
        text summary
    }

    clinical_evaluation_paths {
        bigint id PK
        varchar product_category
        varchar classification_code
        varchar recommended_path
        varchar clinical_trial_required
        text evidence_requirements
        text risk_notes
    }

    regulatory_documents {
        bigint id PK
        varchar document_id UK
        varchar title
        varchar source_type
        date publish_date
        varchar ragflow_dataset_name
        text summary
    }

    knowledge_datasets {
        bigint id PK
        varchar dataset_name UK
        varchar dataset_scope
        varchar owner_workspace_id
        varchar owner_user_id
        varchar source_types
    }

    documents {
        bigint id PK
        varchar document_id UK
        varchar title
        varchar source_type
        varchar ragflow_dataset_name
        varchar local_path
    }

    uploaded_files {
        bigint id PK
        varchar file_id UK
        varchar workspace_id
        varchar user_id
        varchar thread_id
        varchar original_file_name
        varchar storage_path
    }

    agent_tasks {
        bigint id PK
        varchar task_id UK
        varchar thread_id
        varchar workspace_id
        varchar user_id
        varchar task_type
        varchar status
    }

    registered_medical_devices ||--o{ registration_announcements : "registration_certificate_no"
    knowledge_datasets ||--o{ regulatory_documents : "dataset_name"
    knowledge_datasets ||--o{ documents : "dataset_name"
    agent_tasks ||--o{ uploaded_files : "thread_id"
```

## 5. 目录职责

```text
medireg-agents/
├── app/
│   ├── agent/                 主智能体、子智能体和模型配置
│   ├── api/                   FastAPI 接口、WebSocket、任务状态、监控事件
│   ├── prompt/                prompts.yml，主智能体和子智能体提示词
│   ├── rawflow/               RAGFlow 配置
│   ├── tools/                 MySQL、RAGFlow、Tavily、文件读取、报告生成工具
│   ├── utils/                 路径解析、Markdown/PDF 转换等工具函数
│   ├── output/                运行时输出目录，每个 session 单独存放
│   └── updated/               用户上传文件暂存目录
├── frontend/                  React 前端工作台
├── docker/                    本地 MySQL 环境和初始化 SQL
├── scripts/                   知识库清洗、导入和预处理脚本
├── docs/                      长期维护的架构、方案、接口、数据库和验证文档
├── reports/                   运行生成报告、阶段性分析和临时交付件
└── examples/                  DeepAgents 示例、RAGFlow SDK demo 和本地测试材料
```

## 6. 当前关键运行链路

```text
用户问题
  -> React 前端提交任务
  -> FastAPI 创建后台任务
  -> main_agent 调度 DeepAgents
  -> 根据任务选择：
       1. MySQL 查询结构化注册数据
       2. RAGFlow 检索法规和文档证据
       3. Tavily 查询公开网页
       4. read_file_content 读取上传资料
  -> 主智能体汇总证据和结论
  -> 可选生成 Markdown / PDF
  -> WebSocket 推送过程和结果
  -> 前端展示回答、事件和输出文件
```
