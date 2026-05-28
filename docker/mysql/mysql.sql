-- MediReg Agents medical device registration database
--
-- This script initializes the local MySQL instance used by the database
-- query agent. It stores structured medical-device registration data that
-- complements RAGFlow's unstructured document retrieval.
--
-- Docker note:
-- The official MySQL image executes files under /docker-entrypoint-initdb.d
-- only when /var/lib/mysql is empty. If a volume already exists, recreate the
-- volume before expecting this script to run again.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS medireg_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;
USE medireg_db;

-- Registration certificates and product registration facts.
CREATE TABLE IF NOT EXISTS registered_medical_devices (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    registration_certificate_no VARCHAR(80) NOT NULL UNIQUE,
    product_name VARCHAR(255) NOT NULL,
    registrant_name VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255),
    management_category VARCHAR(20),
    classification_code VARCHAR(50),
    approval_date DATE,
    expiry_date DATE,
    product_structure TEXT,
    intended_use TEXT,
    approval_department VARCHAR(100),
    status VARCHAR(50) DEFAULT 'valid',
    source_title VARCHAR(255),
    source_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_registered_devices_product_name (product_name),
    INDEX idx_registered_devices_registrant (registrant_name),
    INDEX idx_registered_devices_category (management_category),
    INDEX idx_registered_devices_expiry (expiry_date)
) COMMENT='医疗器械注册证和产品注册信息';

-- Public approval announcement batches from NMPA or provincial regulators.
CREATE TABLE IF NOT EXISTS registration_announcements (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    announcement_no VARCHAR(120),
    title VARCHAR(255) NOT NULL,
    source_org VARCHAR(120),
    publish_date DATE,
    source_url VARCHAR(500),
    file_name VARCHAR(255),
    local_path VARCHAR(500),
    related_certificate_no VARCHAR(80),
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_announcements_publish_date (publish_date),
    INDEX idx_announcements_certificate (related_certificate_no),
    CONSTRAINT fk_announcements_certificate
        FOREIGN KEY (related_certificate_no)
        REFERENCES registered_medical_devices (registration_certificate_no)
        ON DELETE SET NULL
) COMMENT='医疗器械注册批准公告';

-- Clinical evaluation path recommendations for product categories.
CREATE TABLE IF NOT EXISTS clinical_evaluation_paths (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    product_category VARCHAR(255) NOT NULL,
    classification_code VARCHAR(50),
    management_category VARCHAR(20),
    recommended_path VARCHAR(120) NOT NULL,
    clinical_trial_required VARCHAR(50) NOT NULL,
    comparison_basis TEXT,
    evidence_requirements TEXT,
    risk_notes TEXT,
    basis_document_title VARCHAR(255),
    basis_document_url VARCHAR(500),
    effective_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_clinical_paths_category (product_category),
    INDEX idx_clinical_paths_code (classification_code),
    INDEX idx_clinical_paths_trial (clinical_trial_required)
) COMMENT='临床评价路径推荐和判断依据';

-- Metadata for regulations, guidelines, review reports and common questions.
CREATE TABLE IF NOT EXISTS regulatory_documents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    document_id VARCHAR(80) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    source_org VARCHAR(120),
    source_type VARCHAR(80) NOT NULL,
    publish_date DATE,
    effective_date DATE,
    source_url VARCHAR(500),
    file_name VARCHAR(255),
    local_path VARCHAR(500),
    ragflow_dataset_name VARCHAR(120),
    summary TEXT,
    status VARCHAR(50) DEFAULT 'effective',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_regulatory_documents_type (source_type),
    INDEX idx_regulatory_documents_publish_date (publish_date),
    INDEX idx_regulatory_documents_dataset (ragflow_dataset_name)
) COMMENT='法规、指导原则、审评报告、共性问题等文档元数据';

-- RAGFlow dataset mapping for routing and traceability.
CREATE TABLE IF NOT EXISTS knowledge_datasets (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    dataset_name VARCHAR(120) NOT NULL UNIQUE,
    dataset_scope VARCHAR(50) NOT NULL,
    owner_workspace_id VARCHAR(120),
    owner_user_id VARCHAR(120),
    description TEXT,
    source_types VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_knowledge_datasets_scope (dataset_scope)
) COMMENT='RAGFlow 知识库数据集映射';

-- User-uploaded files copied into task sessions.
CREATE TABLE IF NOT EXISTS uploaded_files (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    file_id VARCHAR(80) NOT NULL UNIQUE,
    workspace_id VARCHAR(120) NOT NULL DEFAULT 'default',
    user_id VARCHAR(120) NOT NULL DEFAULT 'anonymous',
    thread_id VARCHAR(120),
    original_file_name VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    mime_type VARCHAR(120),
    file_size BIGINT,
    parse_status VARCHAR(50) DEFAULT 'uploaded',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_uploaded_files_owner (workspace_id, user_id),
    INDEX idx_uploaded_files_thread (thread_id)
) COMMENT='用户上传文件记录';

-- Agent task metadata for future persistence beyond the in-memory store.
CREATE TABLE IF NOT EXISTS agent_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id VARCHAR(120) NOT NULL UNIQUE,
    thread_id VARCHAR(120) NOT NULL,
    workspace_id VARCHAR(120) NOT NULL DEFAULT 'default',
    user_id VARCHAR(120) NOT NULL DEFAULT 'anonymous',
    task_type VARCHAR(50) NOT NULL,
    query_text TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    output_dir VARCHAR(500),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_agent_tasks_owner (workspace_id, user_id),
    INDEX idx_agent_tasks_status (status),
    INDEX idx_agent_tasks_thread (thread_id)
) COMMENT='智能体任务记录';

-- A compact compatibility table for quick document previews in local tests.
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    document_id VARCHAR(80) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    source_type VARCHAR(80) NOT NULL,
    ragflow_dataset_name VARCHAR(120),
    source_url VARCHAR(500),
    local_path VARCHAR(500),
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) COMMENT='文档元数据简表，便于数据库工具调试';

INSERT INTO knowledge_datasets
    (dataset_name, dataset_scope, owner_workspace_id, owner_user_id, description, source_types)
VALUES
    ('mdr_public_guidelines', 'public', NULL, NULL, '医疗器械法规、指导原则和技术审查要求', '法规,指导原则,技术审查要求'),
    ('mdr_public_review_reports', 'public', NULL, NULL, '公开审评报告和审评关注点资料', '审评报告'),
    ('mdr_public_common_questions', 'public', NULL, NULL, '监管机构共性问题、交流园地和补正问题资料', '共性问题,交流园地'),
    ('mdr_public_clinical_eval', 'public', NULL, NULL, '临床评价路径、同品种比对和临床试验判断资料', '临床评价')
ON DUPLICATE KEY UPDATE
    description = VALUES(description),
    source_types = VALUES(source_types),
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO registered_medical_devices
    (
        registration_certificate_no,
        product_name,
        registrant_name,
        agent_name,
        management_category,
        classification_code,
        approval_date,
        expiry_date,
        product_structure,
        intended_use,
        approval_department,
        status,
        source_title,
        source_url
    )
VALUES
    (
        '国械注准20243140001',
        '一次性使用无菌注射器 带针',
        '南京鼎世医疗器械有限公司',
        NULL,
        'III',
        '14-01',
        '2024-01-12',
        '2029-01-11',
        '由外套、芯杆、活塞和注射针组成，经环氧乙烷灭菌。',
        '用于人体皮下、肌肉、静脉注射药液或抽取血液。',
        '国家药品监督管理局',
        'valid',
        '医疗器械批准注册产品公告示例',
        'https://www.nmpa.gov.cn/'
    ),
    (
        '苏械注准20232140088',
        '医用外科口罩',
        '江苏康瑞医疗科技有限公司',
        NULL,
        'II',
        '14-13',
        '2023-06-20',
        '2028-06-19',
        '由口罩体、鼻夹和口罩带组成，非无菌提供。',
        '供临床医务人员在有创操作过程中佩戴，覆盖使用者口、鼻及下颌。',
        '江苏省药品监督管理局',
        'valid',
        '江苏省医疗器械注册公告示例',
        'https://da.jiangsu.gov.cn/'
    ),
    (
        '国械注进20233070066',
        '全自动生化分析仪',
        'Global Diagnostics GmbH',
        '上海康检医疗器械有限公司',
        'II',
        '22-02',
        '2023-09-08',
        '2028-09-07',
        '由分析模块、样本模块、试剂模块、控制软件和附件组成。',
        '用于医疗机构对人体样本中的生化项目进行定量检测。',
        '国家药品监督管理局',
        'valid',
        '进口医疗器械注册公告示例',
        'https://www.nmpa.gov.cn/'
    )
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name),
    registrant_name = VALUES(registrant_name),
    expiry_date = VALUES(expiry_date),
    status = VALUES(status),
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO registration_announcements
    (
        announcement_no,
        title,
        source_org,
        publish_date,
        source_url,
        file_name,
        local_path,
        related_certificate_no,
        summary
    )
VALUES
    (
        '2024年第01号',
        '国家药监局关于批准注册医疗器械产品公告示例',
        '国家药品监督管理局',
        '2024-01-18',
        'https://www.nmpa.gov.cn/',
        '2024年第01号医疗器械批准注册产品公告.txt',
        'reports/NMPA医疗器械知识库爬虫方案.md',
        '国械注准20243140001',
        '公告包含一次性使用无菌注射器等产品的注册证编号、注册人和批准日期。'
    ),
    (
        '2023年第06号',
        '江苏省医疗器械注册批准公告示例',
        '江苏省药品监督管理局',
        '2023-06-25',
        'https://da.jiangsu.gov.cn/',
        '江苏省2023年第06号医疗器械注册公告.txt',
        'reports/医疗器械注册知识库数据预处理与建库方案.md',
        '苏械注准20232140088',
        '公告包含医用外科口罩等第二类医疗器械注册产品信息。'
    );

INSERT INTO clinical_evaluation_paths
    (
        product_category,
        classification_code,
        management_category,
        recommended_path,
        clinical_trial_required,
        comparison_basis,
        evidence_requirements,
        risk_notes,
        basis_document_title,
        basis_document_url,
        effective_date
    )
VALUES
    (
        '一次性使用无菌注射器',
        '14-01',
        'III',
        '同品种医疗器械临床评价',
        '通常不需要',
        '可结合同品种产品注册信息、产品技术要求、适用范围和性能指标进行等同性论证。',
        '产品技术要求、检验报告、同品种比对资料、临床使用数据或文献资料。',
        '如结构材料、预期用途或关键性能与同品种存在显著差异，应补充临床证据。',
        '决策是否开展医疗器械临床试验技术指导原则',
        'https://www.cmde.org.cn/',
        '2021-09-16'
    ),
    (
        '医用外科口罩',
        '14-13',
        'II',
        '免于临床评价目录或同品种比对',
        '通常不需要',
        '关注产品适用标准、过滤效率、压力差、微生物指标和灭菌状态。',
        '检验报告、产品技术要求、生产工艺说明、同品种比对资料。',
        '若宣称特殊防护性能或使用场景超出常规口罩，应重新评估临床证据需求。',
        '列入免于进行临床评价医疗器械目录产品对比说明技术指导原则',
        'https://www.cmde.org.cn/',
        '2021-09-16'
    ),
    (
        '全自动生化分析仪',
        '22-02',
        'II',
        '同品种医疗器械临床评价',
        '视差异情况确定',
        '重点比较检测原理、检测项目、样本类型、性能指标、软件功能和适配试剂。',
        '分析性能评估、同品种比对、临床样本比对、软件验证和风险管理资料。',
        '新增检测项目、算法或关键性能差异较大时，可能需要补充临床试验或临床样本验证。',
        '体外诊断设备临床评价相关指导原则',
        'https://www.cmde.org.cn/',
        '2022-01-01'
    );

INSERT INTO regulatory_documents
    (
        document_id,
        title,
        source_org,
        source_type,
        publish_date,
        effective_date,
        source_url,
        file_name,
        local_path,
        ragflow_dataset_name,
        summary,
        status
    )
VALUES
    (
        'DOC-CMDE-CLINICAL-001',
        '决策是否开展医疗器械临床试验技术指导原则',
        '国家药监局医疗器械技术审评中心',
        '指导原则',
        '2021-09-16',
        '2021-09-16',
        'https://www.cmde.org.cn/',
        '决策是否开展医疗器械临床试验技术指导原则.txt',
        'reports/医疗器械注册知识库数据预处理与建库方案.md',
        'mdr_public_clinical_eval',
        '用于判断申报产品是否需要开展临床试验，以及如何使用同品种比对、临床文献和临床数据形成证据链。',
        'effective'
    ),
    (
        'DOC-NMPA-REG-001',
        '医疗器械注册与备案管理办法',
        '国家市场监督管理总局',
        '法规',
        '2021-08-26',
        '2021-10-01',
        'https://www.nmpa.gov.cn/',
        '医疗器械注册与备案管理办法.txt',
        'reports/医疗器械注册知识库搭建与召回方案报告.md',
        'mdr_public_guidelines',
        '规定医疗器械注册、备案、变更、延续、监督管理等基本要求。',
        'effective'
    ),
    (
        'DOC-CMDE-COMMON-001',
        '医疗器械注册申报资料常见补正问题示例',
        '国家药监局医疗器械技术审评中心',
        '共性问题',
        '2024-03-01',
        NULL,
        'https://www.cmde.org.cn/',
        '医疗器械注册申报资料常见补正问题示例.txt',
        'reports/医疗器械注册资料分析报告.md',
        'mdr_public_common_questions',
        '归纳产品技术要求、检验报告、说明书、临床评价和风险管理资料中的常见补正点。',
        'reference'
    )
ON DUPLICATE KEY UPDATE
    title = VALUES(title),
    source_type = VALUES(source_type),
    ragflow_dataset_name = VALUES(ragflow_dataset_name),
    summary = VALUES(summary);

INSERT INTO documents
    (document_id, title, source_type, ragflow_dataset_name, source_url, local_path, summary)
SELECT
    document_id,
    title,
    source_type,
    ragflow_dataset_name,
    source_url,
    local_path,
    summary
FROM regulatory_documents
ON DUPLICATE KEY UPDATE
    title = VALUES(title),
    source_type = VALUES(source_type),
    ragflow_dataset_name = VALUES(ragflow_dataset_name),
    summary = VALUES(summary);
