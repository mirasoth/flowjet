#!/usr/bin/env python3
"""Version tags and backups for OMR workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def versions_dir(workspace: Path) -> Path:
    return workspace / ".omr" / "versions"


def backups_dir(workspace: Path) -> Path:
    return workspace / ".omr" / "backups"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _collect_paths(workspace: Path) -> list[Path]:
    paths: list[Path] = []
    for rel in (
        "docs/plans",
        "docs/survey",
        "docs/report",
        "docs/manuscript",
        "docs/brief",
        "deliverables",
    ):
        root = workspace / rel
        if root.is_dir():
            paths.extend(sorted(p for p in root.rglob("*") if p.is_file()))
    return paths


def tag(workspace: Path, label: str) -> dict[str, Any]:
    files = []
    for p in _collect_paths(workspace):
        files.append(
            {"path": str(p.relative_to(workspace)), "sha256_16": _hash_file(p)}
        )
    record = {
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    out = versions_dir(workspace)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{label}.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return record


def history(workspace: Path) -> list[str]:
    d = versions_dir(workspace)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def backup(workspace: Path) -> Path:
    stamp = _stamp()
    dest = backups_dir(workspace) / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for rel in (
        "docs/plans",
        "docs/survey",
        "docs/report",
        "docs/manuscript",
        "docs/brief",
        "deliverables",
    ):
        src = workspace / rel
        if src.exists():
            shutil.copytree(src, dest / rel, dirs_exist_ok=True)
    meta = {"at": datetime.now(timezone.utc).isoformat(), "path": str(dest)}
    (dest / "backup-meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def diff_tags(workspace: Path, a: str, b: str) -> dict[str, Any]:
    da = json.loads((versions_dir(workspace) / f"{a}.json").read_text(encoding="utf-8"))
    db = json.loads((versions_dir(workspace) / f"{b}.json").read_text(encoding="utf-8"))
    ma = {x["path"]: x["sha256_16"] for x in da.get("files", [])}
    mb = {x["path"]: x["sha256_16"] for x in db.get("files", [])}
    added = sorted(set(mb) - set(ma))
    removed = sorted(set(ma) - set(mb))
    changed = sorted(p for p in set(ma) & set(mb) if ma[p] != mb[p])
    return {"a": a, "b": b, "added": added, "removed": removed, "changed": changed}


def main() -> None:
    p = argparse.ArgumentParser(description="OMR version control")
    p.add_argument("--workspace", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tag")
    t.add_argument("label")
    sub.add_parser("history")
    sub.add_parser("list")
    sub.add_parser("backup")
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    args = p.parse_args()
    ws = args.workspace.resolve()
    if args.cmd == "tag":
        print(json.dumps(tag(ws, args.label), indent=2))
    elif args.cmd in ("history", "list"):
        print(
            json.dumps(
                {
                    "tags": history(ws),
                    "backups": sorted(
                        p.name for p in backups_dir(ws).glob("*") if p.is_dir()
                    )
                    if backups_dir(ws).exists()
                    else [],
                },
                indent=2,
            )
        )
    elif args.cmd == "backup":
        print(json.dumps({"backup": str(backup(ws))}, indent=2))
    elif args.cmd == "diff":
        print(json.dumps(diff_tags(ws, args.a, args.b), indent=2))


if __name__ == "__main__":
    main()
