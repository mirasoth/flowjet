#!/usr/bin/env python3
"""Lightweight collect CLI: record sources into materials/ + papers-index.json.

Creates only the directories needed for the files being written — never a full
empty materials/ tree. After recording a source, optionally invokes
`material_to_markdown.py` to download + convert the source into a full-text
Markdown file so ANALYZE can read the entire paper, not just the abstract.

Papers persist the raw binary at `materials/papers-raw/<ID>.<ext>` and the
converted Markdown at `materials/papers/<ID>.md` (same stem, different suffix).
Other buckets still write `materials/<bucket>/<ID>.md`.

Parallel COLLECT: bucket workers pass `--id` + `--bucket` + `--inbox` to write
`docs/index/inbox/<ID>.json` without touching `papers-index.json`. The
coordinator then runs `--merge-inbox`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_SCRIPT_DIR = Path(__file__).resolve().parent
_CONVERTER = _SCRIPT_DIR / "material_to_markdown.py"

INDEX_BUCKETS = ("papers", "web", "github", "search")

# Preprint & repository hosts that carry paper semantics (PDF / DOI resolvable).
# Routing these to `web` would lose the P- ID, papers-raw binary, and full-text
# conversion — see docs/design/collect-enrichment.md §2.2/§3.1.
PAPER_HOST_RE = re.compile(
    r"(arxiv\.org"
    r"|biorxiv\.org"
    r"|medrxiv\.org"
    r"|openreview\.net"
    r"|aclanthology\.org"
    r"|zenodo\.org"
    r"|ssrn\.com"
    r"|hal\.science"
    r")",
    re.IGNORECASE,
)

PREFIX_FOR_KIND = {
    "papers": "P",
    "web": "W",
    "github": "G",
    "search": "S",
    "datasets": "W",
}
KIND_FOR_PREFIX = {"P": "papers", "W": "web", "G": "github", "S": "search"}


def write_text(path: Path, text: str) -> None:
    """Create parent dirs only when writing a real file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def inbox_dir(workspace: Path) -> Path:
    return workspace / "docs" / "index" / "inbox"


def write_inbox(workspace: Path, item: dict[str, Any]) -> Path:
    path = inbox_dir(workspace) / f"{item['id']}.json"
    write_text(path, json.dumps(item, indent=2) + "\n")
    return path


def load_index(workspace: Path) -> dict[str, Any]:
    path = workspace / "docs" / "index" / "papers-index.json"
    if not path.exists():
        return {"papers": [], "web": [], "github": [], "search": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"papers": data, "web": [], "github": [], "search": []}
    for key in INDEX_BUCKETS:
        data.setdefault(key, [])
    return data


def save_index(workspace: Path, data: dict[str, Any]) -> None:
    path = workspace / "docs" / "index" / "papers-index.json"
    write_text(path, json.dumps(data, indent=2) + "\n")
    md = workspace / "docs" / "index" / "papers-index.md"
    lines = ["# Materials Index", ""]
    for bucket in INDEX_BUCKETS:
        items = data.get(bucket, [])
        if not items:
            continue  # skip empty sections — and never invent empty bucket dirs
        lines.append(f"## {bucket}")
        for item in items:
            lines.append(
                f"- [{item['id']}] {item.get('title') or item.get('source')} — {item.get('source')}"
            )
        lines.append("")
    write_text(md, "\n".join(lines).rstrip() + "\n")


def next_id(items: list[dict[str, Any]], prefix: str) -> str:
    nums = []
    for it in items:
        m = re.match(rf"{prefix}-(\d+)", it.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    n = max(nums) + 1 if nums else 1
    return f"{prefix}-{n:03d}"


def classify(source: str) -> str:
    s = source.lower()
    if PAPER_HOST_RE.search(s) or re.match(r"^10\.\d+", s) or s.endswith(".pdf"):
        return "papers"
    if "github.com" in s:
        return "github"
    if "huggingface.co" in s:
        return "datasets"
    if s.startswith(("http://", "https://")):
        return "web"
    return "search"


def index_bucket_for(kind: str) -> str:
    return "web" if kind == "datasets" else kind


def kind_from_id(material_id: str) -> str | None:
    m = re.match(r"^([PWGS])-\d+", material_id)
    if not m:
        return None
    return KIND_FOR_PREFIX.get(m.group(1))


def convert_source(
    workspace: Path, source: str, material_id: str, bucket: str, title: str | None
) -> dict[str, Any]:
    """Invoke material_to_markdown.py to download + convert one source.

    Returns the converter's result dict (status / method / path / ...). On
    any invocation error, returns a failed record with the reason."""
    if not _CONVERTER.exists():
        return {
            "id": material_id,
            "status": "failed",
            "reason": "converter script not found",
        }
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(_CONVERTER),
                source,
                "--id",
                material_id,
                "--bucket",
                bucket,
                "--workspace",
                str(workspace),
                "--title",
                title or "",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
                if isinstance(payload, dict) and payload.get("status"):
                    return payload
            except json.JSONDecodeError:
                pass
        return {
            "id": material_id,
            "status": "failed",
            "reason": result.stderr.strip() or f"converter exit {result.returncode}",
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        return {
            "id": material_id,
            "status": "failed",
            "reason": f"{type(e).__name__}: {e}",
        }


def _build_item(
    workspace: Path,
    source: str,
    kind: str,
    material_id: str,
    title: str | None,
    convert: bool,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    resolved_title = title or source

    if kind == "papers":
        item: dict[str, Any] = {
            "id": material_id,
            "source": source,
            "title": resolved_title,
            "collected_at": now,
            "bucket": "papers",
        }
        note = workspace / "materials" / "papers-raw" / f"{item['id']}.source.txt"
        write_text(note, f"source: {source}\ntitle: {item['title']}\n")
        item["path"] = str(note.relative_to(workspace))
        if convert:
            conv = convert_source(
                workspace, source, item["id"], "papers", item["title"]
            )
            item["markdown_path"] = conv.get("path", "")
            item["markdown_status"] = conv.get("status", "")
            item["markdown_method"] = conv.get("method", "")
            item["raw_path"] = conv.get("raw_path", "")
            if conv.get("reason"):
                item["markdown_failure_reason"] = conv["reason"]
        return item

    if kind == "github":
        item = {
            "id": material_id,
            "source": source,
            "title": title or urlparse(source).path.strip("/") or source,
            "collected_at": now,
            "bucket": "github",
        }
        note = workspace / "materials" / "github" / f"{item['id']}.source.txt"
        write_text(note, f"source: {source}\n")
        item["path"] = str(note.relative_to(workspace))
        return item

    if kind == "web" or kind == "datasets":
        dest = "datasets" if kind == "datasets" else "web"
        item = {
            "id": material_id,
            "source": source,
            "title": resolved_title,
            "collected_at": now,
            "kind": kind,
            "bucket": "web",
        }
        note = workspace / "materials" / dest / f"{item['id']}.source.txt"
        write_text(note, f"source: {source}\n")
        item["path"] = str(note.relative_to(workspace))
        if convert:
            conv = convert_source(workspace, source, item["id"], dest, item["title"])
            item["markdown_path"] = conv.get("path", "")
            item["markdown_status"] = conv.get("status", "")
            item["markdown_method"] = conv.get("method", "")
            if conv.get("reason"):
                item["markdown_failure_reason"] = conv["reason"]
        return item

    item = {
        "id": material_id,
        "source": source,
        "title": resolved_title,
        "collected_at": now,
        "kind": "search",
        "bucket": "search",
    }
    note = workspace / "materials" / "search" / f"{item['id']}.query.txt"
    write_text(note, f"query: {source}\n")
    item["path"] = str(note.relative_to(workspace))
    return item


def record(
    workspace: Path,
    source: str,
    title: str | None = None,
    convert: bool = True,
    material_id: str | None = None,
    bucket: str | None = None,
    inbox: bool = False,
) -> dict[str, Any]:
    kind = bucket or classify(source)
    if kind not in (*INDEX_BUCKETS, "datasets"):
        kind = classify(source)

    if inbox:
        if not material_id:
            raise ValueError(
                "--id is required with --inbox (pre-assigned by coordinator)"
            )
        item = _build_item(workspace, source, kind, material_id, title, convert)
        write_inbox(workspace, item)
        return item

    data = load_index(workspace)
    idx_bucket = index_bucket_for(kind)
    prefix = PREFIX_FOR_KIND[kind]
    mid = material_id or next_id(data[idx_bucket], prefix)
    item = _build_item(workspace, source, kind, mid, title, convert)
    data[idx_bucket].append(item)
    save_index(workspace, data)
    return item


def merge_inbox(workspace: Path) -> dict[str, Any]:
    """Append docs/index/inbox/*.json into papers-index.json; skip duplicate IDs."""
    data = load_index(workspace)
    existing: set[str] = set()
    for bucket in INDEX_BUCKETS:
        for it in data.get(bucket, []):
            if it.get("id"):
                existing.add(it["id"])

    merged: list[dict[str, Any]] = []
    skipped: list[str] = []
    inbox = inbox_dir(workspace)
    if not inbox.is_dir():
        return {
            "merged": [],
            "skipped": [],
            "index": str(workspace / "docs" / "index" / "papers-index.json"),
        }

    for path in sorted(inbox.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            skipped.append(path.name)
            continue
        mid = item.get("id", "")
        if not mid:
            skipped.append(path.name)
            continue
        if mid in existing:
            skipped.append(mid)
            path.unlink(missing_ok=True)
            continue
        bucket = (
            item.get("bucket")
            or kind_from_id(mid)
            or classify(str(item.get("source", "")))
        )
        bucket = index_bucket_for(bucket)
        if bucket not in INDEX_BUCKETS:
            bucket = "search"
        data[bucket].append(item)
        existing.add(mid)
        merged.append(item)
        path.unlink(missing_ok=True)

    if merged or (
        not (workspace / "docs" / "index" / "papers-index.json").exists()
        and any(data[b] for b in INDEX_BUCKETS)
    ):
        save_index(workspace, data)

    leftover = list(inbox.glob("*.json"))
    if not leftover:
        try:
            inbox.rmdir()
        except OSError:
            pass

    return {
        "merged": [it["id"] for it in merged],
        "skipped": skipped,
        "counts": {b: len(data.get(b, [])) for b in INDEX_BUCKETS},
    }


def main() -> None:
    p = argparse.ArgumentParser(description="OMR collect CLI (index + placeholders)")
    p.add_argument("sources", nargs="*", help="URLs, DOIs, or search queries")
    p.add_argument("--workspace", type=Path, default=Path.cwd())
    p.add_argument("--title", default=None)
    p.add_argument(
        "--id", dest="material_id", default=None, help="pre-assigned material ID"
    )
    p.add_argument(
        "--bucket",
        default=None,
        help="papers/web/github/search/datasets (skip classify when set)",
    )
    p.add_argument(
        "--inbox",
        action="store_true",
        help="write docs/index/inbox/<ID>.json only; do not update papers-index.json",
    )
    p.add_argument(
        "--merge-inbox",
        action="store_true",
        help="merge docs/index/inbox/*.json into papers-index.json",
    )
    p.add_argument(
        "--convert",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="download + convert each source to full-text Markdown via anydoc (default: on)",
    )
    args = p.parse_args()
    ws = args.workspace.resolve()

    if args.merge_inbox:
        print(json.dumps(merge_inbox(ws), indent=2))
        return

    if not args.sources:
        p.error("sources are required (or use --merge-inbox)")

    if args.inbox and not args.material_id:
        p.error("--id is required with --inbox")

    if args.material_id and len(args.sources) != 1:
        p.error("--id requires exactly one source")

    results = [
        record(
            ws,
            s,
            args.title,
            convert=args.convert,
            material_id=args.material_id,
            bucket=args.bucket,
            inbox=args.inbox,
        )
        for s in args.sources
    ]
    print(json.dumps({"recorded": results}, indent=2))


if __name__ == "__main__":
    main()
