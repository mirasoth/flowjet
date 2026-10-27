# Create Implementation Guide

Create a new implementation guide from an RFC specification.

## Prerequisites

Before creating an implementation guide, ensure:

1. **RFC exists**: The source RFC document is available and in Frozen or Draft status
2. **Scope is clear**: You know which module/crate/package will implement the RFC
3. **Language is known**: Target programming language and framework are specified
4. **Project context**: You understand the existing codebase architecture

## Input Requirements

| Input | Required | Description |
|-------|----------|-------------|
| RFC Document | Yes | Path to source RFC specification |
| Target Module | Yes | Name of implementing module/crate/package |
| Language | Yes | Target programming language (e.g., Rust, Python, TypeScript) |
| Framework | No | Framework if applicable (e.g., Tokio, Actix, React) |
| Output Path | No | Where to save the guide (default: `.platonic/impl/`) |
| IG Number | No | Explicit `XXX` override; default = next sequential unused IG number |

## Process

### Step 1: Assign IG Number

1. Determine the **namespace scope from the source RFC**: a root-level RFC (`RFC-NNN`, at the specs root) produces a root-level IG; a namespaced RFC (`RFC-<PREFIX>-NNN`, in `.platonic/specs/<ns>/`) produces an IG in the same namespace
2. Scan the relevant impl directory (`.platonic/impl/` at root, or `.platonic/impl/<ns>/` for the namespace) for existing `IG-*.md` files
3. Default: next unused number in strict sequence (`001`, `002`, `003`, …) — exactly three numeric characters, zero-padded. **Sequences are independent per namespace** (and independent of the root sequence)
4. Use a non-sequential or aligned-with-RFC number **only** if the user explicitly requests it

### Step 2: Analyze RFC Specification

Read the RFC document and extract:

1. **Core Concepts**: Key abstractions and entities defined
2. **Requirements**: What must be implemented (MUST, SHALL)
3. **Constraints**: Limitations and invariants
4. **Interfaces**: Expected APIs and protocols
5. **Data Structures**: Defined types and schemas
6. **Behaviors**: Expected runtime behavior
7. **Dependencies**: Related RFCs and external systems

Create a checklist of all extractable requirements.

### Step 3: Design Architecture

Based on RFC analysis, design:

1. **Module Structure**: Directory layout and file organization
2. **Type Mappings**: How RFC concepts map to language types
3. **Dependency Graph**: Internal and external dependencies
4. **Data Flow**: How data moves through the system
5. **Error Strategy**: How errors are represented and handled

### Step 4: Define Concrete Types

For each RFC concept, define concrete types:

```rust
// Example: Rust type definition
/// Documentation referencing RFC section
pub struct ConceptName {
    /// Field documentation
    pub field_name: FieldType,
}
```

Include:
- Full type definitions with all fields
- Documentation comments referencing RFC
- Visibility modifiers appropriate to the language
- Generic parameters if needed

### Step 5: Define Interfaces

For each required behavior, define interfaces:

```rust
// Example: Rust trait definition
/// Trait documentation referencing RFC section
pub trait BehaviorName {
    /// Method documentation
    fn method_name(&self, param: ParamType) -> Result<ReturnType>;
}
```

Include:
- All required methods
- Parameter and return types
- Error types
- Async markers if applicable

### Step 6: Document Implementation Details

For complex algorithms or protocols:

1. Describe the algorithm step-by-step
2. Include diagrams if helpful
3. Reference RFC sections for requirements
4. Note any implementation choices and rationale

### Step 7: Generate Guide Document

Use the template from `assets/implementation/impl-guide-template.md`:

1. Fill in all sections
2. Include code examples
3. Add diagrams where helpful
4. Reference source RFC throughout
5. Document any interpretations of ambiguous specs
6. Author the coding plan (Section 10): ordered task breakdown with test pairing

## Output

A complete implementation guide document containing:

- Overview and architectural position
- Module structure
- Complete type definitions
- Interface/trait definitions
- Implementation details
- Error handling strategy
- Configuration options
- Testing strategy
- Coding plan (ordered task breakdown with test pairing)

**Naming Convention**: Implementation guides MUST be named `IG-XXX-<semantic-short-desc>.md` (root-level) or `IG-<PREFIX>-XXX-<semantic-short-desc>.md` (namespaced, mirroring the source RFC's namespace).

- `XXX`: Exactly **three numeric characters**, zero-padded (`001`–`999`)
- **Strict sequence**: Use the next unused IG number in the guide's scope (`max existing + 1`, zero-padded). Do not skip numbers unless the user explicitly requests a specific number or gap.
- IG numbering is independent of RFC numbering unless the user explicitly requests alignment
- **Namespace mirroring**: an IG lives in the same namespace as its source RFC — root RFC → `.platonic/impl/IG-XXX-...`, namespaced RFC → `.platonic/impl/<ns>/IG-<PREFIX>-XXX-...`. Never split a namespace's RFC and its IG across directories.

## Validation

After creating the guide:

1. Run `impl-validate-guide.md` operation to check for contradictions
2. Review against project coding standards
3. Verify all RFC requirements are addressed

## Example

**Input**:
- RFC: `.platonic/specs/RFC-042-message-queue.md` (Message Queue Protocol)
- Target Module: `acme-queue`
- Language: Rust
- Framework: Tokio (async runtime)

**Output**: `.platonic/impl/IG-003-message-queue-protocol.md` (next sequential IG number; example assumes IG-001 and IG-002 already exist)

(Namespaced variant: RFC `.platonic/specs/auth/RFC-AUTH-003-message-queue.md` → `.platonic/impl/auth/IG-AUTH-001-message-queue-protocol.md`, numbering within the auth namespace's own IG sequence.)

The guide would include:
- Crate structure for `acme-queue`
- Rust struct definitions for `QueueMessage`, `MessageEnvelope`, etc.
- Trait definitions for producer and consumer interfaces
- Persistence layer implementation details
- Message serialization schema
