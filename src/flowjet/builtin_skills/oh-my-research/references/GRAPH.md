# Graph-Guided Workflow

## Purpose

Pattern JSON graphs drive **recommended next steps**. Skills/ops remain freely invocable; the graph records successful paths and unlocks.

Runtime:
1. Read `.omr/pattern.json` (default **Evidence-Deep** if missing after init)
2. Derive artifact presence → update `.omr/tree-state.json`
3. Recommend next node along edges
4. **THINK** is a side-cycle on `analyze` (and optionally `synth` drafts) — does not replace edges unless user stays in deepen loop

## Pattern Library (report-first)

| Pattern | File | Default synth mode |
|---------|------|--------------------|
| Evidence-Deep (default) | `patterns/evidence-deep.json` | survey (or report) |
| Evidence-First | `patterns/evidence-first.json` | survey |
| Idea-First | `patterns/idea-first.json` | brief |
| Stance-First | `patterns/stance-first.json` | report |
| Loop | `patterns/loop.json` | survey |
| Rapid | `patterns/rapid.json` | brief |

**Out of this skill's scope:** experiment/prototype coding evaluation, and a mandatory decide middle node on the default path.

## Evidence-Deep (default)

```
collect → [Gate M] → analyze ⟲ think → [Gate T] → [Gate A / QA1] → [Gate P] → synth
```

- Entry: `collect`
- After collect: Gate M (source diversity & enough materials to analyze?) — default mix is papers+web+github+search via parallel bucket agents; shows diversity report; warn if a default bucket is empty without opt-out
- After analyze judgment: offer THINK if confidence low / gaps high
- After THINK: Gate T (collect more from surfaced gaps?)
- Gate A / QA1 unlock `synth`
- Gate P confirms language / format / mode / audience before outline
- Synth: lenses → Gate D / QA2 → optional wiki

## Node ↔ Artifact Contracts

| Node | Requires | Produces |
|------|----------|----------|
| `init` | — | `AGENTS.md`, `.omr/tree-state.json` |
| `collect` | workspace | `materials/**`, `docs/index/*` (inbox merge), `.omr/collect-batch.json`, Gate M result (with diversity report) |
| `idea` | workspace | `docs/ideas/*` |
| `analyze` | materials + index | brief, evidence-map, judgment, optional plan |
| `think` | target artifact | refined target (in place after confirm) |
| `decide` | judgment (optional override) | `decision-DEC-*.md` |
| `synth` | **judgment** (required) | `docs/<mode>/` drafts + `deliverables/*`, optional `deliverables/wiki/` |
| `reconcile` | existing plans/synth | archive + updated artifacts |

## Unlock Rules (tree-state)

```
unlocked always: init, collect, idea, think
ready analyze: when materials/index exist, then Gate M passes (source diversity + enough materials)
unlock synth: after Gate A pass (judgment exists + gate recorded) + Gate P prefs confirmed
ready decide: when judgment exists (optional path)
ready reconcile: when any plans or synth exist
```

## Cross-Stage Jump Protection (v1.4 — blocking by default)

The graph edges are **recommended** paths, but the agent must enforce **prerequisite artifact checks** before allowing a stage to execute. This prevents the common failure mode where a user says "write the report" and the agent jumps from COLLECT to SYNTH, skipping ANALYZE + THINK + Gate A.

**v1.4 change — blocking by default:** The guard is now **blocking**. The agent must not proceed past a missing prerequisite without an explicit user override (override language required — see `LLM-STATE.md` § Tree-state pre-flight check). A general task instruction like "write the report" does **not** count as an override.

**Prerequisite matrix:**

| Target stage | Required artifacts on disk | Required gate JSON | If missing |
|---|---|---|---|
| ANALYZE | `materials/` ≥1 source + `docs/index/` entry | `gate-m.json` (run during ANALYZE) | Route to COLLECT |
| THINK | `docs/plans/judgment-*.md` | (none) | Route to ANALYZE |
| SYNTH | `docs/plans/judgment-*.md` | `gate-a.json` (pass) + `gate-p.json` | Route to ANALYZE → THINK → Gate A → Gate P |
| DECIDE | `docs/plans/judgment-*.md` | (none) | Route to ANALYZE |
| RECONCILE | `docs/{survey,report,manuscript,brief}/` content (or exported `deliverables/*`) | (none) | Nothing to reconcile |

**Enforcement protocol:**

1. Before executing a stage, read `.omr/tree-state.json` and check if the stage is in `unlocked`, `ready`, or `completed`.
2. If the stage is `locked`, check if the required artifacts exist on disk.
3. If artifacts exist but tree-state is stale, update tree-state and proceed.
4. If artifacts are missing, show `[PHASE-GUARD]` notice and offer to run the prerequisite stage.
5. If user explicitly overrides, proceed but record `scenario_note` in the next gate JSON.

**Tree-state staleness check:**

After every op, the agent **must** update `.omr/tree-state.json`:
- Move completed stages to `completed`
- Unlock next stages per the unlock rules
- Update `notes` field with a brief summary

A stale tree-state (not updated after the last op) is a signal that the workflow may have been interrupted or the agent forgot to update state. The agent should check and update it at the start of any new op.

## Cycles

Only **Loop** pattern declares `graph.cycles[]`:

```json
"cycles": [
  {
    "id": "deep-analyze",
    "nodes": ["collect", "analyze"],
    "gate": "gate_l",
    "exit_to": "synth"
  },
  {
    "id": "idea-dev",
    "nodes": ["idea"],
    "gate": "gate_l",
    "exit_to": "collect"
  }
]
```

THINK side-cycle is **not** a graph cycle; it is a methodology-driven elicitation checkpoint attached to analyze/synth. Each pass loads a playbook (`THINK/methods/<slug>.md`), must surface ≥1 revelation (never default-agree), and stamps an outcome (`hardened`/`refined`/`unchanged`/`killed`).

## Pattern Selection

1. `init` sets default `Evidence-Deep` in `.omr/pattern.json`
2. User may `workflow --pattern Idea-First` (etc.)
3. After 3+ ops, optionally propose renaming/saving custom pattern under `.omr/patterns/`

## Next-Step Presentation

Always show:

```
[ANALYZE] Pattern: Evidence-Deep
Completed: collect, analyze(judgment draft)
Ready: think (recommended), gate_a → synth
Locked: —
```

## Updating State

After each successful op, the **agent** updates (see `LLM-STATE.md`):

- `.omr/tree-state.json` — move op to `completed`; unlock dependents per this graph and the active pattern
- `.omr/loop-state.json` — if Loop / Gate L
- `.omr/quality-gates/*.json` — if gate/QA ran (LLM-written)

Do not require Python helpers for tree/loop/quality state.
