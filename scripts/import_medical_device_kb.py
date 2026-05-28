"""Build RAGFlow datasets from crawled medical-device registration files.

The script is intentionally conservative:
- Dry-run by default.
- Imports only high-value text/document formats to RAGFlow.
- Skips xls/xlsx/json for RAGFlow and reports them as structured/metadata
  candidates.
- Uses small batches and an optional limit for smoke tests.

Example:
    uv run python scripts/import_medical_device_kb.py --source "D:\\work\\爬取的知识库数据"
    uv run python scripts/import_medical_device_kb.py --source "D:\\work\\爬取的知识库数据" --execute --limit 10 --parse
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rawflow.rag_config import _load_ragflow_env

try:
    from ragflow_sdk import RAGFlow
except Exception:  # pragma: no cover - handled at runtime
    RAGFlow = None


RAGFLOW_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
STRUCTURED_EXTENSIONS = {".xls", ".xlsx", ".csv"}
METADATA_EXTENSIONS = {".json"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}

DATASET_RULES = [
    {
        "key": "public_guidelines",
        "name": "mdr_public_guidelines",
        "description": "医疗器械注册技术审查指导原则、指导原则文本库等公共法规技术文件。",
        "keywords": ["指导原则", "指导原则文本库"],
    },
    {
        "key": "public_review_reports",
        "name": "mdr_public_review_reports",
        "description": "医疗器械审评报告、审评结论、审评关注点等资料。",
        "keywords": ["审评报告"],
    },
    {
        "key": "public_common_questions",
        "name": "mdr_public_common_questions",
        "description": "医疗器械注册共性问题、交流园地、审评问答和经验文章。",
        "keywords": ["共性问题", "交流园地"],
    },
    {
        "key": "public_clinical_eval",
        "name": "mdr_public_clinical_eval",
        "description": "医疗器械临床评价路径推荐、临床评价相关资料。",
        "keywords": ["临床评价"],
    },
    {
        "key": "public_draft_comments",
        "name": "mdr_public_draft_comments",
        "description": "医疗器械法规、指导原则、技术文件征求意见稿。",
        "keywords": ["征求意见稿"],
    },
    {
        "key": "public_regulatory_notices",
        "name": "mdr_public_regulatory_notices",
        "description": "医疗器械批件发布、批准注册产品公告等公开公告文本。",
        "keywords": ["批件发布", "批准注册产品公告", "医疗器械批准注册产品公告"],
    },
]

STRUCTURED_DATASET_KEY = "structured_registration_db"
SKIPPED_DATASET_KEY = "skipped_or_pending"


@dataclass
class InventoryItem:
    path: Path
    top_category: str
    extension: str
    target: str
    action: str
    size: int
    sha1: str


def classify_path(path: Path, source_root: Path) -> tuple[str, str, str]:
    relative_parts = path.relative_to(source_root).parts
    top_category = relative_parts[0] if relative_parts else ""
    extension = path.suffix.lower()

    if extension in STRUCTURED_EXTENSIONS:
        return top_category, extension, STRUCTURED_DATASET_KEY
    if extension in METADATA_EXTENSIONS:
        return top_category, extension, "metadata"
    if extension in ARCHIVE_EXTENSIONS:
        return top_category, extension, SKIPPED_DATASET_KEY
    if extension not in RAGFLOW_EXTENSIONS:
        return top_category, extension, SKIPPED_DATASET_KEY

    path_text = str(path)
    for rule in DATASET_RULES:
        if any(keyword in path_text for keyword in rule["keywords"]):
            return top_category, extension, rule["key"]

    return top_category, extension, "public_misc"


def iter_inventory(source_root: Path) -> Iterable[InventoryItem]:
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        top_category, extension, target = classify_path(path, source_root)
        action = "ragflow" if target.startswith("public_") and extension in RAGFLOW_EXTENSIONS else target
        yield InventoryItem(
            path=path,
            top_category=top_category,
            extension=extension,
            target=target,
            action=action,
            size=size,
            sha1=hash_path(path),
        )


def hash_path(path: Path) -> str:
    digest = hashlib.sha1()
    digest.update(str(path).encode("utf-8", errors="ignore"))
    return digest.hexdigest()


def write_inventory(items: list[InventoryItem], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "path",
                "top_category",
                "extension",
                "target",
                "action",
                "size",
                "sha1",
            ],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "path": str(item.path),
                    "top_category": item.top_category,
                    "extension": item.extension,
                    "target": item.target,
                    "action": item.action,
                    "size": item.size,
                    "sha1": item.sha1,
                }
            )


def ensure_datasets(client: RAGFlow, execute: bool) -> dict[str, object]:
    existing = {dataset.name: dataset for dataset in client.list_datasets(page=1, page_size=200)}
    result: dict[str, object] = {}
    for rule in DATASET_RULES:
        dataset = existing.get(rule["name"])
        if dataset:
            result[rule["key"]] = dataset
            continue
        if not execute:
            continue
        result[rule["key"]] = client.create_dataset(
            name=rule["name"],
            description=rule["description"],
            embedding_model=os.getenv("RAGFLOW_EMBEDDING_MODEL", "text-embedding-v3@Tongyi-Qianwen"),
        )
    return result


def upload_batch(dataset, files: list[Path], parse: bool) -> None:
    documents = []
    for file_path in files:
        with file_path.open("rb") as file:
            documents.append(
                {
                    "display_name": file_path.name,
                    "name": file_path.name,
                    "blob": file.read(),
                }
            )
    dataset.upload_documents(documents)

    if parse:
        uploaded = dataset.list_documents(page=1, page_size=200, orderby="create_time", desc=True)
        ids = [getattr(doc, "id", None) for doc in uploaded[: len(files)]]
        ids = [doc_id for doc_id in ids if doc_id]
        if ids:
            dataset.async_parse_documents(ids)


def import_to_ragflow(
    items: list[InventoryItem],
    limit: int,
    per_target_limit: int,
    batch_size: int,
    parse: bool,
) -> dict[str, int]:
    if RAGFlow is None:
        raise RuntimeError("ragflow-sdk is not available")

    api_key, base_url = _load_ragflow_env()
    client = RAGFlow(api_key=api_key, base_url=base_url)
    datasets = ensure_datasets(client, execute=True)

    imported: dict[str, int] = {}
    grouped: dict[str, list[Path]] = {}
    total = 0
    per_target_counts: dict[str, int] = {}
    for item in items:
        if item.action != "ragflow" or item.target not in datasets:
            continue
        if limit > 0 and total >= limit:
            break
        if per_target_limit > 0 and per_target_counts.get(item.target, 0) >= per_target_limit:
            continue
        grouped.setdefault(item.target, []).append(item.path)
        per_target_counts[item.target] = per_target_counts.get(item.target, 0) + 1
        total += 1

    for target, files in grouped.items():
        dataset = datasets[target]
        imported[target] = 0
        for index in range(0, len(files), batch_size):
            batch = files[index : index + batch_size]
            upload_batch(dataset, batch, parse=parse)
            imported[target] += len(batch)

    return imported


def print_summary(items: list[InventoryItem]) -> None:
    by_target: dict[str, int] = {}
    by_ext: dict[str, int] = {}
    for item in items:
        by_target[item.target] = by_target.get(item.target, 0) + 1
        by_ext[item.extension or "(no extension)"] = by_ext.get(item.extension or "(no extension)", 0) + 1

    print("Inventory summary by target:")
    for key, count in sorted(by_target.items(), key=lambda pair: pair[0]):
        print(f"  {key}: {count}")

    print("\nTop extensions:")
    for key, count in sorted(by_ext.items(), key=lambda pair: pair[1], reverse=True)[:20]:
        print(f"  {key}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Crawled knowledge base directory")
    parser.add_argument(
        "--inventory",
        default="app/output/medical_device_kb_inventory.csv",
        help="CSV inventory output path",
    )
    parser.add_argument("--execute", action="store_true", help="Actually create datasets and upload documents")
    parser.add_argument("--limit", type=int, default=0, help="Max RAGFlow documents to upload; 0 means no limit")
    parser.add_argument(
        "--per-target-limit",
        type=int,
        default=0,
        help="Max RAGFlow documents to upload per dataset target; 0 means no per-target limit",
    )
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--parse", action="store_true", help="Trigger RAGFlow async parsing after upload")
    args = parser.parse_args()

    source_root = Path(args.source).resolve()
    if not source_root.exists():
        raise FileNotFoundError(f"Source path not found: {source_root}")

    items = list(iter_inventory(source_root))
    write_inventory(items, Path(args.inventory))
    print_summary(items)
    print(f"\nInventory written to: {Path(args.inventory).resolve()}")

    if not args.execute:
        print("\nDry-run only. Add --execute --limit N to upload a small sample.")
        return

    imported = import_to_ragflow(
        items=items,
        limit=args.limit,
        per_target_limit=args.per_target_limit,
        batch_size=args.batch_size,
        parse=args.parse,
    )
    print("\nImported to RAGFlow:")
    print(json.dumps(imported, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
