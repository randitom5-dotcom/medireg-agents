"""Import cleaned medical-device documents into RAGFlow datasets.

The source corpus is treated as read-only. This script classifies non-structured
documents into dedicated RAGFlow datasets, uploads them in small batches, and can
trigger parsing after upload.

Examples:
    python scripts/import_ragflow_medical_device_kb.py --source "D:\\work\\爬取的知识库数据" --dry-run
    python scripts/import_ragflow_medical_device_kb.py --source "D:\\work\\爬取的知识库数据" --execute --limit 5 --parse
    python scripts/import_ragflow_medical_device_kb.py --source "D:\\work\\爬取的知识库数据" --execute --per-dataset-limit 50 --parse
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from ragflow_sdk import RAGFlow
except Exception:  # pragma: no cover
    RAGFlow = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "app" / "output" / "ragflow_medical_device_kb"

RAGFLOW_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}
SKIP_DIR_NAMES = {
    "数据校验报告",
    "knowledge-base-url-audit",
    "药品监督管理局数据查询",
    "药品监督管理局数据查询（修复）",
}

DATASET_RULES = [
    {
        "key": "mdr_guidelines",
        "name": "mdr_guidelines",
        "description": "医疗器械注册指导原则、技术审查指导原则和相关规范性指导文件。",
        "categories": {"指导原则文本库", "指导原则文本库（修复）"},
    },
    {
        "key": "mdr_review_reports",
        "name": "mdr_review_reports",
        "description": "医疗器械审评报告、产品审评结论和同类产品审评关注点资料。",
        "categories": {"审评报告", "审评报告（修复）"},
    },
    {
        "key": "mdr_common_questions",
        "name": "mdr_common_questions",
        "description": "医疗器械注册共性问题、问答材料和常见审评关注点。",
        "categories": {"共性问题", "共性问题（修复）"},
    },
    {
        "key": "mdr_exchange",
        "name": "mdr_exchange",
        "description": "医疗器械审评交流园地、审评沟通文章和经验材料。",
        "categories": {"交流园地", "交流园地（修复）"},
    },
    {
        "key": "mdr_draft_comments",
        "name": "mdr_draft_comments",
        "description": "医疗器械法规、指导原则、标准等征求意见稿和附件材料。",
        "categories": {"征求意见稿", "征求意见稿（修复）"},
    },
    {
        "key": "mdr_registration_announcements",
        "name": "mdr_registration_announcements",
        "description": "医疗器械批准注册产品公告正文及相关附件。",
        "categories": {"医疗器械批准注册产品公告", "医疗器械批准注册产品公告（修复）"},
    },
    {
        "key": "mdr_clinical_evaluation",
        "name": "mdr_clinical_evaluation",
        "description": "医疗器械临床评价路径、临床评价推荐和临床评价相关材料。",
        "categories": {"临床评价路径推荐", "临床评价路径推荐（修复）"},
    },
]

CATEGORY_TO_DATASET = {
    category: rule["key"]
    for rule in DATASET_RULES
    for category in rule["categories"]
}
DATASET_BY_KEY = {rule["key"]: rule for rule in DATASET_RULES}


@dataclass
class ImportItem:
    path: str
    relative_path: str
    source_category: str
    extension: str
    dataset_key: str
    dataset_name: str
    size_bytes: int
    sha256: str
    status: str
    issue: str


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_items(source_root: Path) -> list[ImportItem]:
    items: list[ImportItem] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if not relative.parts:
            continue
        category = relative.parts[0]
        if category in SKIP_DIR_NAMES:
            continue
        dataset_key = CATEGORY_TO_DATASET.get(category)
        if not dataset_key:
            continue
        extension = path.suffix.lower()
        if extension not in RAGFLOW_EXTENSIONS:
            continue

        try:
            size = path.stat().st_size
            digest = sha256_file(path)
            status = "PASS" if size > 0 else "BLANK_FILE"
            issue = "" if size > 0 else "zero byte file"
        except Exception as exc:
            size = 0
            digest = ""
            status = "UNREADABLE"
            issue = str(exc)

        rule = DATASET_BY_KEY[dataset_key]
        items.append(
            ImportItem(
                path=str(path),
                relative_path=str(relative),
                source_category=category,
                extension=extension,
                dataset_key=dataset_key,
                dataset_name=rule["name"],
                size_bytes=size,
                sha256=digest,
                status=status,
                issue=issue,
            )
        )
    return items


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(items: list[ImportItem]) -> dict[str, Any]:
    return {
        "candidate_count": len(items),
        "by_dataset": dict(Counter(item.dataset_name for item in items)),
        "by_category": dict(Counter(item.source_category for item in items)),
        "by_extension": dict(Counter(item.extension for item in items)),
        "by_status": dict(Counter(item.status for item in items)),
    }


def load_ragflow_client():
    if RAGFlow is None:
        raise RuntimeError("ragflow-sdk is not installed")
    load_dotenv(PROJECT_ROOT / ".env")
    base_url = os.getenv("RAGFLOW_API_URL")
    if base_url and ("localhost" in base_url or "127.0.0.1" in base_url):
        current = os.getenv("NO_PROXY", "")
        values = [part.strip() for part in current.split(",") if part.strip()]
        for host in ["localhost", "127.0.0.1", "::1"]:
            if host not in values:
                values.append(host)
        os.environ["NO_PROXY"] = ",".join(values)
        os.environ["no_proxy"] = ",".join(values)
    return RAGFlow(api_key=os.getenv("RAGFLOW_API_KEY"), base_url=base_url)


def ensure_datasets(client) -> dict[str, Any]:
    existing = {dataset.name: dataset for dataset in client.list_datasets(page=1, page_size=200)}
    datasets: dict[str, Any] = {}
    embedding_model = os.getenv("RAGFLOW_EMBEDDING_MODEL", "text-embedding-v3@Tongyi-Qianwen")
    for rule in DATASET_RULES:
        dataset = existing.get(rule["name"])
        if dataset is None:
            dataset = client.create_dataset(
                name=rule["name"],
                description=rule["description"],
                embedding_model=embedding_model,
            )
        datasets[rule["key"]] = dataset
    return datasets


def select_upload_items(
    items: list[ImportItem],
    limit: int,
    per_dataset_limit: int,
) -> list[ImportItem]:
    selected: list[ImportItem] = []
    per_dataset_counts: Counter[str] = Counter()
    seen_hashes: set[str] = set()
    for item in items:
        if item.status != "PASS":
            continue
        if item.sha256 in seen_hashes:
            continue
        if per_dataset_limit > 0 and per_dataset_counts[item.dataset_key] >= per_dataset_limit:
            continue
        if limit > 0 and len(selected) >= limit:
            break
        selected.append(item)
        per_dataset_counts[item.dataset_key] += 1
        seen_hashes.add(item.sha256)
    return selected


def ragflow_document_name(item: ImportItem) -> str:
    safe_relative = "".join(
        char if char.isalnum() or char in {".", "-", "_"} else "_"
        for char in item.relative_path.replace("\\", "__").replace("/", "__")
    )
    if len(safe_relative) > 160:
        suffix = Path(item.path).suffix
        safe_relative = f"{safe_relative[:120]}__{item.sha256[:16]}{suffix}"
    return f"{item.sha256[:12]}__{safe_relative}"


def existing_document_names(dataset) -> set[str]:
    names: set[str] = set()
    page = 1
    while True:
        docs = dataset.list_documents(page=page, page_size=200)
        if not docs:
            break
        for doc in docs:
            name = getattr(doc, "name", None) or getattr(doc, "display_name", None)
            if name:
                names.add(str(name))
        if len(docs) < 200:
            break
        page += 1
    return names


def upload_documents(dataset, items: list[ImportItem], batch_size: int, parse: bool) -> int:
    uploaded_count = 0
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        documents = []
        for item in batch:
            path = Path(item.path)
            with path.open("rb") as file:
                documents.append(
                    {
                        "display_name": ragflow_document_name(item),
                        "name": ragflow_document_name(item),
                        "blob": file.read(),
                    }
                )
        dataset.upload_documents(documents)
        uploaded_count += len(batch)

        if parse:
            docs = dataset.list_documents(page=1, page_size=200, orderby="create_time", desc=True)
            ids = [getattr(doc, "id", None) for doc in docs[: len(batch)]]
            ids = [doc_id for doc_id in ids if doc_id]
            if ids:
                dataset.async_parse_documents(ids)
    return uploaded_count


def import_to_ragflow(items: list[ImportItem], batch_size: int, parse: bool) -> dict[str, int]:
    client = load_ragflow_client()
    datasets = ensure_datasets(client)
    grouped: dict[str, list[ImportItem]] = defaultdict(list)
    for item in items:
        grouped[item.dataset_key].append(item)

    imported: dict[str, int] = {}
    for dataset_key, dataset_items in grouped.items():
        dataset = datasets[dataset_key]
        existing_names = existing_document_names(dataset)
        dataset_items = [
            item
            for item in dataset_items
            if ragflow_document_name(item) not in existing_names
        ]
        imported[DATASET_BY_KEY[dataset_key]["name"]] = upload_documents(
            dataset,
            dataset_items,
            batch_size=batch_size,
            parse=parse,
        )
    return imported


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Crawled knowledge-base root directory")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Inventory output directory")
    parser.add_argument("--execute", action="store_true", help="Actually upload to RAGFlow")
    parser.add_argument("--dry-run", action="store_true", help="Only generate inventory")
    parser.add_argument("--limit", type=int, default=0, help="Total upload limit; 0 means no limit")
    parser.add_argument("--per-dataset-limit", type=int, default=0, help="Upload limit per dataset")
    parser.add_argument("--batch-size", type=int, default=5, help="RAGFlow upload batch size")
    parser.add_argument("--parse", action="store_true", help="Trigger RAGFlow async parsing")
    args = parser.parse_args()

    source_root = Path(args.source).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not source_root.exists():
        raise FileNotFoundError(f"Source path not found: {source_root}")

    items = discover_items(source_root)
    selected = select_upload_items(items, limit=args.limit, per_dataset_limit=args.per_dataset_limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "ragflow_import_inventory.csv",
        [asdict(item) for item in items],
        list(asdict(items[0]).keys()) if items else list(ImportItem.__dataclass_fields__.keys()),
    )
    write_csv(
        output_dir / "ragflow_selected_uploads.csv",
        [asdict(item) for item in selected],
        list(asdict(selected[0]).keys()) if selected else list(ImportItem.__dataclass_fields__.keys()),
    )

    result = {
        **summarize(items),
        "selected_upload_count": len(selected),
        "selected_by_dataset": dict(Counter(item.dataset_name for item in selected)),
        "output_dir": str(output_dir),
        "imported": {},
    }

    if args.execute and not args.dry_run:
        result["imported"] = import_to_ragflow(selected, batch_size=args.batch_size, parse=args.parse)

    (output_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
