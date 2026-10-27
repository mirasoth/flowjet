# Phase 2: Implementation

**[Phase 2] Implementation**

## Objective

Produce implementation guide from RFC spec, then implement code with tests. Optional: BRAINSTORM mode for design refinement.

## Process

1. **Optional brainstorming**: Enter BRAINSTORM mode (see `references/brainstorm/brainstorm.md`) for architecture validation before coding. On approval, the post-draft routing menu may route into `impl-update-guide` (existing IG) or `impl-create-guide` (new IG).
2. **Identify RFC**: **Call `ask_user`** to confirm the RFC number/index with the user if not specified; determine target module/language/framework.
3. **Run impl-full**: Read `references/impl/impl-full.md`
   - Spec Analysis: Extract requirements, constraints, invariants
   - Impl Guide Design: Create guide incl. coding plan (**confirmation gate** — call `ask_user`)
   - Coding: Implement + unit/integration tests
4. **Verify**: Guide exists, code written, tests passing

## Inputs

- RFC spec (from Phase 1)
- RFC number/index (ask if not specified)
- Target module/language/framework

## Output

- Implementation guide (next sequential in the RFC's scope: `IG-XXX-<name>.md` at the impl root, or `IG-<PREFIX>-XXX-<name>.md` inside the source RFC's namespace impl directory; `XXX` = exactly 3 digits)
- Source code
- Unit + integration tests

## Handoff to Phase 3

**Call `ask_user`** to confirm code paths and RFCs/guides to review with the user. Proceed to Phase 3 (REVIEW mode).