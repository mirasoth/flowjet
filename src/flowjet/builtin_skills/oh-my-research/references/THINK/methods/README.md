# THINK Method Playbooks

Per-method playbooks that drive the `analyze ⟲ think` loop. Load **only the method being run** (slim-context — see `SYNTH/long-report.md`).

## Index

| Method | File | Depth |
|--------|------|-------|
| First Principles Analysis | `first-principles.md` | deep |
| Source Triangulation | `source-triangulation.md` | deep |
| Pre-mortem Analysis | `pre-mortem.md` | deep |
| Steelmanning | `steelmanning.md` | deep |
| Assumption Audit | `assumption-audit.md` | deep |
| Socratic Questioning | `socratic-questioning.md` | lean |
| Literature Review Personas | `literature-review-personas.md` | lean |
| Thesis Defense Simulation | `thesis-defense.md` | lean |
| Chain-of-Thought Scaffolding | `chain-of-thought.md` | lean |
| Inversion Analysis | `inversion.md` | lean |
| Occam's Razor Application | `occams-razor.md` | lean |
| Problem Decomposition | `problem-decomposition.md` | lean |
| Abstraction Laddering | `abstraction-laddering.md` | lean |
| Comparative Analysis Matrix | `comparative-analysis-matrix.md` | lean |
| Critique and Refine | `critique-and-refine.md` | lean |
| Explain Reasoning | `explain-reasoning.md` | lean |
| Feynman Technique | `feynman-technique.md` | lean |
| Reframe the Question | `reframe-the-question.md` | lean |
| Red Team vs Blue Team | `red-team-vs-blue-team.md` | deep |
| Second-Order Thinking | `second-order-thinking.md` | deep |

**Reshuffle pool** (advanced / collaboration / risk): the remaining 10 methods use the one-line `output_pattern` in `methods.md` — no playbook yet. Promote one by writing `methods/<slug>.md` (anatomy below).

## Anatomy

**Deep** playbook sections: Purpose · When to use · What it attacks · Trigger questions · Procedure · Output contract · Worked example · Depth scaling · Evidence boundaries · Anti-patterns.

**Lean** playbook sections: Purpose · When to use · Procedure · Output contract · Anti-pattern.

Every playbook's **Output contract** returns three things, which `think.md` collects and records:

1. **Revelations** — what the method exposed (≥1 required; an empty list fails the pass).
2. **Proposed edits** — diff-style changes to the target artifact.
3. **Outcome stamp** — one of:

| Stamp | Meaning |
|-------|---------|
| `hardened` | Artifact survived challenge; confidence increased |
| `refined` | Edits accepted; artifact changed |
| `unchanged` | No edits accepted — note why (method found nothing, or user rejected) |
| `killed` | A claim/conclusion was downgraded or removed (over-claim found) |

## Cross-cutting rules (all methods)

- **Never default-agree.** A pass must produce a concrete challenge or revelation; rubber-stamping is a failed pass.
- **Evidence boundaries.** Never upgrade `suggests` → `proven`; methods mostly downgrade. Preserve citation IDs; missing support becomes a gap or boundary, never an invented source.
- **Never mutate without yes.** Show revelations + proposed edits, then ask `y / n / other` (see `think.md`).
