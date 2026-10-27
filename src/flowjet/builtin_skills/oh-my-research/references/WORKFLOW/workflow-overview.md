# Workflow Overview — Evidence-Deep

## Objective

Run the default report-first lifecycle with clear phase visibility:

```
[INIT] → [COLLECT] → [ANALYZE] (+ [THINK]) → [SYNTH] → [FINISHED]
```

## Phase visibility

Always show current phase in status lines, e.g. `[ANALYZE] Pattern: Evidence-Deep`.

## End-to-end path

### 1. INIT

```
init "agent memory mechanisms"
```

Creates **only** `AGENTS.md`, `.omr/tree-state.json`, `.omr/pattern.json`, `.omr/locale.json` (language from timezone). No empty content folders.

### 2. COLLECT

```
collect https://arxiv.org/abs/2401.xxxxx
collect "lifecycle formation evolution survey"
```

Materials land under `materials/<bucket>/` only for buckets that receive files (papers: raw binaries in `papers-raw/`, Markdown in `papers/`). Default COLLECT fills papers, web, github, and search in parallel (inbox merge into `docs/index/`). Run **Gate M** (source diversity & sufficiency — shows diversity report, asks user: collect more types or proceed?). On pass → `analyze` becomes ready. On warn/fail → suggest specific source types to collect.

### 3. ANALYZE

```
analyze
```

**Gate M** first: source diversity & enough materials for the intended scope? Shows diversity report (papers, web, github, datasets, models). Asks user: collect more types or proceed? If not, ask to `collect` more.

Produces brief, evidence-map, judgment (id `R-001`).  
Depth checkpoint: offer `think first-principles` or Source Triangulation when confidence/gaps warrant.

```
think first-principles
```

User confirms edits → refresh judgment. Then **Gate T**: did THINK surface load-bearing gaps? If so, ask to `collect` more or proceed.

Present **Gate A / QA1**. On pass → unlock SYNTH.

### 4. SYNTH

```
synth --mode survey --format docx --language en
```

**Gate P** first: confirm language / format / mode / audience / citations before outlining.

**Long-report path (required for deep surveys):**

1. Outline + citation map + LLM-authored `.omr/report-state.json`  
2. Write one chapter per turn into `docs/survey/chapters/`  
3. Update `_continuity.md` after each chapter  
4. Resume with `synth --resume` if interrupted  
5. Write abstract last → lenses → author `_document.json` presentation spec → LLM QA2 → export DOCX/PDF/Markdown → Gate D  

See `references/SYNTH/long-report.md`. Chat: progress only.

### 5. FINISHED

```
version tag v1.0-survey
```

Optional: more `collect` + `reconcile` if new contradictory papers arrive.

## workflow op

```
workflow
workflow --pattern Evidence-Deep
workflow --pattern Rapid
```

Runs recommended next steps along the active graph, pausing at gates unless user requested quick-pass / no confirmations.

## Alternate patterns (short)

| Pattern | Path |
|---------|------|
| Evidence-First | collect → analyze → synth (THINK optional) |
| Idea-First | idea → collect → analyze ⟲ think → synth (brief) |
| Stance-First | decide → collect → analyze → synth (report) |
| Loop | Gate L cycles then synth |
| Rapid | collect → analyze → synth, gates off |

## When to ask the user

- Research question wording (ANALYZE)
- **Gate M**: enough materials before analyzing? (source diversity report — collect more types?)
- **Gate T**: after THINK, collect more from surfaced gaps?
- **Gate P**: language / format / mode / audience / citations before synth
- Other gate confirmations (unless quick-pass)
- THINK method choice when menu shown

## Phase files

- This file — overview + Evidence-Deep e2e
- `workflow-phases.md` — phase checklist detail
