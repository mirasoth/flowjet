# DECIDE Mode (optional)

Frame a **research stance or claim set** with ≥3 alternatives, rationale, risks, and evidence refs. **Not** architecture-for-coding and **not** required on the Evidence-Deep path.

Gate B applies only when this mode runs.

## Trigger

```
decide
```

Also: Stance-First pattern; “choose approach”, “take a position” after judgment.

**Typical requires:** `evidence-*.md` (recommended). Stance-First may start with empty evidence (document that uncertainty).

## Steps

1. Read evidence-map (+ judgment if present).
2. Generate ≥3 alternatives (baseline / evidence-suggested / novel or hybrid).
3. For each: description, evidence basis, pros, cons, risks.
4. Select one with explicit rationale.
5. Write `docs/plans/decision-DEC-{nnn}.md`.
6. Present Gate B checklist; on pass mark complete.
7. Recommend next: `collect` / `analyze` / `synth` per active pattern.

## Template

`assets/plans/decision-template.md`

## Out of scope

- Experiment specs, prototypes, metrics design (removed with evaluation skill)
