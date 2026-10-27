# Steelmanning — Playbook

## Purpose

Construct the strongest possible version of the position that opposes the artifact's conclusion, then rebut that version honestly. Catches the strawman — where a conclusion "wins" only because the counter-argument was never stated at full strength.

## When to use

- A judgment dismisses an opposing school without engaging it
- The literature is polarized and the artifact has quietly taken one side
- Before Gate A / Gate D when a conclusion is contested

## What it attacks

Strawmanning, one-sided synthesis, and conclusions that collapse once the best opposing evidence is on the table.

## Trigger questions

1. What is the strongest argument a fair critic would make against this conclusion?
2. Am I rebutting the best version of the opposition, or a weak caricature of it?
3. What evidence does the opposition's best case actually cite — and is any of it in our map?

## Procedure

1. **State the opposing position** at its strongest: the version its own proponents would endorse, with their best evidence.
2. **Check the evidence map**: is that opposition evidence present? If absent, note it as a gap (and possible collect target) — do not invent it.
3. **Rebutt honestly**: where the steelman is right, concede; where it's wrong, show why with graded evidence.
4. **Re-score the conclusion**: does it survive the steelman unchanged, or must it be weakened/qualified?
5. **Edit**: add the concession, qualify the conclusion, or downgrade the grade; add the opposition as a limitation if it can't be refuted.

## Output contract

- **Revelations** (≥1): the steelman position + which parts the conclusion absorbs vs survives.
- **Proposed edits**: qualifications, concessions, grade changes, gap entries.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Worked example

Conclusion: "Fine-tuning is sufficient for domain adaptation; RAG is unnecessary complexity" (currently strong).

- **Steelman**: "RAG avoids catastrophic forgetting and is cheaper to update than re-fine-tuning; several production systems [W-xxx] chose RAG precisely for this."
- **Evidence map**: W-xxx present; a forgetting benchmark P-010 absent → gap.
- **Rebutt honestly**: fine-tuning *does* suffer forgetting; the claim "RAG unnecessary" is too strong.
- **Re-score**: conclusion weakened → "Fine-tuning is sufficient for some adaptation tasks; RAG is preferable when update frequency or forgetting risk is high."
- **Outcome**: `refined` (qualification + gap).

## Depth scaling

- One contested claim: state + rebut in one pass.
- Whole judgment: steelman the single most contested conclusion.
- Whole report: steelman the thesis's biggest rival school once.

## Evidence boundaries

- The steelman's evidence must be real (in-map) or explicitly a gap; never fabricate the opposition's sources.
- Concessions may lower grades, never raise them.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| Rebut a caricature | Rebut the strongest version |
| "Steelman" by inventing citations | Mark absent opposition evidence as a gap |
| Concede everything and kill the conclusion reflexively | Concede only what the steelman actually proves |
