# Full Implementation (End-to-End)

Default operation for implementing an RFC. Orchestrates: Spec Analysis → Impl Guide (incl. Coding Plan) → Coding + Tests.

```
Spec Analysis → Impl Guide (incl. Coding Plan) → Coding + Tests
                    ▲
              [confirm gate]
```

## Prerequisites

- RFC exists (Draft or Frozen)
- Target module specified
- Language/framework known or detectable

## Inputs

| Input | Required | Notes |
|-------|----------|-------|
| RFC Document | Yes | Path to source RFC |
| Target Module | Yes | Module/crate/package name |
| Language | Yes | Target language |
| Framework | No | If applicable |
| Auto Mode | No | Skip gates (default: false) |

## Sub-Workflow

### Step 1: Spec Analysis
Extract from RFC: core concepts, requirements (MUST/SHALL), constraints, interfaces, data structures, behaviors, dependencies. Create requirements checklist.

### Step 2: Impl Guide Design
Create implementation guide (follow `impl-create-guide.md`). Assign the next sequential IG number in the RFC's namespace scope (`IG-XXX` at the impl root for root-level RFCs; `IG-<PREFIX>-XXX` inside the mirrored `.platonic/impl/<ns>/` directory for namespaced RFCs — sequences are independent per namespace) unless the user explicitly requests a different number. Output: module structure, type definitions, interface signatures, error handling, testing strategy.

Also author the **coding plan** (Section 10 of the guide): break the guide into ordered tasks — one file per task, dependency order, test pairing. Use `assets/implementation/impl-guide-template.md`, which includes the Coding Plan section. The coding plan is part of the guide, not a separate artifact.

**Confirmation Gate**: Present summary (module structure, key types, design decisions, task breakdown) by **calling the `ask_user` tool** with the summary and an approval question. Skip if auto-mode or "no confirmations". Plain-text questions do not pause the loop — use `ask_user` so the goal resumes on the same turn once the user answers.

### Step 3: Coding
Execute the guide's coding plan: follow guide as law, no speculative design, use language idioms, integrate with existing code, write unit + integration tests, verify build.

If guide is incomplete: document gap, suggest update—don't invent behavior.

## Output

- Implementation guide (next sequential in its scope: `IG-XXX-<name>.md` at the impl root, or `IG-<PREFIX>-XXX-<name>.md` in the source RFC's namespace impl directory), including the coding plan
- Source code
- Unit + integration tests
