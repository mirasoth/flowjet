# OMR Scripts

**Scripts are mechanical only.** Judgment, outlines, gates, THINK method choice, and progress tracking are LLM-driven — see `references/LLM-STATE.md` and `references/GATES.md`.

| Script | Role |
|--------|------|
| `export_report.py` | Thin, spec-driven renderer: applies the LLM-authored `docs/<mode>/_document.json` to turn `chapters/` into publication-safe DOCX/PDF/Markdown. No hardcoded styling. Default output is the public hand-off `<workspace>/deliverables/<topic>-<mode>-<language>.<format>` (`--output` overrides). Default `--language` follows timezone/workspace via `prefer_language.py`. |
| `prose_lint.py` | Native-expression linter: detects translationese — calqued metaphors, English-derived coinages, article-style CJK headings (一个…), wrong measure words, 的-chains, passive/em-dash stacking, over-long sentences. Reports per-file budgets (avg sentence length, dash/1k, passive/1k). Exit 1 on `high` findings; `--strict` also fails on `medium`; allowlist via `--allow` or `.omr/prose-lint-allow.txt`. |
| `prefer_language.py` | Detect preferred BCP-47 language from timezone/locale; optional `.omr/locale.json` write; `--list` dumps timezone map |
| `version_control.py` | Workspace research tags and backups (`.omr/versions/`, `.omr/backups/`); covers `docs/plans`, synth draft dirs, and `deliverables/` |
| `skill_version.py` | Skill-package semver: `show` / `check` / `sync` / `set` / `bump` against `SKILL.md` (+ marketplace + `CHANGELOG.md`) |
| `collect_cli.py` | Record a URL/query into `materials/` + index (creates only parent dirs of files written). `--convert` (default on) invokes `material_to_markdown.py`. Parallel COLLECT: `--id` + `--bucket` + `--inbox` writes `docs/index/inbox/<ID>.json` without touching `papers-index.json`; `--merge-inbox` appends inbox files into the index (skips duplicate IDs). |
| `material_to_markdown.py` | Download a source (arxiv / DOI / direct URL / local file) and convert it to GitHub-Flavored Markdown. Papers persist the binary at `materials/papers-raw/<ID>.<ext>` and write Markdown at `materials/papers/<ID>.md` (same stem). Other buckets write `materials/<bucket>/<ID>.md`. Uses **anydoc** (`npx -y @firecrawl/anydoc`) as the preferred converter, with `pymupdf` → `pdfplumber` (PDF) and `markdownify` (HTML) as fallbacks. Markdown/`.txt` files pass through unchanged. Failures are recorded to `materials/failed/<ID>.failed.txt`. |
| `report_lint.py` | **(v1.4)** Publication-safety linter: scans report chapters for internal material IDs, raw arXiv IDs, evidence-grade labels, workflow jargon, gate names, private paths, THINK ledger references, and outcome stamps. Exit 0 = clean, 1 = violations found. Use before Gate D to catch leaked internal terminology. |

Install export dependencies (macOS or Linux):

```bash
python3 -m pip install -r scripts/requirements.txt
```

**Linux PDF symbol coverage** (optional but recommended):

```bash
# Debian/Ubuntu
sudo apt-get install -y fonts-dejavu fonts-noto-core fonts-noto-cjk
# Fedora
sudo dnf install -y dejavu-sans-fonts google-noto-sans-fonts google-noto-sans-cjk-fonts
```

PDF CJK text uses reportlab's built-in CID fonts (`STSong-Light`, etc.) and needs no system Chinese fonts. DOCX East Asian face names default to `Noto Sans CJK SC` on Linux / `PingFang SC` on macOS / `Microsoft YaHei` on Windows — override in `_document.json` if needed.

All scripts use `#!/usr/bin/env python3` and the stdlib `pathlib` API; they are intended to run unchanged on macOS and Linux.
Examples:

```bash
# 1. Author/refresh the presentation spec, then edit docs/<mode>/_document.json
python3 scripts/export_report.py --emit-spec --mode survey

# 2. Render, applying that spec
python3 scripts/export_report.py --mode survey --format docx --language en
python3 scripts/export_report.py --mode report --format pdf --language zh-CN
python3 scripts/version_control.py tag v1.0
python3 scripts/skill_version.py show
python3 scripts/skill_version.py check
python3 scripts/skill_version.py bump patch --message "Fix export edge case"
python3 scripts/collect_cli.py "https://arxiv.org/abs/…"
python3 scripts/collect_cli.py "https://arxiv.org/abs/…" --no-convert   # index only, no download/convert
python3 scripts/collect_cli.py "https://arxiv.org/abs/…" --id P-001 --bucket papers --inbox
python3 scripts/collect_cli.py --merge-inbox --workspace .
python3 scripts/material_to_markdown.py "https://arxiv.org/abs/…" --id P-001 --workspace .
python3 scripts/material_to_markdown.py --index --workspace .            # convert all indexed sources lacking .md
python3 scripts/material_to_markdown.py --convert-dir materials/papers-raw   # batch convert raw PDFs → materials/papers/<stem>.md
python3 scripts/report_lint.py --mode survey --workspace .               # (v1.4) lint report chapters
python3 scripts/report_lint.py --file docs/survey/my-report.md --json     # (v1.4) lint a single file, JSON output
```

Skill package versioning (from **repo root**):

```bash
python3 skills/oh-my-research/scripts/skill_version.py bump minor --message "…"
```

`skill_version.py` manages the skill package only. Workspace research tags stay on `version_control.py`.

Long reports: the agent writes `.omr/report-state.json`, `docs/<mode>/chapters/`, and `docs/<mode>/_document.json` per `references/SYNTH/long-report.md`, then calls `export_report.py`. Presentation (fonts, cover, TOC, colors, chapter order) is decided in `_document.json`, not the script. Working `_*.md` files are not exported (`_document.json` is read but not rendered as content).

`export_report.py` refuses unsafe internal terminology at render time — fix prose and retry.

Python 3.10+ recommended.
