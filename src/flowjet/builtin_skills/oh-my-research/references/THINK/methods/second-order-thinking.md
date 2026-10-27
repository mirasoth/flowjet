# Second-Order Thinking — Playbook

## Purpose

Trace a claim or recommendation beyond its immediate consequence to the cascading, second-order effects — so the report flags downstream implications that a first-order reading misses.

## When to use

- The judgment draws a recommendation or "so what" that stops at the immediate effect
- A conclusion's downstream implications (policy, practice, theory) are unexamined
- Before Gate D, when the report should anticipate objections to its own implications

## What it attacks

Shallow "and therefore…" endings, unexamined side effects, and recommendations that fix the stated problem while quietly creating a worse one.

## Trigger questions

1. If this conclusion is accepted, what happens *next* — and then what?
2. Who is affected by the second-order effect that the first-order story ignores?
3. What could make the obvious implication backfire?
4. Does the evidence support the second-order claim, or is it speculation that should be labeled as such?

## Procedure

1. **State the first-order implication** (the direct "and therefore…").
2. **Chain it forward**: consequence → consequence-of-consequence, 2-3 steps.
3. **Separate** each step into: supported by graded evidence vs inferred/speculative.
4. **Flag** any second-order effect that is load-bearing but has no evidence — label it `inferred` with an explicit boundary, or queue `collect`.
5. **Edit**: add the second-order implications the evidence supports; bound the ones it doesn't.

## Output contract

- **Revelations** (≥1): a second-order effect the artifact missed, or an unsupported downstream claim.
- **Proposed edits**: added implications, boundaries, collect targets.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Worked example

Conclusion: "Retrieval reduces hallucination" → first-order: "so RAG is strictly safer for deployment."

- **Chain**: RAG is safer → teams deploy it everywhere → retrieval quality becomes the new failure point → wrong retrieval misleads with *cited-looking* confidence.
- **Separate**: the "retrieval is the new failure point" step has evidence [P-xxx] `suggests`; the "cited-looking confidence is worse than a bare hallucination" step is `inferred`.
- **Edit**: add the evidenced second-order effect; state the last step as an open question / inferred boundary.
- **Outcome**: `refined` (new implication + boundary).

## Depth scaling

- One claim: chain 2-3 steps in a single pass.
- Whole judgment: trace the main conclusion's implications once.
- Whole report: run on the recommendations section before Gate D.

## Evidence boundaries

- First-order claims may be `proven`/`suggests`; second-order steps usually degrade to `inferred` — mark that boundary explicitly rather than smuggling speculation in as fact.
- Never invent a source for a downstream step; it becomes a boundary or a collect target.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| Stop at the immediate effect | Chain at least one step further |
| State second-order effects as fact | Label each step with its evidence grade |
| Spin a whole cascade of speculation | Bound speculation and mark it inferred |
