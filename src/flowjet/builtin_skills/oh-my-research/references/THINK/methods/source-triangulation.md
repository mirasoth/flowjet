# Source Triangulation — Playbook

## Purpose

Refuse to rest a claim on a single source type. Require at least three independent source types (quantitative, qualitative, expert/independent) before a claim earns its grade. Guards against single-source bias and echo-chamber anchors.

## When to use

- A judgment's load-bearing claim traces to one paper or one blog
- The evidence map is dominated by one source type (all benchmarks, no user studies; all reviews, no primary data)
- You suspect a claim is "true" only because one influential paper is cited by everyone

## What it attacks

Single-source bias, self-reinforcing citation clusters, and claims that are one retraction away from collapse.

## Trigger questions

1. Which claim(s) is the whole judgment resting on?
2. How many *independent* sources back each — counting source types, not papers?
3. Are those sources all downstream of the same original result?
4. What happens to the conclusion if the anchor source is wrong?

## Procedure

1. **Select** the load-bearing claim(s) from the judgment / evidence map.
2. **Inventory** every source currently backing it; tag each by type: quantitative (benchmark, measurement), qualitative (case study, ethnography, review synthesis), expert (survey, position, practitioner report), primary (the original result) vs secondary (citing it).
3. **Check independence**: two papers that both cite the same original are not independent.
4. **Gap-check** against the ≥3 rule. One type = `inferred` at best; two types = `suggests`; three independent types can hold `proven` only if at least one is primary/quantitative.
5. **Hunt** for the missing type (this may trigger a `collect`): the missing quantitative benchmark, the missing practitioner/qualitative voice.
6. **Re-grade** the claim to what triangulation actually supports; record the missing type as an open gap, not a silent downgrade.

## Output contract

- **Revelations** (≥1): per load-bearing claim, the source-type tally and independence verdict.
- **Proposed edits**: grade changes, new `collect` targets for the missing type, gap entries.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Worked example

Claim: "Retrieval-augmented generation reduces hallucination" (currently `proven`).

- **Inventory**: P-002 (quantitative benchmark), P-007 (quantitative benchmark), W-004 (a blog citing P-002).
- **Independence**: P-007 is independent; W-004 is downstream of P-002 — does not count.
- **Tally**: one independent type (quantitative). No qualitative/user study, no expert corroboration.
- **Re-grade**: `suggests`, not `proven`. Gap: "no independent qualitative evidence of hallucination reduction in production use."
- **Proposed collect**: search for practitioner reports / case studies.
- **Outcome**: `refined` (downgrade + collect target).

## Depth scaling

- One claim: tally + re-grade in a single pass.
- Whole evidence map: run on the top 3-5 load-bearing claims only.
- Whole report: triangulate the thesis per chapter.

## Evidence boundaries

- Triangulation re-grades strictly by source count and independence; it never upgrades on volume alone (10 papers citing one result ≠ triangulation).
- Preserve citation IDs; record missing types as gaps with severity.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| Count citations, not source types | Count independent types |
| Treat citing papers as independent | Trace to the original result |
| Upgrade because "many papers agree" | Check whether they agree for independent reasons |
| Downgrade silently | Record the missing type as an explicit gap |
