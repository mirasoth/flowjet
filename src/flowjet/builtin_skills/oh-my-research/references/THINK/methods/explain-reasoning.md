# Explain Reasoning — Playbook

## Purpose

Walk through step-by-step how a judgment reached its conclusion, so the chain is transparent and any opaque jump is exposed.

## When to use

- A conclusion reads as "trust me" with no visible logic
- Gate A / QA1 wants traceability from evidence to claim

## Procedure

1. Reconstruct the steps from evidence → interpretation → claim.
2. State each step's justification (which graded claim, which inference).
3. Flag any step whose justification is missing or circular.
4. Fix by downgrading, adding a boundary, or writing the inference explicitly.

## Output contract

- **Revelations** (≥1): steps that were opaque or unsupported.
- **Proposed edits**: explicit reasoning added, or grade/boundary changes.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Anti-pattern

| Do not | Do instead |
|--------|------------|
| Re-describe the conclusion | Show the actual inference steps and their support |
