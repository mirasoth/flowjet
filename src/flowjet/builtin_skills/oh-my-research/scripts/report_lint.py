#!/usr/bin/env python3
"""Publication-safety linter for OMR report chapters.

Scans reader-facing Markdown files (docs/<mode>/chapters/*.md or a single
report file) for internal terminology that must not appear in public deliverables:

  - Internal material IDs: [P-001], W-002, G-003, S-004, E-005
  - arXiv IDs in raw form: arXiv:2506.23852 (should be a proper citation)
  - Evidence-grade labels in prose: proven / suggests / inferred
  - Workflow jargon: OMR, Evidence-Deep, THINK mode, SYNTH mode
  - Gate names: Gate A, Gate B, Gate D, QA1, QA2
  - Private paths: docs/plans/, .omr/, tree-state.json
  - THINK ledger tables or outcome stamps in public prose

Exit codes: 0 = clean, 1 = violations found, 2 = usage error.

Usage:
  python3 scripts/report_lint.py --mode survey --workspace .
  python3 scripts/report_lint.py --file docs/survey/ego-end-to-end-pipeline.md
  python3 scripts/report_lint.py --mode survey --json  # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# --- Patterns --------------------------------------------------------------

# Internal material ID: [P-001], W-002, G-003, S-004, E-005 (with or without brackets)
MATERIAL_ID_RE = re.compile(
    r"(?<![\w-])\[?(?:P|W|G|S|E)-\d{1,6}\]?(?![\w-])", re.IGNORECASE
)

# Raw arXiv ID in prose (arXiv:NNNN.NNNNN or arxiv:NNNN.NNNNN)
# Exception: inside a proper citation like (Author, 2025) this is fine,
# but bare arXiv:2506.23852 in prose is a violation.
ARXIV_ID_RE = re.compile(r"\barXiv:(\d{4}\.\d{4,5}(v\d+)?)\b", re.IGNORECASE)

# Evidence-grade labels used as inline prose tags
EVIDENCE_LABEL_RE = re.compile(r"\b(?:proven|suggests|inferred)\b", re.IGNORECASE)
# But only flag when used as a grade label (e.g. "[proven]", "Grade: proven")
# not when used in natural prose like "this proves that..."
# We use a more specific pattern: grade-label usage
GRADE_LABEL_RE = re.compile(
    r"(?:\[?(?:proven|suggests|inferred)\]?)"
    r"|(?:grade\s*:\s*(?:proven|suggests|inferred))"
    r"|(?:evidence\s+(?:grade|level)\s*:\s*(?:proven|suggests|inferred))",
    re.IGNORECASE,
)

# Workflow jargon
WORKFLOW_JARGON_RE = re.compile(
    r"\bOMR\b|Evidence-Deep|THINK\s+mode|SYNTH\s+mode|ANALYZE\s+mode|"
    r"COLLECT\s+mode|Phase-Guard|tree-state",
    re.IGNORECASE,
)

# Gate names
GATE_NAME_RE = re.compile(
    r"\bGate\s+[ABDLMPT]\b|\bQA[12]\b|\bPHASE-GUARD\b", re.IGNORECASE
)

# Private artifact paths
PRIVATE_PATH_RE = re.compile(
    r"(?:docs/plans/|\.omr/|tree-state\.json|report-state\.json|"
    r"materials/(?:papers-raw|papers|web|github)/|docs/index/)",
    re.IGNORECASE,
)

# THINK ledger table or outcome stamps in public prose
THINK_LEDGER_RE = re.compile(
    r"THINK\s+Ledger|THINK\s+Passes|outcome\s+stamp", re.IGNORECASE
)
OUTCOME_STAMP_RE = re.compile(
    r"\b(?:hardened|refined|unchanged|killed)\b", re.IGNORECASE
)
# outcome stamps are only violations when adjacent to THINK/ledger context

# Evidence-grade label as inline tag like [PE-5] or [JC-1]
EVIDENCE_TAG_RE = re.compile(r"\[(?:PE|JC|SE|OE)-\d{1,4}\]", re.IGNORECASE)

# Internal gap IDs like [G-1], G-7
GAP_ID_RE = re.compile(r"(?<![\w-])\[?G-\d{1,4}\]?(?![\w-])", re.IGNORECASE)

# --- Linter ----------------------------------------------------------------

ALL_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("material_id", MATERIAL_ID_RE, "Internal material ID (P/W/G/S/E-NNN)"),
    ("arxiv_id", ARXIV_ID_RE, "Raw arXiv ID — convert to proper citation"),
    ("grade_label", GRADE_LABEL_RE, "Evidence-grade label in prose"),
    ("workflow_jargon", WORKFLOW_JARGON_RE, "Workflow jargon"),
    ("gate_name", GATE_NAME_RE, "Gate/QA name"),
    ("private_path", PRIVATE_PATH_RE, "Private artifact path"),
    ("think_ledger", THINK_LEDGER_RE, "THINK ledger reference"),
    ("evidence_tag", EVIDENCE_TAG_RE, "Internal evidence tag (PE/JC/SE/OE-NNN)"),
    ("gap_id", GAP_ID_RE, "Internal gap ID (G-NNN)"),
]

# outcome stamps are checked separately — only flag when near THINK/ledger context


def lint_text(text: str) -> list[dict[str, Any]]:
    """Lint a single text block. Returns list of violation dicts."""
    violations: list[dict[str, Any]] = []

    for label, pattern, description in ALL_PATTERNS:
        for match in pattern.finditer(text):
            line_num = text.count("\n", 0, match.start()) + 1
            # Get the line content for context
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            if line_end == -1:
                line_end = len(text)
            line_content = text[line_start:line_end].strip()

            violations.append(
                {
                    "type": label,
                    "line": line_num,
                    "match": match.group(0),
                    "description": description,
                    "context": line_content[:120],
                }
            )

    # Check for outcome stamps near THINK/ledger context
    for match in OUTCOME_STAMP_RE.finditer(text):
        # Check if within 100 chars of THINK or ledger
        context_start = max(0, match.start() - 100)
        context_end = min(len(text), match.end() + 100)
        context = text[context_start:context_end]
        if re.search(r"THINK|ledger|pass|outcome", context, re.IGNORECASE):
            line_num = text.count("\n", 0, match.start()) + 1
            violations.append(
                {
                    "type": "outcome_stamp",
                    "line": line_num,
                    "match": match.group(0),
                    "description": "THINK outcome stamp in public prose",
                    "context": context[:120],
                }
            )

    return violations


def find_report_files(
    workspace: Path, mode: str | None, file_path: Path | None
) -> list[Path]:
    """Find report files to lint."""
    if file_path is not None:
        return [file_path] if file_path.exists() else []

    if mode is None:
        # Auto-detect: check all mode dirs
        files: list[Path] = []
        for m in ("survey", "report", "manuscript", "brief"):
            mode_dir = workspace / "docs" / m
            if not mode_dir.exists():
                continue
            # chapters/ directory (incremental writing)
            chapters_dir = mode_dir / "chapters"
            if chapters_dir.exists():
                files.extend(sorted(chapters_dir.glob("*.md")))
            else:
                # single-file report
                for md in sorted(mode_dir.glob("*.md")):
                    if not md.name.startswith("_"):
                        files.append(md)
        return files

    # Specific mode
    mode_dir = workspace / "docs" / mode
    if not mode_dir.exists():
        return []

    chapters_dir = mode_dir / "chapters"
    if chapters_dir.exists():
        return sorted(chapters_dir.glob("*.md"))

    # single-file report
    return [f for f in sorted(mode_dir.glob("*.md")) if not f.name.startswith("_")]


def main() -> int:
    p = argparse.ArgumentParser(description="OMR publication-safety linter")
    p.add_argument("--workspace", type=Path, default=Path.cwd())
    p.add_argument("--mode", default=None, help="survey/report/manuscript/brief")
    p.add_argument("--file", type=Path, default=None, help="lint a specific file")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args()

    ws = args.workspace.resolve()
    files = find_report_files(ws, args.mode, args.file)

    if not files:
        if args.json:
            print(json.dumps({"files": [], "violations": [], "total": 0}))
        else:
            print("No report files found to lint.")
        return 0

    all_violations: list[dict[str, Any]] = []
    file_results: list[dict[str, Any]] = []

    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        violations = lint_text(text)
        rel_path = str(f.relative_to(ws)) if f.is_relative_to(ws) else str(f)
        file_results.append(
            {
                "file": rel_path,
                "violations": violations,
                "count": len(violations),
            }
        )
        all_violations.extend(violations)

    total = len(all_violations)

    if args.json:
        print(
            json.dumps(
                {
                    "files": file_results,
                    "total_violations": total,
                    "clean": total == 0,
                },
                indent=2,
            )
        )
    else:
        if total == 0:
            print(f"✓ {len(files)} file(s) scanned — no publication-safety violations.")
        else:
            print(f"✗ {len(files)} file(s) scanned — {total} violation(s) found:\n")
            for fr in file_results:
                if fr["count"] == 0:
                    continue
                print(f"  {fr['file']} ({fr['count']} violations):")
                for v in fr["violations"]:
                    print(
                        f"    L{v['line']} [{v['type']}] {v['match']!r} — {v['description']}"
                    )
                    print(f"      context: {v['context']}")
                print()

    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
