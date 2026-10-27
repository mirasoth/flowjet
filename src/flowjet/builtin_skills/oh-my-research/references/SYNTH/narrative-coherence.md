# Narrative Coherence and Self-Containment Protocol

Apply this protocol to every `survey`, `report`, and `manuscript`; use a compressed version for `brief`.

## Quality target

Build a reader dependency graph, not a source inventory. Arrange the report so that each section requires only concepts already introduced, adds one clear piece to the argument, and leaves the reader prepared for the next section.

A report passes only when a reader who has not seen the research workspace can answer:

1. What problem is being solved, for whom, and why does it matter?
2. What terms, system boundaries, and comparison dimensions govern the analysis?
3. How does each chapter advance the central question?
4. Which conclusions follow from evidence, which are synthesis, and under what conditions could they fail?
5. What action or updated understanding follows from the report?

## 1. Design the reader journey before chapter titles

Write these fields in `_outline.md` before creating the chapter list:

- **Reader starting point**: what may safely be assumed; keep this minimal.
- **Reader destination**: what the reader should understand or decide after finishing.
- **Central question**: one question the report answers.
- **Bottom line**: one provisional answer, written plainly.
- **Argument spine**: 4–8 ordered reasoning steps from problem to conclusion.
- **Canonical dimensions**: the stable taxonomy used throughout. Give each dimension one name and define whether dimensions are alternatives, layers, stages, or orthogonal axes.
- **Concept ladder**: order required concepts from familiar to specialized. A concept may appear only after its prerequisites.

Prefer this progression unless the genre requires otherwise:

1. situation and stakes;
2. system boundary and essential concepts;
3. comparison framework or causal model;
4. evidence organized by the framework;
5. synthesis across evidence;
6. uncertainty, alternatives, and failure conditions;
7. implications, recommendation, or decision.

Do not let discovery order, paper chronology, or a list of products determine chapter order.

## 2. Give every chapter a contract

For every chapter, record:

| Field | Requirement |
|---|---|
| Reader starts knowing | Only knowledge established by earlier chapters or defined locally |
| Guiding question | One question, phrased in reader language |
| New concepts | Terms introduced here, with prerequisites |
| Chapter answer | One sentence that answers the guiding question |
| Evidence role | What the evidence establishes; not merely which sources are cited |
| Link to argument spine | Which numbered reasoning step this chapter advances |
| Exit state | What the reader now knows that enables the next chapter |
| Bridge to next | The unresolved question that naturally motivates the next chapter |

Reject or revise an outline when:

- two chapters claim the same argument-spine step;
- a chapter does not change the reader's knowledge state;
- a label changes meaning between overview and body;
- an alleged category later becomes a stage, axis, product list, or subcomponent;
- conclusions depend on concepts introduced only later.

## 3. Write from known to new

### Section opening

Open with a three-move bridge:

1. **Anchor**: state the relevant established result in concrete words.
2. **Gap**: identify what that result does not yet answer.
3. **Move**: state the question or task of this section.

Do not use bare transitions such as “前文已经说明”, “如上所述”, “this”, or “the above route” unless the noun and proposition are restated in the same sentence.

### Paragraph shape

Use a reasoning paragraph, not a fact bundle:

1. claim or question;
2. explanation or mechanism;
3. evidence, example, or calculation;
4. boundary or counterpoint when material;
5. implication for the chapter question.

Not every paragraph needs all five moves, but a paragraph containing several numbers, model names, or citations must explain why those facts matter before moving on.

### Define before use

At first meaningful use:

- define technical terms in plain language;
- expand abbreviations;
- explain metrics and whether higher/lower is better;
- identify named systems or organizations relevant to the conclusion;
- state comparison baselines and conditions next to performance numbers;
- explain report-specific shorthand and keep it stable.

A definition is insufficient if it only expands an acronym. Explain the concept's role in the current argument.

### Local self-containment

Make every section, table, and figure understandable without private artifacts and without requiring the reader to hunt several chapters backward:

- introduce what the item is for before presenting it;
- define row/column dimensions and scoring direction;
- state the comparison baseline and conditions;
- add a sentence after it that interprets the result;
- replace opaque chapter references with a short restatement plus the reference when useful.

Self-contained does not mean repeating whole explanations. Restate only the premise needed at the point of use.

## 4. Preserve one taxonomy and one argument

Maintain these ledgers in `_continuity.md`:

- canonical dimensions and their relationships;
- locked terms and definitions;
- argument-spine progress;
- reader knowledge state;
- chapter bridges;
- unresolved or contradicted claims;
- repetition budget.

Before drafting a chapter, check that its title and key labels use the canonical taxonomy. When evidence forces a taxonomy change, update the outline, continuity brief, affected earlier chapters, conclusion, and abstract in the same revision cycle. Never patch only the latest chapter.

Distinguish consistently among:

- **pipeline stages**: where work happens;
- **optimization goals**: what cost or quality is changed;
- **mechanisms**: how the change is achieved;
- **candidate solutions**: implementable combinations of mechanisms;
- **evaluation dimensions**: how candidates are compared.

Do not call all five “routes”.

## 5. Control repetition

Use repetition only for orientation or decision reinforcement.

- Chapter takeaways summarize what changed, not every subsection.
- The synthesis compares and integrates; it does not replay all chapter summaries.
- The conclusion answers the central question and states implications; it does not reproduce the report.
- The abstract gives the problem, method/scope, main answer, decisive support, and limits; it does not enumerate every result.

Track repeated headline claims in the continuity brief. A claim appearing in the abstract, introduction, chapter takeaway, synthesis, and conclusion must be compressed or assigned a different role at each occurrence.

## 6. Run the narrative audit

After all body chapters exist, read every chapter once and create a reverse outline: one sentence per section stating its function in the argument. Then check:

### Progressive disclosure

- No specialized concept is used before being explained.
- Background precedes comparison and recommendation.
- Evidence precedes the conclusion it supports, except for a clearly labeled executive preview.
- Detail increases gradually; early chapters orient rather than enumerate products and metrics.

### Global coherence

- Chapter order matches the argument spine.
- Every chapter opening follows from the previous exit state.
- Every chapter closing creates or resolves an explicit thread.
- Taxonomy labels retain one meaning.
- No chapter is an isolated source catalogue.

### Self-containment

- Audience, subject/system, scope, terms, metrics, and baselines are explained.
- Tables and figures can be interpreted from their surrounding text.
- Cross-references help navigation but are not substitutes for missing premises.
- Recommendations state assumptions, evidence, trade-offs, and stopping conditions.

### Revision integrity

- No “still unknown” statement conflicts with a later resolved finding.
- Abstract, chapter takeaways, synthesis, limitations, and conclusion reflect the same final claim state.
- Closed questions are removed from open-question lists or explicitly labeled historical.
- Counts, labels, route names, and recommendation thresholds agree everywhere.

### Prose continuity

- Pronouns and demonstratives have unmistakable antecedents.
- Paragraphs explain relationships rather than stack facts.
- Transitions name the logical relation: cause, contrast, qualification, consequence, or change of level.
- Sentence rhythm and register remain natural in the target language.

Record findings as `location | issue type | reader impact | repair`, apply high-confidence fixes, and rerun the audit until no blocking finding remains.

## 7. Blocking failure signatures

Treat these as Gate D failures, not stylistic suggestions:

- taxonomy drift that changes what a route, dimension, or stage means;
- a conclusion whose necessary premise is absent or appears later;
- unresolved references to deleted, renamed, or superseded content;
- a resolved issue still presented elsewhere as open;
- a report-specific system, metric, score, or threshold used without enough explanation to interpret it;
- recommendations that cannot be traced through the body argument;
- sections that are predominantly lists of studies or numbers without synthesis.
