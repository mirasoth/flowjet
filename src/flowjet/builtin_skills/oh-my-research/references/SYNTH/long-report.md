# Long Deep Report Protocol

How to produce long surveys/reports under LLM context limits. Follow this whenever mode is `survey`, `report`, or `manuscript`. `brief` may use a shorter 3–5 chapter variant of the same loop.

## Why

A deep report is often tens of thousands of words. Holding outline + all evidence + all prior chapters in one context causes truncation, repetition, and dropped citations. **Disk is the source of truth**; the model only holds a slim pack per turn.

## Artifacts (on disk)

| File | Public? | Role |
|------|---------|------|
| `docs/<mode>/_outline.md` | no (working) | Chapter plan, word targets, evidence slices |
| `docs/<mode>/_citation-map.md` | no | Internal ID → bibliographic entry + public cite key |
| `docs/<mode>/_continuity.md` | no | Rolling brief: claims, terms, threads, cite ledger |
| `docs/<mode>/chapters/*.md` | no (draft) | Reader-facing prose, internal until exported |
| `docs/<mode>/_document.json` | no (working) | LLM-authored presentation spec (drives rendering) |
| `.omr/report-state.json` | no | Progress machine for resume |
| `deliverables/*` | **yes** | Final DOCX/PDF/Markdown — the only shareable surface (optional `deliverables/wiki/`) |

Public/private split: only files under `deliverables/` (project root) are handed to a reader. Drafts, working ledgers, and the presentation spec stay in `docs/<mode>/`.

Underscore-prefixed working files are **excluded from export content** by `export_report.py` (chapters only). `_document.json` is read as the presentation spec, not rendered as content.

## State machine (LLM-authored)

Write `.omr/report-state.json` yourself from the outline. **Do not** call a fixed chapter-template script. Chapter IDs, counts, and lengths must fit the topic (3 chapters for a brief; 12+ for a large survey).

```json
{
  "mode": "survey",
  "language": "en",
  "format": "docx",
  "register": "plain",
  "title": "Topic-specific title",
  "status": "outlining|writing|closing|exporting|done",
  "chapters": [
    {
      "id": "03-retrieval-mechanisms",
      "path": "docs/survey/chapters/03-retrieval-mechanisms.md",
      "status": "pending|drafting|done|needs_revision",
      "target_words": 1500,
      "purpose": "…",
      "evidence_focus": ["P-001", "P-004"]
    }
  ],
  "writing_order": ["01-…", "02-…", "00-abstract"],
  "current": null,
  "updated_at": "ISO-8601"
}
```

Rules:
- Derive `chapters` from `_outline.md` (slug IDs from real theme names).
- Put abstract/executive-summary ids in `writing_order` **last** (often `00-…`).
- Each turn: set `current`, write the file, set that chapter to `done`, clear `current`, bump `updated_at`.
- Resume: open report-state; continue first not-done id in `writing_order`.

See `LLM-STATE.md`.

## Phase A — Reader journey and outline (one turn)

Load: research question, intended audience, judgment summary (not full evidence dump), and themes from the evidence map. Follow `narrative-coherence.md`.

Before naming chapters, copy `assets/synth/_outline.md` to `docs/<mode>/_outline.md` and fill in:

1. **Reader starting point and destination** — assume as little private or domain context as possible.
2. **Central question and provisional bottom line** — one sentence each.
3. **Argument spine** — 4–8 ordered reasoning moves from situation to implication.
4. **Canonical dimensions** — define stable labels and whether they are stages, orthogonal axes, mechanisms, candidate solutions, or evaluation criteria. Do not call incompatible kinds by one label such as “routes”.
5. **Concept ladder** — order terms from familiar to specialized and record prerequisites.
6. **Chapter contracts** — for every chapter: reader starts knowing, guiding question, new concepts, chapter answer, evidence role, argument-spine step, exit state, and bridge to the next chapter.
7. **Dependencies and writing order** — conclusions after their premises; abstract/executive summary last.

Then validate the outline as a reader dependency graph:

- Every chapter advances one distinct argument-spine step and changes the reader's knowledge state.
- No conclusion depends on a concept or premise introduced later.
- Background and comparison criteria precede method/product enumeration and scoring.
- Taxonomy labels keep one meaning from overview through conclusion.
- Chapter order follows explanatory need, not discovery order, paper chronology, or source buckets.

Confirm with the user unless quick-pass. Then write matching `.omr/report-state.json`. Create `docs/<mode>/chapters/` only when writing the first chapter file (and other `docs/<mode>/` files only when writing them).

**Starter shapes (customize freely):**

| Scenario | Shape |
|----------|--------|
| Deep survey | situation → concepts/framework → N evidence themes → comparative synthesis → gaps → implications/conclusions → references → abstract last |
| Industry report | decision context → system boundary/framework → findings → alternatives/trade-offs → recommendation → limitations → references → exec summary last |
| Brief | situation/question → essential context → findings → implication/limits → references → exec summary last |
| Single-paper deep dive | context/prerequisites → method → results reading → critique → implications → references → abstract last |

Split any chapter that would exceed ~2,500 words into `…-part-1` / `…-part-2`.

## Phase B — Citation map (one turn)

From indexes + materials metadata, write `_citation-map.md` (start from `assets/synth/_citation-map.md`):

```markdown
| Internal | Public cite | Full reference |
|----------|-------------|----------------|
| P-001 | (Smith, 2025) | Smith, J. (2025). … DOI |
```

Assign stable public cite keys before body writing. Prefer author–date; numbered `[1]` is fine if the outline chooses that style — stay consistent.

Update the map when new sources appear; never invent bibliographic fields.

## Phase C — Chapter loop (many turns)

For each pending chapter:

### C1. Build slim context pack (only these)

1. Report title, language, mode, audience, and register.
2. The **full argument spine** and canonical dimensions from `_outline.md` (compact, always loaded).
3. This chapter's full contract: reader starts knowing, guiding question, new concepts, chapter answer, evidence role, argument step, exit state, bridge, target words, and `evidence_focus`.
4. Full `_continuity.md` (keep it short — see below), especially reader knowledge state, canonical labels, claim-state ledger, and repetition budget.
5. **Evidence slice**: excerpts / notes for `evidence_focus` IDs only (from evidence-map + full-text material notes). Do not reload the entire evidence-map.
6. Last ~200 words of the immediately previous chapter **and the next chapter's contract**. The former anchors the transition; the latter prevents a dead-end closing.

Before drafting, verify that every concept the chapter assumes is either in `reader starts knowing` or will be defined locally. If not, revise the chapter contract or move the prerequisite earlier.

### C2. Write the chapter

- Open with **anchor → gap → move**: restate the relevant established result, name what remains unanswered, then state this chapter's question.
- Proceed from familiar context to specialized mechanism, then evidence, boundary, and implication.
- Use reader-facing prose and conventional citations from the map.
- Express evidence strength naturally.
- End with a short synthesis paragraph that answers the guiding question and creates the next bridge.
- Add **Chapter takeaways** only when they improve navigation. Keep 2–4 bullets, each stating what the chapter changed in the argument; never replay every subsection.

**Reasoning paragraph rule:** when a paragraph contains several model names, numbers, or citations, give it an explicit claim and implication. Prefer `claim/question → explanation/mechanism → evidence/example → boundary → implication` over a source or fact list.

**Self-containment rules (mandatory — see `narrative-coherence.md`):**

1. Define a technical concept before using it to support a conclusion; expanding an acronym alone is not a definition.
2. At first use, explain the subject/system, metric direction, baseline, comparison conditions, and report-specific shorthand needed to interpret the claim.
3. Introduce each table or figure with its purpose and dimensions; follow it with the result the reader should take from it.
4. Restate the needed premise beside a cross-reference. Never use a chapter number, “as above”, “this route”, or a demonstrative as a substitute for the premise.
5. Use canonical dimensions exactly. Keep pipeline stages, optimization goals, mechanisms, candidate solutions, and evaluation criteria distinct.
6. When evidence changes an earlier claim, mark it in the claim-state ledger and revise every affected location before export.

**Expression quality rules (mandatory — see `native-expression.md` and `LANGUAGE.md` § Non-English Writing):**

1. **Register**: write in the register confirmed at Gate P (`plain` | `academic` | `hybrid`) and keep it stable across chapters.
   - `plain`: clear and direct, explain each term where it first appears, prefer short sentences, use analogies to anchor hard concepts ("explain like I'm five" bar — simple wording, never dumbed-down content)
   - `academic`: formal scholarly register, precise claims, appropriate hedging — but **still natural prose**, not stiff translationese
   - `hybrid`: plain narration with academic rigor in method/results discussion
2. **Compose, don't translate** (hard rule): build each sentence in the report language from the start. Never plan the sentence in English and render it.
3. **Metaphor provenance test** (`native-expression.md` § 1): before using any figurative expression, verify the metaphor exists in the report language. If it does not, use a native metaphor or state the idea plainly — never coin a compound by translating an English metaphor (問題の形/问题的形状, attack surface/攻击面, load-bearing/承重).
4. **Native heading style** (`native-expression.md` § 2): do not open a CJK heading with an article-mimicking classifier (一个/一次/一条). Name the topic or assert the claim; use correct measure words.
5. **Sentence rhythm budget** (`native-expression.md` § 3): one proposition per sentence; keep Chinese sentences mostly under ~60 characters and none over ~100; at most one 破折号 per paragraph; no 「的」-chains of four or more in a clause; prefer active or topic-comment structures over stacked passives.
6. **Verbs over nominalizations** (`native-expression.md` § 4): rewrite noun phrases carrying two or more nominalized verbs.
7. **Term first-mention annotation** (non-English reports): when a technical term first appears, write it as `译名（English Original, ABBR）` — e.g. 「检索增强生成（Retrieval-Augmented Generation, RAG）」. If no standard translation exists or the translation would mislead, keep the English term as the name and add a short in-language gloss. Use **one** name for the rest of the report; never re-annotate.
8. Check the continuity brief's **bilingual term table** before writing: reuse locked translations exactly; add new terms (with status) as they enter.
9. **Read-aloud test before saving** (`native-expression.md` § 6): read the chapter's headings and each section's first sentence as if speaking to a colleague in that language; rewrite anything a native speaker would not say.

Save immediately to `chapters/<id>.md`.

### C3. Update continuity (mandatory, same turn or next)

Edit `_continuity.md` to ≤ ~1,200–1,600 words total. Start from `assets/synth/_continuity.md` and maintain:

1. central question and current bottom line;
2. argument-spine progress;
3. reader knowledge state — what is now understood, what has not yet been introduced, and the next question made necessary;
4. canonical dimensions and labels, explicitly typed as stage / axis / mechanism / candidate / criterion;
5. established claims with their support and boundary;
6. bilingual terms and plain-language definitions;
7. chapter bridges;
8. citation ledger;
9. claim-state and revision ledger (`open | resolved | superseded`) with all locations that must remain synchronized;
10. repetition budget for headline claims and their next allowed role.

For the bilingual term table:

- `standard`: widely accepted translation — annotate at first mention, then use the translation alone;
- `nonstandard`: no settled translation — keep English as the name and gloss it in-language if needed;
- `keep-English`: model names, dataset names, and abbreviations conventionally left untranslated.

After each chapter, update the reader knowledge state and chapter bridge, then check the claim-state ledger. If a claim became resolved or superseded, revise all affected existing chapters now; do not leave cleanup until the conclusion.

Prune evidence detail aggressively, but never prune the argument spine, canonical taxonomy, unresolved bridge, or current claim state. Continuity is a **semantic contract**, not merely a chapter summary.

### C4. Mark done

Edit `.omr/report-state.json`: set the chapter `status` to `done`, clear `current`, set `updated_at`. If all done → `status: exporting`.

Chat: one-line progress only. Proceed to next chapter in a **new turn**.

### C5. Oversized chapter

If mid-draft the chapter is still growing:

1. Save part A as `03-theme-a.md`
2. Add `03-theme-a-continued.md` (or split outline into two chapters)
3. Continue with continuity updated — do not keep the unfinished megachapter in context

## Phase D — Closing chapters

Order:

1. **Build a body reverse outline** — one sentence per completed body section stating its argument function, prerequisite, result, and next link.
2. **Comparative synthesis** — use the argument spine, canonical dimensions, body reverse outline, and chapter answers. Compare mechanisms on shared dimensions; do not replay source summaries.
3. **Gaps and limitations** — distinguish open evidence gaps, invalidated assumptions, and scope boundaries. Synchronize the claim-state ledger.
4. **Conclusions** — answer the central question by walking the shortest valid path through the argument spine; state implications and conditions that would change the answer.
5. **References** — compile from the citation ledger + map; include complete entries.
6. **Abstract / executive summary / overview** (**last**) — write an independently understandable account of situation, question, answer, decisive reasoning, implication, and limits. Preserve body order; do not produce a dense list of unexplained findings.

## Phase E — Narrative and expression review

1. **Per-chapter lens**: Structure/Prose/Adversarial on each chapter after drafting, using that file + continuity. This is mandatory for long reports; quick-pass may combine the findings.
2. **Complete the reverse outline**: extend the body reverse outline to synthesis, limitations, conclusions, and abstract; compare the whole document to the planned argument spine and chapter contracts.
3. **Run the global Narrative Audit** from `narrative-coherence.md`: progressive disclosure, global coherence, self-containment, revision integrity, and prose continuity.
4. Fix every blocking finding chapter-by-chapter. Structural repairs may reorder or merge chapters; do not limit repairs to 1–2 chapters.
5. **Consistency & Polish pass** (mandatory, before export) — see below.

A headings-and-takeaways skim is not sufficient for global review. Read every chapter file once during the combined narrative/consistency pass. Keep only the reverse outline and findings table in context between chapters.

### Phase E.5 — Consistency & Polish pass

Run after the narrative audit and before authoring `_document.json` / export. Scan each chapter against the outline, continuity brief, bilingual term table, and Gate P register.

Checklist (each item yields findings; a genuinely clean item must say "checked, clean" with one line of evidence):

| # | Check | What to verify |
|---|-------|----------------|
| 1 | **Reader dependency order** | Each concept and premise appears before first use; detail increases from situation/framework to evidence/synthesis/action |
| 2 | **Argument-spine alignment** | Every section has a distinct function; chapter order and conclusions follow the planned reasoning path; no isolated source catalogue |
| 3 | **Taxonomy integrity** | Stages, axes, mechanisms, candidate solutions, and evaluation criteria remain distinct; every label keeps one meaning report-wide |
| 4 | **Transitions and antecedents** | Openings use anchor → gap → move; closings create the next question; pronouns, demonstratives, and cross-references name an unmistakable referent |
| 5 | **Local self-containment** | Subject, terms, metrics, baselines, figures, tables, report-specific assumptions, and recommendations can be interpreted without working files or distant premises |
| 6 | **Revision integrity** | No resolved issue remains listed as open; abstract, body, takeaways, limitations, and conclusion share the same final claim state |
| 7 | **Repetition discipline** | Repeated claims have distinct roles; takeaways, synthesis, conclusion, and abstract do not merely restate one another |
| 8 | **Terminology and first mention** | One concept = one name; technical terms have a plain-language definition and, for non-English reports, the locked English annotation at actual first use only |
| 9 | **Native expression sweep** (non-English) | Run `scripts/prose_lint.py --mode <mode>`; resolve every `high` finding (calqued metaphor, coined compound, article-style heading, wrong measure word) and review each `medium` finding (的-chain, passive/dash stacking, long sentence, `X侧`); apply the metaphor provenance test and read-aloud test from `native-expression.md` |
| 10 | **Heading and rhythm budgets** | Headings read as native section titles; sentence length, 破折号 density, and passive density within the budgets in `native-expression.md` § 2–3 |
| 11 | **Register adherence** | Style matches Gate P in every chapter; no unexplained shift between plain and academic writing |

Write `docs/<mode>/_narrative-audit.md` from `assets/synth/_narrative-audit.md` with:

1. a reverse outline (`section | argument function | prerequisite | result | next link`);
2. a findings table (`location | issue type | reader impact | repair | status`);
3. blocking-check results and a resolution summary.

Apply high-confidence fixes directly in quick-pass; otherwise ask the user to accept/reject substantive reframing. Update the outline and continuity ledgers whenever structure, taxonomy, or claim state changes. Rerun affected checks until no blocking finding remains. Gate D requires this artifact and fails while any finding remains `open`.

## Phase F — Export

First author the presentation spec (this is an LLM decision, not the script's):

```bash
# starter (once); then edit docs/<mode>/_document.json
python scripts/export_report.py --emit-spec --mode survey
```

In `_document.json` set title/subtitle/author, fonts (including `eastasia`/`pdf_cjk` for Chinese), heading colors + sizes, cover elements, TOC depth, header/footer, and `chapters.order`. Omit fields to accept defaults. Then render:

```bash
python scripts/export_report.py --mode survey --format docx --language en
```

Default output: `deliverables/<topic>-<mode>-<language>.<format>` at the project root (`--output` overrides). The renderer applies `_document.json` and reads `chapters/*.md` only (per spec order, else sorted). Other `_*.md` working files are not included. It never invents styling — tune the spec, not the script.

Then QA2 + Gate D + visual inspect of DOCX/PDF.

## Resume

```
synth --resume
```

1. Read `.omr/report-state.json` and `_outline.md`
2. If `current` is `drafting` with a partial file, finish that chapter
3. Else take the next not-done id from `writing_order`
4. Rebuild slim pack; continue loop

Never restart from outline unless the user asks to re-outline.

## Anti-patterns

| Do not | Do instead |
|--------|------------|
| Generate all chapters in one reply | One chapter per turn |
| Paste full report into chat | Paths + progress only |
| Reload every prior chapter while drafting | Argument spine + continuity + previous tail + next contract |
| Let source/discovery order determine the report | Build a reader dependency graph and concept ladder |
| Call stages, axes, mechanisms, and candidates all “routes” | Define canonical dimensions and type each label |
| Stack model names, metrics, and citations | State the claim, explain the mechanism, then interpret evidence and limits |
| Use “as above” or a chapter number as the premise | Restate the needed proposition beside the cross-reference |
| Write abstract first | Write a self-contained abstract last, in body argument order |
| Repeat every conclusion in every takeaway | Track a repetition budget and give each recurrence a distinct role |
| Expand continuity forever | Cap and prune evidence detail; retain semantic contracts and claim state |
| Patch a resolved claim in one chapter only | Synchronize abstract, body, limitations, takeaways, and conclusion |
| Export mid-loop | Export when state is complete and narrative audit passes |
| Dump entire evidence-map each turn | Evidence slice for this chapter |
| Draft in English, then translate to the report language | Compose directly in the target language |
| Coin a compound by translating an English metaphor | Apply the metaphor provenance test; use a native figure or plain statement |
| Open CJK headings with 一个/一次/一条 | Name the topic or assert the claim |
| Extend a sentence with 破折号 asides | Split at the logical seam |
| Treat "no translationese" as a reminder | Run `prose_lint.py` and clear every `high` finding |
| Review only headings and takeaways | Read each chapter once, build a reverse outline, and run the Narrative Audit |

## Agent turn checklist

```
[ ] report-state + outline loaded (LLM-owned JSON)
[ ] argument spine + canonical dimensions + chapter contract loaded
[ ] assumed concepts are already known or defined locally
[ ] previous bridge and next chapter contract loaded
[ ] only the relevant evidence slice is in context
[ ] chapter opens anchor → gap → move and closes with answer → next question
[ ] metaphors pass the provenance test; headings use native style
[ ] read-aloud test done on headings and section openings
[ ] chapter written to chapters/
[ ] continuity reader-state, bridge, taxonomy, claim-state, and repetition ledgers updated
[ ] chapter marked done in report-state.json
[ ] chat: progress line only
[ ] stop turn (next chapter = next turn) unless user asked for quick-pass multi-chapter
```

Quick-pass may write 2–3 short chapters per turn **only if** each is flushed to disk before the next starts and total output stays well within safe limits. Prefer one chapter per turn for deep survey quality.

## Figures (Mermaid)

- **All figures are Mermaid fenced blocks** — no ASCII art, no external images
  - `flowchart` for structures and pipelines; `sequenceDiagram` for interactions
  - `classDiagram` / `stateDiagram-v2` / `erDiagram` for static models
  - `pie` / `mindmap` / `timeline` for summaries
- **Caption**: one italic line immediately below the fence — `*Figure 3-1: ...*` (manual `chapter-sequence` numbering)
- **Node IDs** must not match `[PWGSE]-\d+` (e.g. `P-001`) — the publication-safety scan treats that pattern as an internal material ID and blocks the export; use `N1`, `N2`, or short semantic names
- **Labels** inside nodes/edges follow the report language; keep each label short enough to survive reader-side auto-layout
- Markdown deliverables render fences natively (GitHub/GitLab/Typora); DOCX/PDF exports show Mermaid source as code blocks — the Markdown version is the graphical reference
