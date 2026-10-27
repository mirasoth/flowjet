# Oh-My-Research — Complete Reference

Detailed operation guide for the unified OMR skill.

## Operations Index

| Mode | Ops | Reference |
|------|-----|-----------|
| INIT | `init` | `INIT/init.md` |
| COLLECT | `collect` | `COLLECT/collect.md` |
| ANALYZE | `analyze` | `ANALYZE/analyze.md` |
| THINK | `think [method]` | `THINK/think.md`, `THINK/methods.md`, `THINK/methods/` (playbooks) |
| SYNTH | `synth [--mode] [--format] [--language] [--resume] [--chapter] [--no-wiki]` | `SYNTH/synth.md`, `SYNTH/long-report.md` |
| QA | `qa qa1\|qa2\|all\|state-check` | `GATES.md`, `LLM-STATE.md` |
| IDEA | `idea` | `IDEA/idea.md` |
| DECIDE | `decide` | `DECIDE/decide.md` |
| RECONCILE | `reconcile`, `archive`, `rollback`, `list` | `RECONCILE/reconcile.md` |
| WORKFLOW | `workflow [--phase N] [--pattern P]` | `WORKFLOW/workflow-overview.md` |

Cross-cutting: `GATES.md`, `GRAPH.md`, `LLM-STATE.md`, `LANGUAGE.md`.

---

## Auto-Detection Decision Tree

The full decision tree — intention detection, workspace-state detection, and Phase-Guard routing — lives in `../SKILL.md` as a Mermaid flowchart. Canonical op names (`init`, `collect`, `analyze`, `think`, `synth`, `decide`, `idea`, `reconcile`, `workflow`, `qa`) always win over keyword routing.

**Intent keyword summary** (case-insensitive):

| Signal | Route |
|---------------------------|-------|
| `first principles`, `socratic`, `pre-mortem`, `red team`, `steelman`, `deepen`, `rethink`, `elicit`, `think` | **THINK** on latest artifact |
| `idea`, `brainstorm`, `speculate`, `what if`, `hypothesis` | **IDEA** |
| URL / DOI / arxiv / GitHub / HuggingFace / `search …` / `collect` | **COLLECT** (init-on-demand if needed) |
| `report`, `survey`, `write up`, `synthesize`, `manuscript`, `brief` | **SYNTH** (Phase-Guard checked) |

---

## Artifact Naming

| Artifact | Pattern | Location |
|----------|---------|----------|
| Research brief | `brief-{id}.md` | `docs/plans/` |
| Evidence map | `evidence-{id}.md` | `docs/plans/` |
| Judgment | `judgment-{id}.md` | `docs/plans/` |
| Research plan | `plan-{id}.md` | `docs/plans/` |
| Decision (optional) | `decision-DEC-{nnn}.md` | `docs/plans/` |
| Idea note | `YYYY-MM-DD-<slug>.md` | `docs/ideas/` |
| Papers index | `papers-index.json` (+ `.md`) | `docs/index/` |
| Synthesis drafts | chapters + spec under mode dir | `docs/{survey,report,manuscript,brief}/` |
| Deliverable (public) | `<topic>-<mode>-<lang>.<ext>` | `deliverables/` (optional `deliverables/wiki/`) |
| Material IDs | `P-xxx` papers, `W-xxx` web, `G-xxx` github | indexes |
| Full-text Markdown | `materials/<bucket>/<ID>.md` | papers: `materials/papers/`; also `web`, `github` |
| Paper raw binaries | `materials/papers-raw/<ID>.<ext>` | same stem as the Markdown file |

`{id}` default: `R-001` for first research thread (increment if multiple threads).

**Layout rule:** locations above are destinations for real files. Never create those directories empty — write the file (parent dirs appear as a side effect). INIT only creates `AGENTS.md` + `.omr/*.json`. See `INIT/init.md`.

---

## Evidence Boundaries (non-negotiable)

| Level | Label | Meaning |
|-------|-------|---------|
| **proven** | "Paper X validates / proves…" | Strong experimental or formal validation in source |
| **suggests** | "Paper X suggests / demonstrates…" | Indirect or limited evidence |
| **inferred** | "Based on X, we infer…" | Multi-source synthesis; explicit boundary |
| **speculative** | — | Exclude from evidence map as anchor |

Never claim "proves" when authors only suggest or demonstrate.

---

## Tree State

File: `.omr/tree-state.json`

```json
{
  "unlocked": ["init", "collect", "idea", "think"],
  "ready": ["analyze"],
  "locked": ["synth", "decide", "reconcile"],
  "completed": []
}
```

Update after each op using graph rules in `GRAPH.md` (LLM edits `.omr/tree-state.json` — see `LLM-STATE.md`).

---

## Template Variables

Templates use `{{PLACEHOLDER}}` syntax. Each template file declares its own placeholders inline (e.g. `AGENTS.md.template` needs project/language fields, `judgment-template.md` needs evidence/confidence fields) — read the file you are filling instead of relying on a central list.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Wrong auto-detection | Use explicit op (`analyze`, `synth`, `think first-principles`) |
| Gate A fails | Collect more materials or run THINK (triangulation / first principles) |
| Shallow judgment | `think` with Literature Review Personas or Thesis Defense |
| Over-claiming in draft | Lenses + Gate D; fix evidence boundaries |
| Missing citations | Ensure every claim has `[P-xxx]` / `[W-xxx]` linked in index |
| Stuck after collect | Run `analyze` |

---

## Reference Map

- `LLM-STATE.md` — agent-owned state JSON; scripts only for render/backup/language detect/optional collect
- `LANGUAGE.md` — timezone/locale → preferred BCP-47 language tag
- `GRAPH.md` — pattern graphs and next-step routing
- `THINK/` — elicitation behavior + method catalog + per-method playbooks (`THINK/methods/`)
- `ANALYZE/` — deep analysis pipeline
- `SYNTH/` — incremental long-report protocol + export
- `WORKFLOW/` — end-to-end Evidence-Deep
- `patterns/*.json` — machine-readable graphs
