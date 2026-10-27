---
name: oh-my-research
description: Intelligent orchestrator for high-quality deep research reports from collected materials and evidence. Auto-detects intent and workspace state, then routes to init, collect, deep analyze (with THINK paradigms such as first principles), optional decide/idea, synthesize survey/report, reconcile, or version. Single entry point for the report-first research lifecycle.
license: Apache-2.0
metadata:
  version: "2.0.0"
  author: "Xiaming Chen"
  category: "workflow"
---

# Oh-My-Research

Intelligent orchestrator for **report-first deep research**. Auto-detects user intent and workspace state, then executes the right mode — initialize, collect materials, deep-analyze with evidence boundaries and thinking paradigms, synthesize a survey/report, or maintain state.

**North star:** high-quality deep research reports from collected materials and evidence — not prototypes, not coding validation.

## When to Use This Skill

- **Start** a research workspace on a topic
- **Collect** papers, URLs, repos, datasets
- **Analyze** materials into evidence maps and judgments
- **Deepen** analysis with first principles, Socratic, triangulation, etc. (THINK)
- **Write** a survey, report, manuscript, or brief
- **Reconcile** when new evidence contradicts prior claims
- **Run** the full Evidence-Deep workflow

**Keywords**: research, survey, literature review, evidence, collect papers, analyze, first principles, synthesize report, deep research, oh-my-research, omr

## Core Pipeline (Evidence-Deep)

```
COLLECT materials → [Gate M] → ANALYZE (deep evidence + THINK) → [Gate A] → [Gate P] → SYNTH (survey / report)
```

Optional: IDEA, DECIDE (stance), RECONCILE. Default pattern: **Evidence-Deep**. See `references/GRAPH.md` and `patterns/`.

## Auto-Detection Decision Tree

The agent runs **intention detection first**, then falls back to **workspace-state detection**. Canonical op names (`init`, `collect`, `analyze`, `think`, `synth`, `decide`, `idea`, `reconcile`, `workflow`, `qa`) **always win** over keyword routing.

```mermaid
flowchart TD
    START([User request]) --> OP{Canonical op<br/>in request?}
    OP -- Yes --> RUNOP[Run named op — wins]
    OP -- No --> INT{Intent keywords?}

    INT -- THINK keywords<br/>first principles, socratic,<br/>pre-mortem, red team, steelman,<br/>deepen, rethink, elicit, think --> THINK[THINK on latest artifact]
    INT -- IDEA keywords<br/>idea, brainstorm, speculate,<br/>what if, hypothesis --> IDEA[IDEA mode]
    INT -- COLLECT signals<br/>URL, DOI, arxiv, github,<br/>huggingface, search, collect --> COLLECT[COLLECT — init-on-demand<br/>if no workspace]
    INT -- SYNTH keywords<br/>report, survey, write up,<br/>synthesize, manuscript, brief --> SYNTHGUARD{Phase-Guard:<br/>judgment + gate-a present?}
    INT -- none --> STATE[Inspect workspace state]

    COLLECT --> GATEM[Run Gate M:<br/>source diversity + sufficiency]
    GATEM --> ANALYZE

    SYNTHGUARD -- Yes --> SYNTH[SYNTH mode]
    SYNTHGUARD -- No, missing --> BLOCKSYNTH[Show PHASE-GUARD<br/>offer ANALYZE first]

    STATE --> S1{No AGENTS.md<br/>and no .omr/?}
    S1 -- Yes --> INIT[INIT]
    S1 -- No --> S2{Materials present,<br/>no judgment?}
    S2 -- Yes --> GATEM
    S2 -- No --> S3{Judgment present,<br/>no synth content?}
    S3 -- Yes --> SYNTHGUARD
    S3 -- No --> S4{loop-state active?}
    S4 -- Yes --> GATEL[Gate L:<br/>iterate vs advance]
    S4 -- No --> S5{Contradiction vs<br/>published claims?}
    S5 -- Yes --> RECONCILE[Propose RECONCILE]
    S5 -- No --> AMBIG[Ambiguous → ask user<br/>or show graph-recommended next]

    GATEL --> AMBIG
    THINK --> GATEA[Gate A / QA1]
    GATEA --> SYNTHGUARD
    BLOCKSYNTH --> ANALYZE
    ANALYZE --> GATEA
```

**Always show a phase label** at the start of each action: `[INIT]`, `[COLLECT]`, `[ANALYZE]`, `[THINK]`, `[SYNTH]`, `[RECONCILE]`, `[FINISHED]` (plus `[DECIDE]` / `[IDEA]` when used).

## Phase-Guard: Cross-Stage Jump Protection

Before routing to a stage, **read `.omr/tree-state.json`** and check whether the target stage is `unlocked`, `ready`, or `completed`. If `locked`, verify the required **prerequisite artifacts** exist on disk before proceeding. This prevents silent stage-skipping (e.g. user says "write report" → SYNTH keyword detected → but no `judgment-*.md` exists).

| Target stage | Required prerequisite artifacts | Required gate JSON | If missing |
|---|---|---|---|
| ANALYZE | `materials/` with ≥1 source + `docs/index/` entry | `gate-m.json` (source diversity + sufficiency, run during ANALYZE) | Route to COLLECT first |
| THINK | `docs/plans/judgment-*.md` or `docs/plans/evidence-*.md` | (none) | Route to ANALYZE first |
| SYNTH | `docs/plans/judgment-*.md` | `gate-a.json` (pass) + `gate-p.json` | Route to ANALYZE → THINK → Gate A → Gate P first |
| DECIDE | `docs/plans/judgment-*.md` | (none) | Route to ANALYZE first |

**Blocking by default.** The agent must not proceed past a missing prerequisite without either (a) satisfying the prerequisites or (b) receiving an explicit user override (e.g. "I know, just write the report" or "skip guard"). A general instruction like "write the report" does **not** count as an override. When overridden, record `scenario_note: "prerequisite skipped by user override"` in the next gate JSON for auditability.

**Tree-state staleness:** after every op, update `.omr/tree-state.json` — move completed stages to `completed`, unlock dependents, write a brief `notes` summary. A stale tree-state signals an interrupted workflow; check and refresh it at the start of any new op.

## Operation Modes

| Mode | Op | One-line | Detail |
|------|----|----------|--------|
| INIT | `init "<topic>"` | Bootstrap workspace (only `AGENTS.md` + `.omr/*.json`; no empty folders) | `references/INIT/init.md` |
| COLLECT | `collect <url\|query\|…>` | Default **papers+web+github+search** (parallel bucket agents) → materials + indexes + full-text Markdown | `references/COLLECT/collect.md` |
| ANALYZE | `analyze` | Brief, evidence-map, judgment; reads full-text Markdown; Gate M before, Gate A / QA1 after, Gate T after THINK | `references/ANALYZE/analyze.md` |
| THINK | `think [method]` | Methodology-driven elicitation on research artifacts (never code); stamps `hardened`/`refined`/`unchanged`/`killed` | `references/THINK/think.md`, `references/THINK/methods/` |
| SYNTH | `synth [--mode] [--format docx\|pdf\|md] [--language] [--resume] [--chapter] [--no-wiki]` | Incremental long reports in preferred language; Gate P confirms prefs; never one-shot a deep report; exports land in `deliverables/` | `references/SYNTH/synth.md`, `references/SYNTH/long-report.md`, `references/LANGUAGE.md` |
| IDEA | `idea "…"` | Capture speculative notes (optional) | `references/IDEA/idea.md` |
| DECIDE | `decide` | Stance / claim framing with ≥3 alternatives; Gate B (optional) | `references/DECIDE/decide.md` |
| RECONCILE | `reconcile` | Contradiction blast-radius, archive, rollback | `references/RECONCILE/reconcile.md` |
| VERSION | — | Workspace artifact versioning: tag, history, diff, backup, list | `references/VERSION/version.md` |
| WORKFLOW | `workflow [--pattern P]` | Graph-driven multi-step Evidence-Deep (or other pattern) | `references/WORKFLOW/workflow-overview.md` |
| QA | `qa qa1\|qa2\|all\|state-check` | LLM QA checklists; `state-check` reconciles disk vs tree-state | `references/GATES.md` |

## Confirmation Gates

Default **semi-automated** (pause for confirm). Support "no confirmations" / quick-pass. Rapid pattern skips all gates (fully-automated).

| Gate | When |
|------|------|
| M | After COLLECT: source diversity & enough materials? Shows diversity report, asks user: collect more types or proceed? |
| L | Loop pattern: iterate vs advance |
| A / QA1 | After ANALYZE judgment, before unlock SYNTH |
| T | After THINK: collect more from surfaced gaps? |
| B | Only if DECIDE runs |
| P | Before SYNTH: language / format / mode / audience / register / citations |
| Lenses | Structure → Prose → Adversarial before Gate D |
| D / QA2 | Before publishing SYNTH |

**Post-Step Routing Menu** (after Gate M / IDEA / Gate A / THINK proceed / Gate T / Gate B): (1) Pause at each gate (default) · (2) Quick pass · (3) Continue recommended (next graph edge) · (4) Run THINK · (5) Switch pattern · (6) Stop.

## Default Paths

Paths below are **logical destinations**. Create a folder only when writing the first file into it (see `references/INIT/init.md`).

**Two surfaces.** `deliverables/` at the project root is the only public, reader-facing surface — everything a user reads or shares lands there. `materials/`, `docs/`, and `.omr/` are private working state and never leave the workspace.

| Artifact | Path (when content exists) |
|----------|------|
| State (private) | `.omr/` (tree-state, pattern, locale; other JSON as needed) |
| Materials (private) | `materials/{papers-raw,papers,web,github,datasets,search,failed}/` — papers: raw binaries in `papers-raw/`, Markdown in `papers/` (same stem); other buckets only when they receive files |
| Indexes (private) | `docs/index/` (`papers-index.json`; workers use `docs/index/inbox/` then merge) |
| Plans (private) | `docs/plans/` |
| Ideas (private) | `docs/ideas/` |
| Report drafts (private) | `docs/{survey,report,manuscript,brief}/` — outline, chapters, citation map, continuity, presentation spec |
| **Deliverables (public)** | **`deliverables/`** — exported `<topic>-<mode>-<lang>.docx\|pdf\|md`; optional `deliverables/wiki/` |
| Archive (private) | `docs/archive/` |

Templates: `assets/`. Patterns: `patterns/`. Full operation reference: `references/REFERENCE.md`.

## Best Practices

1. Trust auto-detection; override with canonical ops when needed
2. **Phase-Guard before every stage (blocking by default)** — read `.omr/tree-state.json`, check prerequisites, show `[PHASE-GUARD]` if missing; never silently skip a stage
3. Never create empty directories — mkdir only as the parent of a real file write
4. Never upgrade `suggests` → `proven` without stronger source language
5. Use THINK (first principles / triangulation) before Gate A when confidence is low — in Evidence-Deep, THINK is offered by default after judgment, not only when confidence is low
6. **Run Gate M after every collect batch** — default collect fills papers, web, github, and search (parallel bucket agents). Show the diversity report; warn if a default bucket is empty **without** an explicit opt-out. Prevents premature analysis on narrow or single-type corpora
7. Write long reports chapter-by-chapter to disk; keep a pruned continuity brief; author `.omr/report-state.json` to match the topic outline; resume if interrupted
8. Prefer a professionally formatted DOCX, PDF, or Markdown deliverable in the preferred language (timezone/locale auto-detect via `LANGUAGE.md` / `.omr/locale.json`, or explicit `--language`); drive its presentation via an LLM-authored `_document.json` (title, fonts, cover, TOC, header/footer, chapter order) rather than script defaults
9. Keep internal traceability private; translate it into standard citations and natural prose
10. Design SYNTH as a reader journey before a chapter list: define the reader's starting point and destination, argument spine, canonical dimensions, concept ladder, and chapter contracts; follow `references/SYNTH/narrative-coherence.md`
11. Make the final report self-contained, professional, and accessible to its intended reader; define terms and premises before use, preserve one taxonomy and claim state, and run the reverse-outline Narrative Audit plus Consistency & Polish pass before export
12. **Write in the report language, not through it** — apply `references/SYNTH/native-expression.md`: test every metaphor's provenance, use native heading style and sentence rhythm, avoid English-derived coinages, and clear all `high` findings from `scripts/prose_lint.py` before Gate D
13. Run LLM QA checklists (adapt thresholds to the scenario); write results under `.omr/quality-gates/`
14. Write full reports to disk; reply in chat with summary only
15. Run document lenses and visually inspect the rendered file before Gate D
16. **Update `.omr/tree-state.json` after every op** — move completed stages to `completed`, unlock next stages; never leave tree-state stale

## Dependencies

- Read/write project workspace
- Agent-authored state under `.omr/` (tree, loop, report-state, quality-gates) — see `references/LLM-STATE.md`
- Mechanical scripts only: `export_report.py` (thin, spec-driven DOCX/PDF/Markdown renderer applying LLM-authored `_document.json`; the Markdown deliverable passes Mermaid figures and GFM tables through verbatim), `prefer_language.py` (timezone/locale → BCP-47 language tag), `version_control.py` (workspace tags/backups), `collect_cli.py` (records source + invokes `material_to_markdown.py`; `--id`/`--bucket`/`--inbox` for parallel workers, `--merge-inbox` for the coordinator), `material_to_markdown.py` (downloads source via arxiv/DOI/preprint hosts (ACL Anthology, bioRxiv, medRxiv, OpenReview, Zenodo, SSRN, HAL)/URL; papers persist `materials/papers-raw/<ID>.<ext>` and convert to `materials/papers/<ID>.md`; other buckets write `materials/<bucket>/<ID>.md`; **anydoc** with pymupdf/pdfplumber/markdownify fallbacks; `--index` batch-converts/retries every indexed source lacking a `.md`, `--convert-dir` batch-converts pre-downloaded files), `report_lint.py` (publication-safety linter: scans report chapters for leaked internal IDs, evidence-grade labels, workflow jargon, gate names, and private paths), `prose_lint.py` (native-expression linter: flags calqued metaphors, English-derived coinages, article-style CJK headings, wrong measure words, 的-chains, passive/em-dash stacking, and over-long sentences; `--strict` fails on medium findings, `.omr/prose-lint-allow.txt` allowlists field-standard terms)
- `python-docx` / `reportlab` via `scripts/requirements.txt` for export; **anydoc** (`npx -y @firecrawl/anydoc`, Node 20+) for material → Markdown conversion; optional `pymupdf` / `pdfplumber` / `markdownify` / `beautifulsoup4` as fallbacks if anydoc is unavailable

## Deep Dive

- `references/REFERENCE.md` — complete operation guide, artifact naming, evidence boundaries, tree state, troubleshooting
- `references/GRAPH.md` — pattern graphs, node ↔ artifact contracts, unlock rules, cycles
- `references/GATES.md` — gate definitions and QA checklists
- `references/LLM-STATE.md` — agent-owned state JSON schemas
- `references/LANGUAGE.md` — timezone/locale → preferred BCP-47 language tag
- `references/SYNTH/long-report.md` — incremental report state, chapter loop, continuity, and final review
- `references/SYNTH/narrative-coherence.md` — reader journey, argument spine, concept order, self-containment, and Narrative Audit
- `references/SYNTH/native-expression.md` — metaphor provenance, native heading style, sentence-rhythm budgets, and the translationese scan
- `references/COLLECT/collect.md` — default four-bucket mix + parallel workers
- `references/COLLECT/agents/bucket-worker.md` — per-bucket collect agent
