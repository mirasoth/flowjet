# LLM-Driven State & Quality

Judgment, structure, and progress tracking are **agent-owned**. Do not rely on Python helpers to invent chapter plans, pass/fail research quality, or pick thinking methods.

## Principle

| Concern | Owner |
|---------|--------|
| Research judgment, outlines, gates, method choice, continuity | **LLM** following reference docs |
| Report content **and presentation** (title, fonts, colors, cover, TOC, header/footer, chapter order) — via `_document.json` | **LLM** authoring the spec |
| Bytes on disk: DOCX/PDF/Markdown render from spec, version backups, skill semver sync, URL indexing + full-text Markdown conversion (anydoc + fallbacks) | **Scripts** (`export_report.py`, `version_control.py`, `skill_version.py`, `collect_cli.py`, `material_to_markdown.py`) |

`export_report.py` is a **thin renderer**: it applies the LLM-authored `docs/<mode>/_document.json`, not hardcoded styling. It never invents structure or layout — it renders exactly what the spec + chapters describe.

When a scenario differs (short brief, Chinese industry report, 20-theme survey, single-paper deep dive), **adapt the JSON/Markdown artifacts** — do not force a fixed script template.

## Files the agent writes directly

### `.omr/collect-batch.json`

Written at the start of a parallel COLLECT wave: topic, per-bucket caps, reserved IDs, user source assignments. Workers read it; they do not rewrite it. Safe to delete after `--merge-inbox`.

### `.omr/tree-state.json`

Update after each op using unlock rules in `GRAPH.md`. Example shape:

```json
{
  "unlocked": ["init", "collect", "idea", "think"],
  "ready": ["analyze"],
  "locked": ["synth", "decide", "reconcile"],
  "completed": ["init", "collect"],
  "gate_m": {
    "status": "pass",
    "run_at": "2026-08-20T10:00:00+08:00",
    "diversity": {"papers": 2, "web": 5, "github": 1, "datasets": 0, "models": 0},
    "gaps": ["datasets/models empty — acceptable for this scope"]
  }
}
```

Adapt freely: unlock `synth` early for Rapid; keep `decide` locked forever if unused. Gate M result is recorded under `.omr/quality-gates/gate-m.json` and summarized in tree-state for quick reference.

### Tree-state pre-flight check (v1.4 — blocking by default)

**Before executing any op, the agent must read `.omr/tree-state.json` and verify the target stage is permitted.** This is a mandatory pre-flight check, not optional.

**Check procedure:**

1. Read `.omr/tree-state.json` (create defaults if file missing)
2. **Startup reconciliation** (v1.4): scan disk for actual artifacts and auto-correct stale tree-state (see § Startup reconciliation below)
3. Check if the target stage is in `unlocked`, `ready`, or `completed`
4. If `locked`, check if required prerequisite artifacts exist on disk (see `GRAPH.md` § Cross-Stage Jump Protection)
5. If prerequisites are met, update tree-state to unlock the stage, then proceed
6. If prerequisites are missing, show `[PHASE-GUARD]` notice and **block** — do not proceed unless the user explicitly overrides

**v1.4 change — blocking by default:** The Phase-Guard is now **blocking by default**. The agent must not proceed past a missing prerequisite without an explicit user override. An override is only recognized when the user uses explicit language such as "I know, skip to SYNTH" or "override phase-guard" — a general task instruction like "write the report" does **not** count as an override.

When the user explicitly overrides, record `scenario_note: "prerequisite skipped by user override"` in the next gate JSON, and proceed — but the guard must have been shown first.

**Common failure modes this prevents:**

| Failure | Example | Prevention |
|---|---|---|
| Stage skip | User says "write report" → agent jumps to SYNTH without ANALYZE | SYNTH pre-flight checks for `judgment-*.md` + `gate-a.json` |
| Stale state | tree-state says `completed: ["init", "collect"]` but ANALYZE was run | Agent checks artifact existence, not just tree-state |
| Silent THINK skip | Evidence-Deep pattern, but THINK never offered after judgment | Gate A checks for THINK ledger entry |

**After every op, update tree-state:**

```json
{
  "unlocked": ["init", "collect", "idea", "think"],
  "ready": ["synth"],
  "locked": ["decide", "reconcile"],
  "completed": ["init", "collect", "analyze"],
  "gate_m": {"status": "pass", "diversity": {"papers": 3, "web": 5, "github": 1}},
  "notes": "Gate A passed. THINK: 1 pass (first-principles, hardened). synth ready for Gate P."
}
```

**Never leave tree-state stale** — if the agent runs an op but forgets to update tree-state, the next op's pre-flight check will detect the inconsistency (artifacts exist but tree-state doesn't reflect them) and auto-correct.

**Startup reconciliation (v1.4 new):** At the beginning of **every** op — before any other logic — the agent must perform a disk-vs-state reconciliation:

1. Read `.omr/tree-state.json`
2. Scan disk for actual artifacts:
   - `docs/plans/brief-*.md`, `evidence-*.md`, `judgment-*.md` → ANALYZE completed
   - `.omr/quality-gates/gate-*.json` → corresponding gates passed
   - `docs/{survey,report,manuscript,brief}/chapters/` or report files → SYNTH in progress/completed
   - `deliverables/*` → SYNTH exported (public hand-off present)
   - `.omr/report-state.json` → SYNTH resume state
3. Compare disk reality against tree-state:
   - If disk has artifacts that tree-state doesn't reflect → **auto-correct** tree-state (mark stages completed, unlock next stages)
   - If tree-state claims a stage is completed but disk lacks artifacts → **flag inconsistency** in `notes` and downgrade to `ready` or `locked`
4. If the target op's prerequisites are still missing after reconciliation → show `[PHASE-GUARD]` (blocking — see `SKILL.md` § Phase-Guard)

This reconciliation prevents the common failure mode where an agent runs an op but forgets to update tree-state, and a subsequent session starts from stale state and re-skips stages. The disk is the ground truth; tree-state is a cache that must be reconciled against it.

**Manual reconciliation command (v1.4 new):** The agent or user can trigger reconciliation explicitly:

```
qa state-check
```

This runs the full disk-vs-state reconciliation, proposes a corrected `tree-state.json`, and lists missing gates/artifacts. Use this when resuming an interrupted workspace or auditing workflow compliance.

### `.omr/loop-state.json`

Only when Loop is active. Agent sets fields from Gate L discussion:

```json
{
  "active": true,
  "mode": "deep-analyze",
  "iteration": 2,
  "focus_question": "…",
  "gaps": ["…"],
  "history": [{"at": "ISO-8601", "event": "iterate", "note": "…"}]
}
```

### `.omr/locale.json`

Preferred report/chat language from timezone (or user override):

```json
{
  "language": "ja",
  "source": "timezone",
  "timezone": "Asia/Tokyo",
  "detected_at": "2026-08-18T20:00:00+09:00"
}
```

BCP-47 tags (`en`, `zh-CN`, `zh-TW`, `ja`, `de`, `pt-BR`, …). See `LANGUAGE.md`. Explicit `--language` always wins over this file.

### `.omr/pattern.json`

```json
{ "name": "Evidence-Deep" }
```

Or any pattern from `patterns/` / user-defined under `.omr/patterns/` — a custom pattern is a `.omr/patterns/<name>.json` file using the same schema as `patterns/*.json` (nodes, edges, optional `cycles[]`), agent-authored and optional; `pattern.json` simply names it.

### `.omr/report-state.json`

Built from the **topic-specific outline**, not a fixed theme-a/b/c list. See `SYNTH/long-report.md`.

### `.omr/quality-gates/QA1-*.json` / `QA2-*.json`

Agent evaluates checklists in `GATES.md` and writes results with rationale — scale thresholds to the research scenario.

## INIT without a script

1. Create `AGENTS.md` from `assets/templates/AGENTS.md.template` (fill placeholders for this topic).
2. Create `.omr/tree-state.json`, `.omr/pattern.json`, and `.omr/locale.json` (timezone→language; see `LANGUAGE.md` / `prefer_language.py --write-workspace`).
3. **Never** pre-create empty `materials/`, `docs/`, `deliverables/`, or other content dirs — mkdir only as the parent of a real file write (see `INIT/init.md`).

## THINK without a registry script

1. Read `THINK/methods.md` (and optionally `assets/think/methods.csv` as a catalog).
2. Choose 5 best-fit methods for **this** artifact and user intent.
3. Load the method's playbook from `THINK/methods/<slug>.md` (index in `methods/README.md`) and apply its procedure.
4. Produce revelations (≥1, never default-agree) + proposed edits + outcome stamp; confirm before mutating.
5. Record the pass in the judgment's THINK ledger.

## QA (LLM checklist)

1. Read the relevant artifacts.
2. Apply QA1 or QA2 checklist in `GATES.md`; adjust numeric expectations to scope (e.g. a 3-paper deep dive can pass QA1 with an explicit “narrow corpus” rationale).
3. Write JSON under `.omr/quality-gates/` with `status`, `checks[]` (`id`, `status`, `details`), and `rationale` / `scenario_note`.
4. Fail closed on publication-safety and over-claiming; be flexible on coverage counts.

## Gate M (LLM checklist — source diversity & sufficiency)

1. After COLLECT saves materials, scan `materials/` buckets and `docs/index/`.
2. Apply Gate M checklist in `GATES.md`; adapt diversity thresholds to scope (e.g. a narrow 3-paper deep dive can pass with an explicit "narrow corpus" rationale; a broad survey needs wider source-type diversity).
3. Write JSON under `.omr/quality-gates/gate-m.json` with `status`, `checks[]`, `diversity` inventory, `suggested_collects`, and `scenario_note`.
4. **Show the diversity report to the user** and ask: collect more source types or proceed?
5. On warn/fail: suggest specific source types and queries to collect next; do not unlock analyze.

## Report progress (LLM-authored state)

1. After outline approval, write `.omr/report-state.json` mirroring `_outline.md` chapters (topic-specific IDs — not fixed theme-a/b/c).
2. Each turn: set `current`, write chapter file, mark that chapter `done`, prune `_continuity.md`.
3. Resume = read report-state + continue first not-done chapter in `writing_order` (abstract/`00-*` last).

## Presentation spec (LLM-authored)

Before export, write `docs/<mode>/_document.json` (start from `assets/synth/_document.json` or `export_report.py --emit-spec`). Decide, per report/audience/language:

- title / subtitle / author / date; page size + margins; line spacing
- fonts: body + heading Latin, `eastasia` for DOCX CJK, `pdf_cjk` for PDF CJK
- heading colors + sizes; table header color
- `cover` elements + order (or disable); `toc` on/off + depth; `header.text`; `footer.page_numbers`
- `chapters.order` / `include` / `exclude` for publication ordering

Omit any field to accept the neutral default. Never rely on the script to choose styling.

## Still use scripts for

```bash
# Author/refresh the presentation spec (then edit docs/survey/_document.json)
python scripts/export_report.py --emit-spec --mode survey

# Final render — applies the LLM-authored spec (mechanical)
python scripts/export_report.py --mode survey --format docx --language en

# Snapshots / tags (workspace research artifacts)
python scripts/version_control.py tag v1.0

# Skill package semver (from oh-my-research repo root)
python skills/oh-my-research/scripts/skill_version.py check
python skills/oh-my-research/scripts/skill_version.py bump minor --message "…"

# Optional: record a URL into materials/index
python scripts/collect_cli.py "https://arxiv.org/abs/…"
```

`export_report.py` still enforces a mechanical publication-safety scan before writing DOCX/PDF/Markdown — fix prose if it rejects.

`skill_version.py` syncs package semver only; it does not tag research workspaces.
