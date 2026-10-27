# Abstraction Laddering — Playbook

## Purpose

Move up ("why?") or down ("how?") the abstraction ladder to check the artifact is reasoning at the right altitude — neither too abstract to be testable nor too concrete to generalize.

## When to use

- The research question is at the wrong scope (too tactical or too philosophical)
- A conclusion over-generalizes from a concrete case or stays uselessly abstract

## Procedure

1. Locate the current question/conclusion on the ladder.
2. Step **up** ("why does this matter?") and **down** ("how would we test/observe this?") alternately.
3. Identify where the artifact's reasoning breaks: too abstract to tie to evidence, or too concrete to support the claim's scope.
4. Re-frame at the altitude where evidence and claim match; note what was gained/lost.

## Output contract

- **Revelations** (≥1): the mismatch between the claim's altitude and its evidence.
- **Proposed edits**: re-framed question/conclusion, scope qualifier.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Anti-pattern

| Do not | Do instead |
|--------|------------|
| Abstract away from the evidence | Find the altitude where the evidence actually lives |
