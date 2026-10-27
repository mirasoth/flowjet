# Platonic Coding Workflow Overview

## Objective

Execute the full three-phase Platonic Coding workflow with clear phase visibility and correct handoffs between RFC specification, implementation, and review. BRAINSTORM mode (internal design exploration) is optional at Phases 1 and 2.

## Phase Visibility Rule

**Always show the current Phase** at the start of each step and in any status summary, e.g.:

- `[Phase 1] RFC Specification`
- `[Phase 2] Implementation`
- `[Phase 3] Spec Compliance Review`
- `[FINISHED]`

## Phase Flow

```
Phase 1: RFC Specification
    → Optional: BRAINSTORM mode (conceptual design exploration)
    → Create design draft (.platonic/drafts/)
    → Generate RFC from draft
    → SPECS mode: specs-refine (validate + update supporting files)
Phase 2: Implementation
    → Optional: BRAINSTORM mode (design refinement)
    → IMPL mode: impl-full (spec analysis → guide (incl. coding plan) → code + tests)
Phase 3: Spec Compliance Review
    → REVIEW mode: review code against RFC + impl guides
    → Compliance report
FINISHED
```

## Default Paths

- Design drafts: `.platonic/drafts/`
- RFC specs: `.platonic/specs/`
- Implementation guides: `.platonic/impl/`

These are built-in defaults used automatically. A `.platonic.yml` is **optional** — create one only to override these paths, to define custom spec stages, or to declare namespaces (which partition `.platonic/specs` and `.platonic/impl` per service/module with independent `RFC-<PREFIX>-NNN` sequences; see `references/specs/specs-partition.md`). If absent, the skill auto-detects project metadata (name, language, framework) from host manifests.

## BRAINSTORM Mode Integration Pattern

Brainstorming is an **internal mode** of this skill (formerly the standalone `platonic-brainstorming` skill). It is no longer invoked via the Skill tool as a separate skill. All phases that integrate brainstorming follow this standard pattern:

### Detection and Invocation

1. **Detect**: Intent keywords in the user's request (brainstorm, discuss, investigate, explore, deep analysis, deep dive, think through, trade-offs, what's the best approach) → enter BRAINSTORM mode. Also enterable explicitly with `brainstorm`.
2. **Run**: Follow `references/brainstorm/brainstorm.md`:
   - Collaborative dialogue explores requirements, constraints, approaches, trade-offs
   - Produces an approved design draft in `.platonic/drafts/`
   - Presents the post-draft routing menu (see `references/brainstorm/brainstorm.md`)
3. **Benefits**: Structured exploration, approach comparison, incremental validation before committing to an RFC or implementation

### Phase-Specific Usage

- **Phase 1**: Use before RFC formalization for conceptual design exploration
- **Phase 2**: Use before implementation for design refinement and architecture validation
- **Phase 3**: Not applicable (review phase is purely analytical)

## When to Ask the User

At every gate below, **call the `ask_user` tool** — do not write the question as plain text. Plain-text questions do not pause the loop; `ask_user` pauses the loop and resumes on the same turn once the user answers.

- **Phase 1**: RFC number/index for the new or updated RFC, if not specified. Whether to use BRAINSTORM mode for conceptual design.
- **Phase 2**: RFC number/index for which to implement, if not specified. Whether to use BRAINSTORM mode for design refinement. The IMPL mode operation handles its own confirmation gates for the impl guide (which includes the coding plan).
- **Phase 3**: Which code paths and RFC(s) to review, if not specified.

## Mode Invocations

| Phase | Optional Integration | Mode / Action |
|-------|---------------------|---------------|
| 1 | BRAINSTORM mode | **SPECS mode** — draft → RFC → refine (validate + update supporting files) |
| 2 | BRAINSTORM mode | **IMPL mode** — impl-full: spec analysis → impl guide (incl. coding plan) → code with tests |
| 3 | — | **REVIEW mode** — review code against RFC specs and impl guides |

Read the phase-specific reference file before executing each phase:

- `references/workflow/workflow-phase-1.md` — RFC Specification
- `references/workflow/workflow-phase-2.md` — Implementation
- `references/workflow/workflow-phase-3.md` — Spec Compliance Review