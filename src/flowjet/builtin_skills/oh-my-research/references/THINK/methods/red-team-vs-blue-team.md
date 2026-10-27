# Red Team vs Blue Team — Playbook

## Purpose

Attack the artifact's conclusion as an adversary would, then defend it with graded evidence — hardening it where it survives and weakening it where it doesn't. A structured attack/defend pass for contested or load-bearing claims.

## When to use

- A conclusion is high-stakes or will anchor the whole report
- You want a conclusion to be "attacked to destruction" before Gate A / Gate D
- A claim has survived friendly review but never adversarial review

## What it attacks

Over-confidence, unexamined counter-evidence, and conclusions that hold only because no one tried to break them.

## Trigger questions

1. If I were a hostile reviewer (or a competing school), what is the sharpest attack on this conclusion?
2. Which specific claim, if it fell, would bring the conclusion down with it?
3. What counter-evidence or alternative explanation would the attack cite — and is it in the map?

## Procedure

1. **Blue team first**: state the conclusion and the graded evidence that supports it.
2. **Red team attacks**: enumerate the strongest attacks — methodological flaw, confound, alternative explanation, missing counter-evidence, over-claimed grade, cherry-picked sources.
3. **Blue team defends**: for each attack, answer with graded evidence only. Where the defense holds, record it as hardened; where it cracks, record the crack.
4. **Harden**: for each crack, either downgrade the claim/grade, add a limitation, mark a gap, or queue `collect` for the missing evidence. Do not paper over the crack.
5. **Re-score** the conclusion against what survived.

## Output contract

- **Revelations** (≥1): the attacks the blue team could not fully answer.
- **Proposed edits**: downgrades, limitations, gap entries, collect targets.
- **Outcome stamp**: `hardened` | `refined` | `unchanged` | `killed`.

## Worked example

Conclusion: "Prompting alone solves hallucination in production LLMs" (currently `proven`).

- **Blue team**: P-003 benchmark `suggests` prompting reduces hallucination; P-008 reports a case study.
- **Red team attacks**: (a) benchmarks don't transfer to open-domain production; (b) P-003 measured a narrow metric; (c) "solves" over-claims — P-008 still reports residual errors.
- **Blue team defense**: (a) and (b) crack — no production-domain evidence in the map; (c) confirms the grade is too strong.
- **Harden**: downgrade to `suggests`; add limitation "evidence is benchmark-bound; production behavior untested"; gap "no open-domain hallucination study".
- **Outcome**: `refined` (downgrade + gaps).

## Depth scaling

- One claim: one attack list + defense in a single pass.
- Whole judgment: red-team the single load-bearing conclusion.
- Whole report: red-team the thesis once before Gate D.

## Evidence boundaries

- The red team may *name* counter-evidence; if it isn't in the map it becomes a gap or collect target, never a fabricated citation.
- Defense may only re-grade downward; it never upgrades a grade the source language doesn't support.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| Let blue team win every round | Require each attack to be answered or logged as a crack |
| Attack with invented sources | Name the missing counter-evidence as a gap/collect target |
| Harden by ignoring the crack | Downgrade, add a limitation, or queue collection |
