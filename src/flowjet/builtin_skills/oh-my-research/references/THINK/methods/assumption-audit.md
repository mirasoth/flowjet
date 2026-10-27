# Assumption Audit — Playbook

## Purpose

Explicitly list every assumption under a plan or judgment, rate each by confidence × impact, then stress-test the weakest high-impact ones. Prevents building a report on foundations nobody checked.

## When to use

- Before Gate A (judgment) or Gate D (publish)
- When a conclusion depends on a chain of "obvious" premises
- After First Principles, when you want the full inventory, not just the framing assumptions

## What it attacks

Unstated assumptions, silent dependencies, and the "we all know X" premise that turns out to be false or contested.

## Trigger questions

1. What am I taking for granted for this to be true?
2. Which assumption, if false, sinks the conclusion (high impact)?
3. Which am I least sure about (low confidence)?
4. Which assumption has no evidence in the map at all?

## Procedure

1. **List** every assumption, no matter how obvious (scope, method, data, framing, mechanism).
2. **Rate** each on two axes: confidence (high/medium/low) and impact (high/medium/low).
3. **Flag** the low-confidence × high-impact ones — these are the load-bearing risks.
4. **Stress-test** each flagged assumption: what evidence (graded) supports it? What would contradict it? Is the contradiction anywhere in the map?
5. **Shore up or boundary**: add evidence (if present), queue `collect` (if missing), or write the assumption into the judgment as an explicit boundary/limitation.
6. **Record** the audit so the report's limitations section is honest about what's assumed.

## Output contract

- **Revelations** (≥1): the assumption inventory, with the flagged high-risk ones called out.
- **Proposed edits**: boundary/limitation text, collect targets, grade adjustments where an assumption was silently carrying a claim.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Worked example

Judgment: "Scale is the primary driver of emergent ability" (confidence: medium).

- **Assumptions**: (a) emergent abilities exist as a real discontinuity; (b) observed jumps are due to scale, not metrics/measurement artifacts; (c) the trend continues at larger scale.
- **Rate**: (a) confidence medium, impact high → flagged; (b) confidence low, impact high → flagged; (c) confidence low, impact medium.
- **Stress (b)**: metric-resolution papers [P-xxx] `suggest` some "emergence" is a measurement artifact → the assumption is contested.
- **Shore up**: judgment must state "emergence may partly reflect metric choice; causal attribution to scale is not settled" and downgrade to `suggests`.
- **Outcome**: `refined` (boundary + downgrade).

## Depth scaling

- One claim: list 5-10 assumptions.
- Whole judgment: audit the main conclusion's assumptions; batch secondary claims.
- Whole report: audit the thesis; reference the top risks in limitations.

## Evidence boundaries

- The audit only downgrades or adds boundaries/collect targets; it never adds evidence.
- Every assumption that becomes a claim must either resolve to an ID or be labeled a boundary/gap.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| List 50 trivial assumptions | Focus on confidence × impact, then stress the flagged set |
| Assume "high confidence" without checking the map | Tie each rating to actual graded evidence |
| Audit and change nothing | Write the top risks into limitations/boundaries |
