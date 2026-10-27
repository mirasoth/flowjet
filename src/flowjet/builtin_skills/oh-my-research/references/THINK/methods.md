# THINK Method Catalog

Research-curated elicitation methods. Agents pick best-fit; users may name a method.

## Core research (always prefer these first)

| Method | Intent | Output pattern | When to use |
|--------|--------|----------------|-------------|
| First Principles Analysis | Strip assumptions; rebuild from fundamental truths | assumptions → truths → new approach | Shaky framing; overfitted jargon; “why is this true?” |
| Socratic Questioning | Reveal hidden assumptions via targeted questions | questions → revelations → understanding | Vague claims; missing “how do you know?” |
| Assumption Audit | List assumptions; rate confidence/impact; stress-test weak ones | list → rate → stress-test → shore up | Before Gate A; before publish |
| Source Triangulation | Require ≥3 independent source types before accepting a claim | claim → sources → confidence | Single-paper anchors; blog-heavy maps |
| Literature Review Personas | Optimist + skeptic + synthesizer | sources → critiques → synthesis | Polarized literature |
| Thesis Defense Simulation | Committee stress-tests conclusions | thesis → challenges → defense → refinements | Judgment / report conclusion |
| Chain-of-Thought Scaffolding | Explicit intermediate steps; no leaps | premise → steps → conclusion | Thin reasoning chains |
| Steelmanning | Strongest opposing reading before rebuttal | opposing view → strongest form → honest rebuttal | Contested claims |
| Inversion Analysis | How would this survey be wrong? | goal → invert → failure paths → avoidance | Blind spots |
| Pre-mortem Analysis | Imagine peer-review failure; work backward | failure scenario → causes → prevention | Before Gate D |
| Occam's Razor Application | Simplest sufficient explanation | options → simplification → selection | Over-complex taxonomies |
| Problem Decomposition | Break / solve / reassemble | whole → parts → solutions → reassembly | Sprawling topics |
| Abstraction Laddering | Move why↔how to right altitude | concrete ↔ abstract → right level | Wrong scope |
| Comparative Analysis Matrix | Options × weighted criteria | options → criteria → scores → recommendation | Competing schools |
| Critique and Refine | Strengths/weaknesses → improve | strengths/weaknesses → improvements → refined | Any draft |
| Explain Reasoning | Transparent step-through | steps → logic → conclusion | Opaque judgments |
| Feynman Technique | Explain simply; find gaps | complex → simple → gaps → mastery | Dense chapters |
| Reframe the Question | Is the stated question the real one? | stated → reframe → true problem | Start of ANALYZE |

**Playbooks** — one file per core method under `methods/` (e.g. `first-principles.md`), with full procedure + worked example for the five deep methods. Index + anatomy in `methods/README.md`. THINK loads the playbook when it runs the method.

## Reshuffle pool (advanced / collaboration / risk)

| Method | Category | Pattern |
|--------|----------|---------|
| Tree of Thoughts | advanced | paths → evaluation → selection |
| Graph of Thoughts | advanced | nodes → connections → patterns |
| Self-Consistency Validation | advanced | approaches → comparison → consensus |
| Second-Order Thinking | core | action → consequences → second-order → choice |
| Debate Club Showdown | collaboration | thesis → antithesis → synthesis |
| Six Thinking Hats | collaboration | white → red → black → yellow → green → blue |
| Red Team vs Blue Team | competitive | defense → attack → hardening |
| Stakeholder Lens Rotation | framing | perspective A → B → C → gaps |
| Map Is Not the Territory | framing | model → reality check → divergences |
| What If Scenarios | creative | scenarios → implications → insights |
| Failure Mode Analysis | risk | components → failures → prevention |
| Challenge from Critical Perspective | risk | assumptions → challenges → strengthening |

Reshuffle methods mostly use their `output_pattern` directly. Two are promoted to playbooks: Red Team vs Blue Team (`methods/red-team-vs-blue-team.md`) and Second-Order Thinking (`methods/second-order-thinking.md`). Promote more by writing `methods/<slug>.md` (anatomy in `methods/README.md`).

## Omitted (code-centric; do not offer for OMR research)

Algorithm Olympics, Rubber Duck Debugging, Code Review Gauntlet, Performance Profiler Panel, Security Audit Personas, Verification-gap code lenses.

## Machine catalog (optional)

`assets/think/methods.csv` is a readable catalog. The agent selects methods; there is no registry runner.
