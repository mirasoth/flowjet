#!/usr/bin/env python3
"""Skill-package version management for oh-my-research.

Single source of truth: skills/oh-my-research/SKILL.md → metadata.version

Synced (when present):
  - .claude-plugin/marketplace.json  (metadata.version + plugins[].version)
  - CHANGELOG.md                     (prepended on set/bump)

Works in repo checkouts and installed skill packages (e.g.
~/.agents/skills/oh-my-research); marketplace sync is skipped when absent.

Commands:
  show                         Print metadata.version from SKILL.md
  check                        Exit 0 if marketplace matches SKILL.md
  sync                         Write SKILL.md version into marketplace.json
  set <X.Y.Z> [--date YYYY-MM-DD] [--message TEXT]
  bump major|minor|patch [--date YYYY-MM-DD] [--message TEXT]
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
SKILL_VERSION_RE = re.compile(
    r'(^metadata:\s*\n(?:^[ \t]+.*\n)*?[ \t]+version:\s*)(["\']?)([^"\'\n]+)(["\']?)',
    re.MULTILINE,
)


def skill_package_root() -> Path:
    """Directory that contains SKILL.md (scripts/ → parent)."""
    return Path(__file__).resolve().parent.parent


def repo_root(explicit: Path | None = None) -> Path | None:
    """Repo root containing .claude-plugin/marketplace.json, if any."""
    if explicit is not None:
        return explicit.resolve()
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / ".claude-plugin" / "marketplace.json").exists():
            return parent
    return None


def paths(root: Path | None = None) -> dict[str, Path | None]:
    skill = skill_package_root()
    skill_md = skill / "SKILL.md"
    if not skill_md.exists() and root is not None:
        skill_md = root / "skills" / "oh-my-research" / "SKILL.md"
        skill = skill_md.parent

    repo = repo_root(root) if root is not None else repo_root()
    marketplace = (
        (repo / ".claude-plugin" / "marketplace.json") if repo is not None else None
    )
    changelog = None
    if repo is not None and (repo / "CHANGELOG.md").exists():
        changelog = repo / "CHANGELOG.md"
    elif (skill / "CHANGELOG.md").exists():
        changelog = skill / "CHANGELOG.md"
    elif repo is not None:
        changelog = repo / "CHANGELOG.md"

    return {
        "skill": skill_md,
        "marketplace": marketplace if marketplace and marketplace.exists() else None,
        "changelog": changelog,
    }


def parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER.match(value)
    if not match:
        raise SystemExit(f"Invalid semver: {value!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_semver(value: str, kind: str) -> str:
    major, minor, patch = parse_semver(value)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"Unknown bump kind: {kind}")


def skill_md_version(text: str) -> str | None:
    match = SKILL_VERSION_RE.search(text)
    return match.group(3).strip() if match else None


def read_skill_version(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Missing SKILL.md: {path}")
    value = skill_md_version(path.read_text(encoding="utf-8"))
    if value is None:
        raise SystemExit("metadata.version missing in SKILL.md")
    if not SEMVER.match(value):
        raise SystemExit(f"Invalid semver in SKILL.md metadata.version: {value!r}")
    return value


def set_skill_md_version(text: str, version: str) -> str:
    if not SKILL_VERSION_RE.search(text):
        raise SystemExit("Could not find metadata.version in SKILL.md")
    return SKILL_VERSION_RE.sub(
        lambda m: f'{m.group(1)}"{version}"',
        text,
        count=1,
    )


def marketplace_versions(data: dict) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    meta = data.get("metadata") or {}
    if "version" in meta:
        found.append(("metadata.version", str(meta["version"])))
    for i, plugin in enumerate(data.get("plugins") or []):
        if "version" in plugin:
            found.append((f"plugins[{i}].version", str(plugin["version"])))
    return found


def set_marketplace_versions(data: dict, version: str) -> None:
    data.setdefault("metadata", {})["version"] = version
    for plugin in data.get("plugins") or []:
        plugin["version"] = version


def collect_versions(p: dict[str, Path | None]) -> dict[str, str]:
    assert p["skill"] is not None
    versions: dict[str, str] = {"SKILL.md": read_skill_version(p["skill"])}
    if p["marketplace"] is not None:
        market = json.loads(p["marketplace"].read_text(encoding="utf-8"))
        for label, value in marketplace_versions(market):
            versions[f"marketplace.json:{label}"] = value
    return versions


def cmd_show(p: dict[str, Path | None]) -> int:
    assert p["skill"] is not None
    print(read_skill_version(p["skill"]))
    return 0


def cmd_check(p: dict[str, Path | None]) -> int:
    versions = collect_versions(p)
    expected = versions["SKILL.md"]
    mismatches = {k: v for k, v in versions.items() if v != expected}
    if mismatches:
        print(f"SKILL.md={expected}")
        for key, value in mismatches.items():
            print(f"  MISMATCH {key}={value}")
        return 1
    print(f"OK — all locations at {expected}")
    for key, value in versions.items():
        print(f"  {key}: {value}")
    if p["marketplace"] is None:
        print("  (marketplace.json not present — skipped)")
    return 0


def sync_to_files(p: dict[str, Path | None], version: str) -> None:
    assert p["skill"] is not None
    skill_text = p["skill"].read_text(encoding="utf-8")
    p["skill"].write_text(set_skill_md_version(skill_text, version), encoding="utf-8")
    if p["marketplace"] is not None:
        market = json.loads(p["marketplace"].read_text(encoding="utf-8"))
        set_marketplace_versions(market, version)
        p["marketplace"].write_text(
            json.dumps(market, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def prepend_changelog(
    path: Path | None, version: str, when: str, message: str | None
) -> None:
    if path is None:
        return
    heading = f"## [{version}] — {when}\n"
    body = (
        f"\n### Changed\n\n- {message.strip()}\n"
        if message and message.strip()
        else "\n### Added\n\n- \n\n### Changed\n\n- \n\n### Fixed\n\n- \n"
    )
    entry = heading + body + "\n"
    if not path.exists():
        path.write_text(
            "# Changelog\n\n"
            "All notable changes to the **oh-my-research** skill package are documented here.\n\n"
            + entry,
            encoding="utf-8",
        )
        return
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^## \[", text, re.MULTILINE)
    if match:
        text = text[: match.start()] + entry + text[match.start() :]
    else:
        text = text.rstrip() + "\n\n" + entry
    if text.count(f"## [{version}]") > 1:
        parts = re.split(rf"(?=^## \[{re.escape(version)}\])", text, flags=re.MULTILINE)
        kept = [parts[0]]
        version_blocks = [b for b in parts[1:] if b.startswith(f"## [{version}]")]
        other = [b for b in parts[1:] if not b.startswith(f"## [{version}]")]
        if version_blocks:
            kept.append(version_blocks[0])
        kept.extend(other)
        text = "".join(kept)
    path.write_text(text, encoding="utf-8")


def cmd_sync(p: dict[str, Path | None]) -> int:
    assert p["skill"] is not None
    version = read_skill_version(p["skill"])
    sync_to_files(p, version)
    if p["marketplace"] is None:
        print(f"Synced {version} → SKILL.md only (no marketplace.json)")
    else:
        print(f"Synced {version} → SKILL.md + marketplace.json")
    return cmd_check(p)


def cmd_set(
    p: dict[str, Path | None], version: str, when: str, message: str | None
) -> int:
    parse_semver(version)
    sync_to_files(p, version)
    prepend_changelog(p["changelog"], version, when, message)
    print(f"Set version {version}")
    return cmd_check(p)


def cmd_bump(
    p: dict[str, Path | None], kind: str, when: str, message: str | None
) -> int:
    assert p["skill"] is not None
    current = read_skill_version(p["skill"])
    next_version = bump_semver(current, kind)
    return cmd_set(p, next_version, when, message)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Oh-My-Research skill package versioning (SKILL.md is source of truth)"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Optional repo root (auto-detected; not required for installed skills)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show", help="Print SKILL.md metadata.version")
    sub.add_parser("check", help="Verify marketplace matches SKILL.md")
    sub.add_parser("sync", help="Write SKILL.md version into marketplace.json")

    set_p = sub.add_parser("set", help="Set an explicit semver and sync")
    set_p.add_argument("version")
    set_p.add_argument("--date", default=None, help="Changelog date (YYYY-MM-DD)")
    set_p.add_argument("--message", default=None, help="One-line changelog note")

    bump_p = sub.add_parser("bump", help="Bump major|minor|patch, sync, changelog stub")
    bump_p.add_argument("kind", choices=("major", "minor", "patch"))
    bump_p.add_argument("--date", default=None)
    bump_p.add_argument("--message", default=None)

    args = parser.parse_args()
    p = paths(args.root)
    when = (
        args.date
        if hasattr(args, "date") and args.date
        else datetime.now(timezone.utc).date().isoformat()
    )

    if args.cmd == "show":
        raise SystemExit(cmd_show(p))
    if args.cmd == "check":
        raise SystemExit(cmd_check(p))
    if args.cmd == "sync":
        raise SystemExit(cmd_sync(p))
    if args.cmd == "set":
        raise SystemExit(cmd_set(p, args.version, when, args.message))
    if args.cmd == "bump":
        raise SystemExit(cmd_bump(p, args.kind, when, args.message))
    raise SystemExit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
