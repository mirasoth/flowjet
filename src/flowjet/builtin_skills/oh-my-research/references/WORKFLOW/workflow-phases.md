# Workflow Phases — Checklist

## [INIT]

- [ ] Topic confirmed
- [ ] `AGENTS.md` written
- [ ] `.omr/tree-state.json` + `pattern.json` (Evidence-Deep default)
- [ ] `.omr/locale.json` (preferred BCP-47 language from timezone/locale; see `LANGUAGE.md`)
- [ ] No empty content dirs scaffolded (`materials/`, `docs/`, `deliverables/`, …)
- [ ] User shown `collect` next step

## [COLLECT]

- [ ] Inputs routed to handlers
- [ ] Only destination buckets with real files exist under `materials/`
- [ ] Indexes updated with stable IDs (`docs/index/` created on first write)
- [ ] Failures logged
- [ ] `analyze` marked ready when ≥1 usable source (Gate M confirms source diversity & sufficiency before the deep scan)

## [ANALYZE]

- [ ] **Gate M** passed (source diversity & enough materials for the intended scope — diversity report shown to user)
- [ ] Question confirmed
- [ ] Findings graded (`proven` / `suggests` / `inferred`)
- [ ] `brief-*`, `evidence-*`, `judgment-*` written
- [ ] THINK offered/run when Evidence-Deep or low confidence
- [ ] **Gate T** run after THINK (collect more from surfaced gaps?)
- [ ] Gate L if Loop
- [ ] QA1 + Gate A passed
- [ ] Optional `plan-*` for further collection / chapter outline

## [THINK] (side-cycle)

- [ ] Target artifact identified
- [ ] Method selected (named or menu of 5)
- [ ] Playbook loaded (`THINK/methods/<slug>.md`) and procedure applied
- [ ] Revelations (≥1) + proposals + outcome stamp shown (never default-agree)
- [ ] User y/n before mutation
- [ ] Pass recorded in judgment's THINK ledger
- [ ] **Gate T** — load-bearing gaps surfaced? ask user to `collect` or proceed
- [ ] Return to ANALYZE or SYNTH

## [DECIDE] (optional)

- [ ] ≥3 alternatives
- [ ] Gate B passed
- [ ] Decision file written

## [SYNTH]

- [ ] **Gate P** passed — language / format / mode / audience / citations confirmed
- [ ] Outline + citation map + topic-specific `.omr/report-state.json` (LLM-authored)
- [ ] Chapters written one-at-a-time under `docs/<mode>/chapters/`
- [ ] Continuity brief updated and pruned after each chapter
- [ ] Abstract / executive summary written last
- [ ] All chapters `done` in report-state (or `synth --resume` until done)
- [ ] Citations resolve to complete bibliography entries
- [ ] Gaps/limitations section present
- [ ] Lenses run; accepted edits applied
- [ ] Presentation spec authored: `docs/<mode>/_document.json` (title, fonts, cover, TOC, header/footer, chapter order per report/language)
- [ ] LLM QA2 recorded; deliverable (DOCX/PDF/Markdown) exported into `deliverables/` (spec applied) and inspected
- [ ] Gate D passed
- [ ] Wiki generated under `deliverables/wiki/` or skipped
- [ ] Chat: progress / summary only (no full chapters)

## [RECONCILE] (as needed)

- [ ] Blast radius identified
- [ ] Archive + updates applied
- [ ] Gates re-checked if judgment/synth changed

## [FINISHED]

- [ ] Version tag recommended
- [ ] Next research questions listed from gaps
