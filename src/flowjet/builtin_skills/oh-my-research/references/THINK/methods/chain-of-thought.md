# Chain-of-Thought Scaffolding — Playbook

## Purpose

Force the reasoning between premise and conclusion into explicit intermediate steps, exposing the leap where a thin argument skips a flawed link.

## When to use

- A conclusion jumps from "evidence exists" to "claim proven" with no visible chain
- You suspect a hidden premise hides in the gap between two statements

## Procedure

1. Write the claim as `premise → … → conclusion`.
2. Expand into single steps, no compound leaps; every arrow must be a valid inference.
3. Inspect each arrow: is it supported by graded evidence, or is it an assumption?
4. Where an arrow has no support, mark the gap and either downgrade, add a boundary, or queue collection.

## Output contract

- **Revelations** (≥1): the specific arrow(s) that lack support.
- **Proposed edits**: grade changes, boundaries, gaps.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Anti-pattern

| Do not | Do instead |
|--------|------------|
| Write the chain but skip inspecting the arrows | Treat every arrow as a claim that needs its own support |
