# First Principles Analysis — Playbook

## Purpose

Strip the artifact back to assumptions, then rebuild conclusions from fundamental truths instead of inherited framing. Used when a judgment or evidence map feels plausible but you can't defend *why* it's true.

## When to use

- Judgment confidence is low/medium and the conclusion leans on field jargon ("scale is enough", "attention is all you need")
- A framing was imported from a single influential paper and never questioned
- "Why is this true?" leads back to "because the literature says so" rather than a mechanism

## What it attacks

Overfitted jargon, inherited assumptions, and conclusions that survive only because nobody re-derived them. It catches the case where every paper agrees for the same unexamined reason.

## Trigger questions

1. What is this claim actually asserting, in one plain sentence?
2. Which parts are *derived* (follow from evidence) vs *assumed* (inherited framing)?
3. If I deleted the field's vocabulary, what would remain true?
4. What is the minimum set of truths this conclusion depends on?

## Procedure

1. **Restate** the target conclusion in plain language, no field terms.
2. **Decompose** it into the assumptions it rests on (list every one, even "obvious").
3. **Separate** each assumption into: fundamental truth (axiom / physics / arithmetic / definition) vs inherited belief (framing, convention, prior art's choice).
4. **Stress** each inherited belief: what evidence actually supports it? What would be true if it were false?
5. **Rebuild** the conclusion from only the surviving fundamental truths + the evidence map's graded claims.
6. **Diff** the rebuilt conclusion against the original. Where they differ, that is the revelation.
7. Propose edits: tighten the conclusion to what the rebuild supports; downgrade any claim that now reads as over-claim.

## Output contract

- **Revelations** (≥1 required): each names an assumption, its classification (truth vs inherited), and what changes when it's challenged.
- **Proposed edits** (diff-style): conclusion wording, grade adjustments (downgrade only), new open questions.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Worked example

Target: judgment "Self-attention is necessary for long-range dependency modeling" (confidence: medium).

- **Restate**: "To model dependencies between distant tokens, the model must use self-attention."
- **Assumptions**: (a) long-range dependencies matter for the task; (b) self-attention is the only mechanism that captures them; (c) alternatives (RNNs, state-space models, convolutions) fail.
- **Classify**: (a) fundamental only if evidence shows it; (b) inherited — from the Transformer framing; (c) empirical, contestable.
- **Stress (b)**: state-space models [G-xxx] report comparable long-range results without self-attention; (c) fails — evidence `suggests` alternatives work, not that attention is uniquely necessary.
- **Rebuild**: "Self-attention is *a* competitive mechanism for long-range modeling, with strong evidence; alternatives are active and comparable in recent work."
- **Diff**: original over-claimed ("necessary"); rebuild is weaker and correct. Grade `suggests`, not `proven`.
- **Outcome**: `refined` (downgrade + new open question: "under what conditions does attention dominate?").

## Depth scaling

- Small artifact (one claim): restate + 3 assumptions + rebuild.
- Whole judgment: run on the main conclusion only; list secondary claims for later passes.
- Whole report: run per-chapter on the thesis, not every sentence.

## Evidence boundaries

- Never upgrade `suggests` → `proven`; this method usually *downgrades*.
- Keep every citation ID intact; rebuilt claims must still trace to `[P-xxx]` / `[W-xxx]`.
- If the rebuild reveals a claim with no source, mark it `inferred` with an explicit boundary or a gap — do not invent a source.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| Re-list the conclusion and call it "true" | Show the assumption chain and what survives |
| Rebuild from vague "fundamental principles" | Use specific truths (definitions, axioms, the evidence map) |
| Upgrade a claim because the reasoning "feels clean" | Re-grade strictly from source language |
| Apply to every sentence | Apply to the load-bearing conclusion(s) |
