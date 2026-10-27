# Phase 1: RFC Specification

**[Phase 1] RFC Specification**

## Objective

Produce RFC (Status: Draft) and refine via `specs-refine`. Optional: use BRAINSTORM mode for design exploration.

## Process

1. **Optional brainstorming**: Enter BRAINSTORM mode (see `references/brainstorm/brainstorm.md`) for conceptual design exploration. On approval, the post-draft routing menu may route directly into step 3 or 4.
2. **Create draft**: Use existing draft or create interactively (problem, constraints, abstractions, terminology). Save to `.platonic/drafts/YYYY-MM-DD-<topic>-design.md`
3. **Determine RFC index**: If the project declares namespaces in `.platonic.yml`, first determine the target namespace with the user (root-level for cross-cutting RFCs, or one of the declared namespaces for service-specific ones). Suggest the next sequential `NNN` within that scope (exactly three numeric characters, zero-padded; root scope uses `RFC-NNN`, namespace scope uses `RFC-<PREFIX>-NNN` with the namespace's declared prefix). **Call `ask_user`** to confirm the index with the user. Use a non-sequential number only if the user explicitly requests it.
4. **Generate RFC**: Formal RFC following `assets/templates/template-rfc-standard.md`. Write to `.platonic/specs/RFC-NNN-<name>.md` (root) or `.platonic/specs/<ns>/RFC-<PREFIX>-NNN-<name>.md` (namespaced)
5. **Refine**: Run `specs-refine` (updates history, index — rollup + local indexes, namings; validates consistency)

## Output

- RFC in `.platonic/specs/` (Status: Draft)
- Updated supporting files
- Optional: Design draft in `.platonic/drafts/`

## Handoff to Phase 2

**Call `ask_user`** to confirm the RFC path/identifier with the user before proceeding to implementation. Optional: enter BRAINSTORM mode for design refinement.