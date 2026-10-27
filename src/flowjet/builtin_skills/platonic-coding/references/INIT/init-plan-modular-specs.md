# Plan Modular Specs

From scan results, propose a modular RFC dependency graph with a bounded number of specs. In multi-service projects, each subsystem additionally becomes a **namespace** (its own directory + ID prefix), so generated specs land in the right place from the start.

## Objective

Design a small, focused graph of Draft RFCs that captures the existing system's design. The user MUST confirm this plan before any specs are generated.

## Inputs

| Input | Source |
|-------|--------|
| Scan synthesis | From scan-project.md Phase 5 |
| Max RFC count | Default: 5. User may override |
| RFC numbering start | Default: `001` (exactly three numeric characters). Continue in strict sequence unless the user explicitly overrides |

## Namespace Decision

Decide whether the project runs in **namespaced mode** before assigning IDs:

- **Recommend namespaces when**: ≥ 3 independent services/modules detected in the scan (distinct top-level packages with separate deployment units, multiple language manifests), or the project already expects ≥ 10 RFCs
- **Namespaced mode**: each subsystem (below) maps to one namespace (directory `.platonic/specs/<ns>/`, qualified IDs `RFC-<PREFIX>-NNN` with an independent sequence per namespace). The conceptual design RFC stays at the specs root as a cross-cutting `RFC-NNN`
- **Single-namespace mode** (default): all RFCs are root-level `RFC-NNN` — identical to pre-3.0 behavior

For each proposed namespace, present 2–4 **prefix candidates** (1–4 uppercase letters) and confirm with the user via `ask_user` — never auto-assign prefixes. Candidate heuristics: service name ≤ 4 letters → direct uppercase (`auth` → AUTH); multi-word → initials (`miracloud gateway` → MGW); long word → vowel-stripped compression (`agentspace` → AGSP). Rules: `^[A-Z]{1,4}$`, unique, `RFC`/`IG` reserved.

If namespaces are adopted, record them in `.platonic.yml` (this is a legitimate reason to create the file) as part of plan confirmation.

## Modular Planning Principles

### Principle 1: One System-Wide Conceptual Design

Always produce **exactly 1** Conceptual Design spec:

- RFC-001 (or user-specified start number)
- Covers the entire system's vision, principles, taxonomy, and invariants
- Every other RFC depends on this one

### Principle 2: One Architecture Spec Per Major Subsystem

For each major subsystem identified in the scan:

- Create a separate Architecture Design RFC
- Each depends on the Conceptual Design RFC
- Each covers a cohesive set of modules with clear boundaries

### Principle 3: Impl Interface Specs Only on Request

Do NOT plan Implementation Interface Design specs unless the user explicitly asks for them. If requested:

- Create one per major API boundary surface
- Each depends on relevant Architecture Design RFCs

### Principle 4: Bounded Count

Stay within the max RFC count (default: 5):

- If there are more subsystems than the count allows, **merge** related subsystems into a single Architecture spec
- Prefer fewer, richer specs over many thin ones
- The conceptual design always counts as 1 of the total

### Principle 5: Meaningful Granularity

Do not create architecture specs that are too broad or too narrow:

- **Too broad**: One architecture spec covering the entire system (that's what conceptual is for)
- **Too narrow**: One per source file or small module
- **Right size**: One per major subsystem with 2+ modules and distinct responsibility

## Subsystem Identification Heuristic

From the scan's structural analysis:

1. **Top-level packages/crates/modules** with distinct names and responsibilities are subsystem candidates
2. **Cluster related modules**: If several small modules serve the same purpose (e.g., `utils/`, `helpers/`, `common/`), merge them
3. **Respect dependency direction**: Modules in the same layer that depend on each other are often one subsystem
4. **Simple projects** (1-3 modules): May produce only 1 architecture spec
5. **Complex projects** (10+ modules): Group into 3-4 subsystems max

## Output Format

Present the proposed RFC graph to the user as a table and dependency diagram.

### Table Format

```markdown
| RFC | Title | Kind | Namespace | Summary | Depends On |
|-----|-------|------|-----------|---------|------------|
| RFC-001 | [System] Vision and Principles | Conceptual | — (root) | System goals, core principles, taxonomy | — |
| RFC-AUTH-001 | [Subsystem A] Architecture | Architecture | auth (AUTH) | Components, data flow, constraints for A | RFC-001 |
| RFC-AGSP-001 | [Subsystem B] Architecture | Architecture | agentspace (AGSP) | Components, data flow, constraints for B | RFC-001 |
```

(Without namespaces, the Namespace column shows "—" for all rows and IDs are plain `RFC-NNN`.)

### Dependency Diagram

```
RFC-001 (Conceptual: System Vision — root)
├── auth/RFC-AUTH-001 (Architecture: Subsystem A)
└── agentspace/RFC-AGSP-001 (Architecture: Subsystem B)
```

### Confirmation Prompt

After presenting the plan, ask via the `ask_user` tool:

> "Here is the proposed RFC structure for your project. Before I generate the specs:
> 1. Should any subsystems be merged or split?
> 2. Should any RFC titles be adjusted?
> 3. Would you like to add Implementation Interface Design specs?
> 4. Should the total count change?
> 5. (Namespaced mode) Are the namespace names and prefixes correct?
>
> Confirm to proceed, or suggest adjustments."

## Adjustment Rules

If the user wants changes:

- **Merge**: Combine two architecture RFCs into one covering both subsystems
- **Split**: Break one architecture RFC into two (if count allows)
- **Add impl interface**: Add Implementation Interface Design RFCs (increases count)
- **Rename**: Update RFC titles
- **Reorder**: Change RFC numbering
- **Change count**: Increase or decrease the max

After adjustments, re-present the updated plan for confirmation.

## Examples

### Small Project (1-2 modules)

```
| RFC | Title | Kind |
|-----|-------|------|
| RFC-001 | System Vision and Principles | Conceptual |
| RFC-002 | System Architecture | Architecture |
```

Total: 2 RFCs.

### Medium Project (3-6 modules)

```
| RFC | Title | Kind |
|-----|-------|------|
| RFC-001 | System Vision and Principles | Conceptual |
| RFC-002 | Core Engine Architecture | Architecture |
| RFC-003 | API Layer Architecture | Architecture |
| RFC-004 | Storage Layer Architecture | Architecture |
```

Total: 4 RFCs.

### Large Project (10+ modules)

```
| RFC | Title | Kind |
|-----|-------|------|
| RFC-001 | System Vision and Principles | Conceptual |
| RFC-002 | Core Domain Architecture | Architecture |
| RFC-003 | Service Layer Architecture | Architecture |
| RFC-004 | Infrastructure Architecture | Architecture |
| RFC-005 | API and Integration Architecture | Architecture |
```

Total: 5 RFCs (at default max).

## Notes

- The plan is a proposal, not a commitment. The user has full control.
- RFC numbers assigned during planning may change if user adjusts. In namespaced mode, numbering is per-namespace (`RFC-<PREFIX>-001`, `RFC-<PREFIX>-002`, …) — each namespace starts its own strict sequence; only the root-level conceptual RFC uses the global root sequence
- Recovery proceeds in order: conceptual first, then architecture (per namespace). Generated RFCs are written directly into their namespace directories
- After generation, rfc-index.md (root rollup + one local index per namespace), rfc-namings.md, and rfc-history.md are updated to reflect all generated specs
