"""Clean crawled medical-device knowledge-base files and import metadata.

This script keeps the source corpus read-only. It performs three jobs:
1. Build a file inventory with hashes and quality status.
2. Normalize NMPA registration `detail_*.json` records.
3. Import cleaned structured records and document metadata into MySQL.

Examples:
    python scripts/clean_and_import_medical_device_kb.py --source "D:\\work\\爬取的知识库数据" --dry-run
    python scripts/clean_and_import_medical_device_kb.py --source "D:\\work\\爬取的知识库数据" --execute
    python scripts/clean_and_import_medical_device_kb.py --source "D:\\work\\爬取的知识库数据\\药品监督管理局数据查询" --execute --limit 100
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from mysql.connector import connect


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "app" / "output" / "medical_device_kb_ingest"
SUPPORTED_RAGFLOW_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}
STRUCTURED_EXTENSIONS = {".json", ".csv", ".xls", ".xlsx"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}


FIELD_ALIASES = {
    "registration_certificate_number": ["注册证编号", "注册证号", "批准文号"],
    "registrant_name": ["注册人名称", "申请人名称", "企业名称"],
    "registrant_address": ["注册人住所", "住所"],
    "production_address": ["生产地址"],
    "product_name": ["产品名称", "名称"],
    "management_category": ["管理类别"],
    "model_specification": ["型号规格", "型号、规格"],
    "structure_composition": ["结构及组成/主要组成成分", "结构及组成", "主要组成成分"],
    "intended_use": ["适用范围/预期用途", "适用范围", "预期用途"],
    "storage_validity": ["产品储存条件及有效期", "储存条件及有效期"],
    "attachments": ["附件"],
    "other_content": ["其他内容"],
    "remarks": ["备注"],
    "approval_department": ["审批部门", "批准部门"],
    "approval_date": ["批准日期"],
    "effective_date": ["生效日期"],
    "expiry_date": ["有效期至"],
    "change_history": ["变更情况"],
}


@dataclass
class FileInventoryItem:
    source_path: str
    relative_path: str
    top_category: str
    extension: str
    kb_type: str
    size_bytes: int
    sha256: str
    status: str
    issue: str


@dataclass
class RegistrationRecord:
    business_key: str
    source_hash: str
    source_path: str
    relative_path: str
    source_category: str
    query_keyword: str
    source_url: str
    search_url: str
    page_no: str
    row_no: str
    crawl_status: str
    crawl_time: str | None
    registration_certificate_number: str
    product_name: str
    registrant_name: str
    registrant_address: str
    production_address: str
    management_category: str
    model_specification: str
    structure_composition: str
    intended_use: str
    storage_validity: str
    attachments: str
    other_content: str
    remarks: str
    approval_department: str
    approval_date: str | None
    effective_date: str | None
    expiry_date: str | None
    change_history: str
    raw_json: str
    searchable_text: str
    duplicate_count: int = 1


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = value.replace("\ufeff", "").replace("\u00a0", " ")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", value)
    value = re.sub(r"[ \t\r\n]+", " ", value).strip()
    return value


def parse_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def classify_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_RAGFLOW_EXTENSIONS:
        return "ragflow_document"
    if suffix in STRUCTURED_EXTENSIONS:
        return "structured_or_metadata"
    if suffix in ARCHIVE_EXTENSIONS:
        return "archive"
    return "other"


def inventory_files(source_root: Path) -> list[FileInventoryItem]:
    items: list[FileInventoryItem] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        try:
            stat = path.stat()
            digest = sha256_file(path)
            status = "PASS" if stat.st_size > 0 else "BLANK_FILE"
            issue = "" if stat.st_size > 0 else "zero byte file"
        except Exception as exc:
            stat = None
            digest = ""
            status = "UNREADABLE"
            issue = str(exc)

        items.append(
            FileInventoryItem(
                source_path=str(path),
                relative_path=str(relative),
                top_category=relative.parts[0] if relative.parts else "",
                extension=path.suffix.lower(),
                kb_type=classify_file(path),
                size_bytes=stat.st_size if stat else 0,
                sha256=digest,
                status=status,
                issue=issue,
            )
        )
    return items


def get_field(fields: dict[str, Any], canonical_name: str) -> str:
    for alias in FIELD_ALIASES[canonical_name]:
        if alias in fields:
            return clean_text(fields.get(alias))
    return ""


def category_from_relative(relative_path: Path) -> tuple[str, str]:
    parts = relative_path.parts
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def build_searchable_text(record: dict[str, Any], fields: dict[str, Any]) -> str:
    parts = [
        clean_text(record.get("_url")),
        get_field(fields, "registration_certificate_number"),
        get_field(fields, "product_name"),
        get_field(fields, "registrant_name"),
        get_field(fields, "management_category"),
        get_field(fields, "model_specification"),
        get_field(fields, "structure_composition"),
        get_field(fields, "intended_use"),
        get_field(fields, "approval_department"),
    ]
    return "\n".join(part for part in parts if part)


def iter_registration_records(source_root: Path) -> Iterable[RegistrationRecord]:
    for path in source_root.rglob("detail_*.json"):
        relative = path.relative_to(source_root)
        source_category, query_keyword = category_from_relative(relative)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue

        if isinstance(data, dict):
            units = data.items()
        elif isinstance(data, list):
            units = [(str(index), item) for index, item in enumerate(data)]
        else:
            continue

        for unit_key, unit in units:
            if not isinstance(unit, dict):
                continue
            fields = unit.get("fields") if isinstance(unit.get("fields"), dict) else {}
            cert_no = get_field(fields, "registration_certificate_number")
            source_url = clean_text(unit.get("_url"))
            raw_json = json.dumps(unit, ensure_ascii=False, sort_keys=True)
            source_hash = sha256_text(f"{path}|{unit_key}|{raw_json}")
            business_key = cert_no or source_url or source_hash

            yield RegistrationRecord(
                business_key=business_key,
                source_hash=source_hash,
                source_path=str(path),
                relative_path=str(relative),
                source_category=source_category,
                query_keyword=query_keyword,
                source_url=source_url,
                search_url=clean_text(unit.get("_search_url")),
                page_no=clean_text(unit.get("_page")),
                row_no=clean_text(unit.get("_row")),
                crawl_status=clean_text(unit.get("_status")),
                crawl_time=clean_text(unit.get("_time")) or None,
                registration_certificate_number=cert_no,
                product_name=get_field(fields, "product_name"),
                registrant_name=get_field(fields, "registrant_name"),
                registrant_address=get_field(fields, "registrant_address"),
                production_address=get_field(fields, "production_address"),
                management_category=get_field(fields, "management_category"),
                model_specification=get_field(fields, "model_specification"),
                structure_composition=get_field(fields, "structure_composition"),
                intended_use=get_field(fields, "intended_use"),
                storage_validity=get_field(fields, "storage_validity"),
                attachments=get_field(fields, "attachments"),
                other_content=get_field(fields, "other_content"),
                remarks=get_field(fields, "remarks"),
                approval_department=get_field(fields, "approval_department"),
                approval_date=parse_date(get_field(fields, "approval_date")),
                effective_date=parse_date(get_field(fields, "effective_date")),
                expiry_date=parse_date(get_field(fields, "expiry_date")),
                change_history=get_field(fields, "change_history"),
                raw_json=raw_json,
                searchable_text=build_searchable_text(unit, fields),
            )


def dedupe_records(records: Iterable[RegistrationRecord]) -> list[RegistrationRecord]:
    seen: dict[str, RegistrationRecord] = {}
    duplicates: Counter[str] = Counter()
    for record in records:
        key = record.business_key
        duplicates[key] += 1
        existing = seen.get(key)
        if existing is None:
            seen[key] = record
            continue
        if len(record.searchable_text) > len(existing.searchable_text):
            record.duplicate_count = existing.duplicate_count
            seen[key] = record
    for key, count in duplicates.items():
        seen[key].duplicate_count = count
    return list(seen.values())


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_db_config() -> dict[str, Any]:
    load_dotenv(PROJECT_ROOT / ".env")
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "deepsearch_db"),
        "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
        "collation": os.getenv("MYSQL_COLLATION", "utf8mb4_unicode_ci"),
        "autocommit": False,
    }


def ensure_tables(conn) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS medical_device_kb_ingest_runs (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            source_root VARCHAR(1024) NOT NULL,
            output_dir VARCHAR(1024) NOT NULL,
            file_count INT NOT NULL DEFAULT 0,
            registration_count INT NOT NULL DEFAULT 0,
            duplicate_registration_count INT NOT NULL DEFAULT 0,
            dry_run BOOLEAN NOT NULL DEFAULT TRUE,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP NULL
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS medical_device_kb_files (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            source_path VARCHAR(1024) NOT NULL,
            relative_path VARCHAR(1024) NOT NULL,
            top_category VARCHAR(255),
            extension VARCHAR(32),
            kb_type VARCHAR(64),
            size_bytes BIGINT NOT NULL DEFAULT 0,
            sha256 CHAR(64),
            status VARCHAR(64) NOT NULL,
            issue TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_kb_files_path (source_path(768)),
            KEY idx_kb_files_category (top_category),
            KEY idx_kb_files_hash (sha256),
            KEY idx_kb_files_type (kb_type)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS medical_device_registration_records (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            business_key VARCHAR(255) NOT NULL,
            source_hash CHAR(64) NOT NULL,
            source_path VARCHAR(1024) NOT NULL,
            relative_path VARCHAR(1024) NOT NULL,
            source_category VARCHAR(255),
            query_keyword VARCHAR(255),
            source_url TEXT,
            search_url TEXT,
            page_no VARCHAR(32),
            row_no VARCHAR(32),
            crawl_status VARCHAR(64),
            crawl_time VARCHAR(64),
            registration_certificate_number VARCHAR(128),
            product_name VARCHAR(512),
            registrant_name VARCHAR(512),
            registrant_address TEXT,
            production_address TEXT,
            management_category VARCHAR(128),
            model_specification TEXT,
            structure_composition MEDIUMTEXT,
            intended_use MEDIUMTEXT,
            storage_validity TEXT,
            attachments TEXT,
            other_content TEXT,
            remarks TEXT,
            approval_department VARCHAR(255),
            approval_date DATE NULL,
            effective_date DATE NULL,
            expiry_date DATE NULL,
            change_history MEDIUMTEXT,
            raw_json JSON,
            searchable_text MEDIUMTEXT,
            duplicate_count INT NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_mdr_business_key (business_key),
            UNIQUE KEY uk_mdr_source_hash (source_hash),
            KEY idx_mdr_cert_no (registration_certificate_number),
            KEY idx_mdr_product_name (product_name),
            KEY idx_mdr_registrant_name (registrant_name),
            KEY idx_mdr_category (source_category, query_keyword),
            FULLTEXT KEY ft_mdr_searchable_text (searchable_text)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
    ]
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    conn.commit()


def insert_inventory(conn, items: list[FileInventoryItem], batch_size: int) -> None:
    sql = """
        INSERT INTO medical_device_kb_files
            (source_path, relative_path, top_category, extension, kb_type, size_bytes, sha256, status, issue)
        VALUES
            (%(source_path)s, %(relative_path)s, %(top_category)s, %(extension)s, %(kb_type)s,
             %(size_bytes)s, %(sha256)s, %(status)s, %(issue)s)
        ON DUPLICATE KEY UPDATE
            relative_path = VALUES(relative_path),
            top_category = VALUES(top_category),
            extension = VALUES(extension),
            kb_type = VALUES(kb_type),
            size_bytes = VALUES(size_bytes),
            sha256 = VALUES(sha256),
            status = VALUES(status),
            issue = VALUES(issue)
    """
    with conn.cursor() as cursor:
        for start in range(0, len(items), batch_size):
            cursor.executemany(sql, [asdict(item) for item in items[start : start + batch_size]])
            conn.commit()


def insert_registration_records(conn, records: list[RegistrationRecord], batch_size: int) -> None:
    columns = list(asdict(records[0]).keys()) if records else []
    if not columns:
        return
    placeholders = ", ".join(f"%({column})s" for column in columns)
    column_sql = ", ".join(columns)
    update_sql = ", ".join(
        f"{column} = VALUES({column})"
        for column in columns
        if column not in {"business_key", "source_hash"}
    )
    sql = f"""
        INSERT INTO medical_device_registration_records ({column_sql})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {update_sql}
    """
    with conn.cursor() as cursor:
        for start in range(0, len(records), batch_size):
            cursor.executemany(sql, [asdict(record) for record in records[start : start + batch_size]])
            conn.commit()


def insert_ingest_run(
    conn,
    source_root: Path,
    output_dir: Path,
    file_count: int,
    registration_count: int,
    duplicate_registration_count: int,
    dry_run: bool,
) -> None:
    sql = """
        INSERT INTO medical_device_kb_ingest_runs
            (source_root, output_dir, file_count, registration_count, duplicate_registration_count, dry_run, finished_at)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    """
    with conn.cursor() as cursor:
        cursor.execute(
            sql,
            (
                str(source_root),
                str(output_dir),
                file_count,
                registration_count,
                duplicate_registration_count,
                dry_run,
            ),
        )
    conn.commit()


def summarize(items: list[FileInventoryItem], records: list[RegistrationRecord]) -> dict[str, Any]:
    by_type = Counter(item.kb_type for item in items)
    by_status = Counter(item.status for item in items)
    by_extension = Counter(item.extension or "(no extension)" for item in items)
    by_category = Counter(item.top_category for item in items)
    duplicate_count = sum(max(record.duplicate_count - 1, 0) for record in records)
    return {
        "file_count": len(items),
        "registration_count": len(records),
        "duplicate_registration_count": duplicate_count,
        "by_type": dict(by_type),
        "by_status": dict(by_status),
        "top_extensions": dict(by_extension.most_common(30)),
        "top_categories": dict(by_category.most_common(30)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Crawled knowledge-base root directory")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Cleaned report output directory")
    parser.add_argument("--execute", action="store_true", help="Import cleaned data into MySQL")
    parser.add_argument("--dry-run", action="store_true", help="Only generate local cleaned files and reports")
    parser.add_argument("--limit", type=int, default=0, help="Limit registration records for smoke tests")
    parser.add_argument("--batch-size", type=int, default=500, help="MySQL insert batch size")
    args = parser.parse_args()

    source_root = Path(args.source).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not source_root.exists():
        raise FileNotFoundError(f"Source path not found: {source_root}")

    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = inventory_files(source_root)
    records = dedupe_records(iter_registration_records(source_root))
    if args.limit > 0:
        records = records[: args.limit]

    summary = summarize(inventory, records)
    write_csv(output_dir / "file_inventory.csv", [asdict(item) for item in inventory], list(asdict(inventory[0]).keys()) if inventory else [])
    write_csv(
        output_dir / "medical_device_registration_records.csv",
        [asdict(record) for record in records],
        list(asdict(records[0]).keys()) if records else list(RegistrationRecord.__dataclass_fields__.keys()),
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    execute = args.execute and not args.dry_run
    if execute:
        conn = connect(**get_db_config())
        try:
            ensure_tables(conn)
            insert_inventory(conn, inventory, args.batch_size)
            insert_registration_records(conn, records, args.batch_size)
            insert_ingest_run(
                conn,
                source_root=source_root,
                output_dir=output_dir,
                file_count=len(inventory),
                registration_count=len(records),
                duplicate_registration_count=summary["duplicate_registration_count"],
                dry_run=False,
            )
        finally:
            conn.close()

    print(json.dumps({**summary, "output_dir": str(output_dir), "imported": execute}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
