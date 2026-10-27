# Pre-mortem Analysis — Playbook

## Purpose

Assume the report has already failed peer review (or the judgment is already wrong) and work backward to the causes. Surfaces failure modes that optimistic review never reaches.

## When to use

- Before Gate D / QA2 on a synth draft
- Before Gate A when the judgment feels "obviously right"
- When a conclusion is high-confidence but you haven't imagined how it could be wrong

## What it attacks

Optimism bias, blind spots, and the "we looked and found nothing wrong" illusion that hides the gap nobody asked about.

## Trigger questions

1. Imagine the reviewer/reader rejects this in 6 months. What is the headline criticism?
2. What would have to be true for the main conclusion to be wrong?
3. Which gap, if filled, would overturn the judgment?
4. What did we *not* collect because it wasn't obvious we needed it?

## Procedure

1. **Set the scene**: "It is 6 months from now; this report was rejected / the conclusion was overturned. Why?"
2. **Brainstorm causes** (no filtering): wrong assumption, missing counter-evidence, over-claimed grade, obsolete source, misread method, sampling bias, an alternative explanation nobody considered.
3. **Rank** causes by likelihood × damage.
4. **Map each cause** back to the artifact: which claim/grade/gap would it invalidate?
5. **Convert** top causes into preventive edits: add the missing counter-evidence, downgrade the grade, add a limitation, mark a gap.
6. **Record** causes that need new collection as `collect` targets.

## Output contract

- **Revelations** (≥1): ranked failure scenarios, each tied to a specific claim/gap.
- **Proposed edits**: downgrades, limitation text, gap entries, collect targets.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Worked example

Scene: "The survey on X was rejected because it ignored the replication literature."

- **Causes**: (a) all sources are positive results (publication bias); (b) the "consensus" rests on one unreplicated study; (c) grade `proven` on a claim with no independent replication.
- **Rank**: (b) highest damage (overturns the thesis).
- **Map**: (b) invalidates the main conclusion's anchor claim.
- **Edits**: downgrade anchor to `suggests`; add limitation "primary evidence has not been independently replicated"; add gap "replication status unknown"; collect target: search for replication studies.
- **Outcome**: `refined`.

## Depth scaling

- Single claim: one scene + 3 causes.
- Whole judgment: run on the main conclusion.
- Whole report: run once before Gate D; 5-10 causes is enough.

## Evidence boundaries

- A pre-mortem never adds evidence — it only downgrades, adds gaps, or queues collection.
- Any "cause" that names a source must resolve to a real ID or become a gap, not an invented citation.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| List vague fears ("reviewers are harsh") | Name the specific claim that fails and why |
| Add sources to "fix" the fear | Queue collection for real evidence |
| Treat pre-mortem as permission to strip all confidence | Downgrade only what the scenario actually threatens |
