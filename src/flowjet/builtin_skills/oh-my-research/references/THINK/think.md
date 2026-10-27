# THINK Mode — Research Elicitation

Shared refinement checkpoint for research depth. Applies **named thinking paradigms** to research artifacts (evidence-map, judgment, report chapters) — **never to code**.

## Trigger

```
think
think first-principles
think socratic
think source-triangulation
deepen judgment
rethink the evidence map
```

Intent keywords: `first principles`, `socratic`, `pre-mortem`, `red team`, `steelman`, `deepen`, `rethink`, `elicit`, `think`.

## Behavior

1. **Target** = most recent research artifact in the session, or path the user names.
2. If user named a method → use it. Else **choose** 5 best-fit methods for this artifact from `methods.md` / `assets/think/methods.csv` (LLM selection — no registry script). Prefer research-core methods; reshuffle excludes already offered.
3. **Load the method's playbook** from `methods/<slug>.md` (index + anatomy in `methods/README.md`). Apply its **Trigger questions** and **Procedure**; scale depth per the playbook's Depth scaling (or target size for lean playbooks).
4. Produce the playbook's **Output contract**: revelations (≥1 required), proposed edits (diff-style), and an **outcome stamp** (`hardened` | `refined` | `unchanged` | `killed`).
5. Show revelations + proposed edits + outcome stamp. Ask **y / n / other** — **never mutate without yes**. On no, drop proposal and record `unchanged` with a note. Other text = revise instruction.
6. Compound passes on the enhanced version until user says **proceed**.
7. Record each pass in the artifact's THINK ledger (judgment: "THINK Passes Applied" table with outcome). Return to ANALYZE or SYNTH (caller resumes).

## Recommended defaults by artifact

| Artifact | First offer |
|----------|-------------|
| Research question / brief | Reframe the Question, First Principles, Abstraction Laddering |
| Evidence map | Source Triangulation, Assumption Audit, Literature Review Personas |
| Judgment | First Principles, Thesis Defense, Steelmanning, Pre-mortem |
| Synth chapter | Critique and Refine, Adversarial (via SYNTH lenses), Inversion, Feynman |

## Auto-offer checkpoints

- After ANALYZE judgment draft if confidence low or gaps high → offer First Principles **or** Source Triangulation
- After SYNTH chapter draft before document lenses → offer Critique and Refine (optional; lenses still run)

## Pattern-driven enforcement (v1.3+)

**In Evidence-Deep pattern, THINK is mandatory after ANALYZE judgment — not optional.** The agent must present a method selection menu before Gate A can be evaluated. This is the most common failure mode: ANALYZE produces a judgment and immediately proceeds to SYNTH without any depth elicitation.

**Enforcement rules:**

| Pattern | THINK requirement | Gate A behavior if THINK skipped |
|---|---|---|
| Evidence-Deep | **Mandatory** — at least 1 pass before Gate A | Gate A fails with `checks: [{id: "think_pass", status: "fail", details: "No THINK pass recorded in judgment"}]` |
| Evidence-First | Recommended — offer if confidence < high | Gate A warns but can pass |
| Loop | Mandatory per iteration | Gate L checks THINK ledger |
| Rapid | Optional | Gate A passes without THINK |
| Idea-First | Optional | Gate A passes without THINK |
| Stance-First | Mandatory before DECIDE | Gate B checks THINK ledger |

**Method selection menu format (must be shown to user):**

```
[THINK] Method selection (Evidence-Deep — mandatory)

Select a thinking method to deepen the judgment:

  1. First Principles Analysis  — strip assumptions, rebuild from fundamental truths
  2. Source Triangulation       — require ≥3 independent source types before accepting
  3. Steelmanning               — strongest opposing reading before rebuttal
  4. Pre-mortem Analysis        — imagine peer-review failure, work backward
  5. Thesis Defense Simulation  — committee stress-tests conclusions

Enter 1-5, or type a method name. (quick-pass: agent selects best-fit)
```

The agent must **show this menu** — not silently skip to Gate A. If the user types "skip" or "proceed", record `scenario_note: "THINK skipped by user override"` in the gate JSON, but the menu must have been presented.

## Hard rules

- **Never default-agree**: a pass must surface ≥1 concrete challenge/revelation. An empty revelation list is a *failed* pass, not a clean one — re-run with a different method or state plainly why none applies.
- Preserve evidence grades; THINK may **downgrade** over-claims, never silently upgrade `suggests` → `proven`
- Keep citation IDs intact; if a claim cannot be cited, mark as gap or inferred with boundary
- Do not invent sources
- Every pass ends with an **outcome stamp** (`hardened` / `refined` / `unchanged` / `killed`) and is recorded in the artifact's THINK ledger

## Outcome stamps

| Stamp | Meaning |
|-------|---------|
| `hardened` | Artifact survived challenge; confidence increased |
| `refined` | Edits accepted; artifact changed |
| `unchanged` | No edits accepted — note why (method found nothing, or user rejected) |
| `killed` | A claim/conclusion was downgraded or removed (over-claim found) |

## Catalog

Method list and patterns: `methods.md` + `assets/think/methods.csv`. Per-method playbooks: `methods/*.md` (index in `methods/README.md`).
