# {{FEATURE_NAME}} Implementation Architecture

> Implementation guide for {{FEATURE_DESCRIPTION}} in {{PROJECT_NAME}}.
> 
> **Crate/Module**: `{{MODULE_NAME}}`
> **Source**: Derived from {{SOURCE_RFCS}}
> **Related RFCs**: {{RELATED_RFCS}}
> **Language**: {{LANGUAGE}}
> **Framework**: {{FRAMEWORK}}

---

## 1. Overview

{{OVERVIEW_DESCRIPTION}}

### 1.1 Purpose

This document specifies the **implementation architecture** for {{FEATURE_NAME}} as defined in {{PRIMARY_RFC}}. It provides:

- Concrete module/crate structure
- Type definitions with full field specifications
- Interface/trait definitions
- Implementation details and algorithms
- Error handling strategy
- Testing approach

### 1.2 Scope

**In Scope**:
- {{IN_SCOPE_ITEM_1}}
- {{IN_SCOPE_ITEM_2}}

**Out of Scope**:
- {{OUT_OF_SCOPE_ITEM_1}}
- {{OUT_OF_SCOPE_ITEM_2}}

### 1.3 Spec Compliance

This implementation guide **supersedes** RFC specifications with concrete details but **MUST NOT contradict** them. All invariants and requirements from source RFCs are preserved.

---

## 2. Architectural Position

### 2.1 System Context

{{SYSTEM_CONTEXT_DESCRIPTION}}

```
{{SYSTEM_CONTEXT_DIAGRAM}}
```

### 2.2 Dependency Graph

```
{{DEPENDENCY_GRAPH}}
```

### 2.3 Module Responsibilities

| Module | Responsibility | Dependencies |
|--------|----------------|--------------|
| `{{MODULE_1}}` | {{RESPONSIBILITY_1}} | {{DEPS_1}} |
| `{{MODULE_2}}` | {{RESPONSIBILITY_2}} | {{DEPS_2}} |

### 2.4 Dependency Constraints

**{{MODULE_NAME}}**:
- **MUST** {{CONSTRAINT_1}}
- **MUST NOT** {{CONSTRAINT_2}}
- **MAY** {{OPTIONAL_1}}

---

## 3. Module Structure

```
{{MODULE_NAME}}/
├── Cargo.toml (or package.json, etc.)
└── src/
    ├── lib.rs              # Public API surface
    ├── {{FILE_1}}.rs       # {{FILE_1_DESCRIPTION}}
    ├── {{FILE_2}}.rs       # {{FILE_2_DESCRIPTION}}
    ├── {{SUBMODULE_1}}/
    │   ├── mod.rs          # {{SUBMODULE_1}} public interface
    │   ├── {{SUB_FILE_1}}.rs
    │   └── {{SUB_FILE_2}}.rs
    └── error.rs            # Error types
```

---

## 4. Core Types

### 4.1 {{TYPE_1_NAME}}

{{TYPE_1_DESCRIPTION}}

```{{LANGUAGE}}
{{TYPE_1_DEFINITION}}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `{{FIELD_1}}` | `{{FIELD_1_TYPE}}` | {{FIELD_1_DESC}} |
| `{{FIELD_2}}` | `{{FIELD_2_TYPE}}` | {{FIELD_2_DESC}} |

### 4.2 {{TYPE_2_NAME}}

{{TYPE_2_DESCRIPTION}}

```{{LANGUAGE}}
{{TYPE_2_DEFINITION}}
```

---

## 5. Key Interfaces

### 5.1 {{INTERFACE_1_NAME}}

{{INTERFACE_1_DESCRIPTION}}

```{{LANGUAGE}}
{{INTERFACE_1_DEFINITION}}
```

**Method Descriptions**:

| Method | Description |
|--------|-------------|
| `{{METHOD_1}}` | {{METHOD_1_DESC}} |
| `{{METHOD_2}}` | {{METHOD_2_DESC}} |

### 5.2 {{INTERFACE_2_NAME}}

{{INTERFACE_2_DESCRIPTION}}

```{{LANGUAGE}}
{{INTERFACE_2_DEFINITION}}
```

---

## 6. Implementation Details

### 6.1 {{ALGORITHM_1_NAME}}

{{ALGORITHM_1_DESCRIPTION}}

**Process**:
1. {{STEP_1}}
2. {{STEP_2}}
3. {{STEP_3}}

**Diagram** (if applicable):
```
{{ALGORITHM_DIAGRAM}}
```

### 6.2 {{STORAGE_OR_PROTOCOL_NAME}}

{{STORAGE_DESCRIPTION}}

**Format**:
```
{{FORMAT_SPECIFICATION}}
```

---

## 7. Error Handling

### 7.1 Error Types

```{{LANGUAGE}}
{{ERROR_TYPE_DEFINITION}}
```

### 7.2 Error Handling Strategy

| Error Category | Handling Approach |
|----------------|-------------------|
| {{ERROR_CAT_1}} | {{HANDLING_1}} |
| {{ERROR_CAT_2}} | {{HANDLING_2}} |

---

## 8. Configuration

### 8.1 Configuration Options

```{{LANGUAGE}}
{{CONFIG_TYPE_DEFINITION}}
```

### 8.2 Defaults

| Option | Default | Description |
|--------|---------|-------------|
| `{{OPTION_1}}` | `{{DEFAULT_1}}` | {{OPTION_1_DESC}} |
| `{{OPTION_2}}` | `{{DEFAULT_2}}` | {{OPTION_2_DESC}} |

---

## 9. Testing Strategy

### 9.1 Unit Tests

| Component | Test Focus |
|-----------|------------|
| `{{COMPONENT_1}}` | {{TEST_FOCUS_1}} |
| `{{COMPONENT_2}}` | {{TEST_FOCUS_2}} |

### 9.2 Integration Tests

{{INTEGRATION_TEST_DESCRIPTION}}

### 9.3 Test Utilities

```{{LANGUAGE}}
{{TEST_UTILITY_EXAMPLE}}
```

Gate test-only code behind feature flags:
```{{LANGUAGE}}
{{FEATURE_FLAG_EXAMPLE}}
```

---

## 10. Coding Plan

{{PLAN_SUMMARY}}

**Total Tasks**: {{TOTAL_TASKS}}
**Estimated Files**: {{ESTIMATED_FILES}} new / {{ESTIMATED_MODIFIED}} modified

The coding plan breaks this guide into an ordered sequence of implementation tasks, each paired with its tests. It lives inside this guide (not as a separate artifact) and must stay consistent with the architecture above.

### 10.1 Task Breakdown

#### Task {{TASK_NUMBER}}: {{TASK_TITLE}}

**Action**: Create / Modify
**File(s)**: `{{FILE_PATH}}`
**Guide Section**: Section {{GUIDE_SECTION}}
**Description**: {{TASK_DESCRIPTION}}

**Deliverables**:
- {{DELIVERABLE_1}}
- {{DELIVERABLE_2}}

**Dependencies**: {{TASK_DEPENDENCIES}}

#### Task {{TASK_NUMBER}}: Unit Tests for {{COMPONENT}}

**Action**: Create
**File(s)**: `{{TEST_FILE_PATH}}`
**Guide Section**: Section 9.1
**Description**: Unit tests for {{COMPONENT}}

**Test Cases**:
- {{TEST_CASE_1}}
- {{TEST_CASE_2}}
- {{TEST_CASE_3}}

**Dependencies**: Task {{IMPL_TASK_NUMBER}}

#### Task {{TASK_NUMBER}}: Integration Tests

**Action**: Create
**File(s)**: `{{INTEGRATION_TEST_PATH}}`
**Guide Section**: Section 9.2
**Description**: Integration tests for cross-component behavior

**Test Scenarios**:
- {{SCENARIO_1}}
- {{SCENARIO_2}}

**Dependencies**: {{ALL_IMPL_TASKS}}

### 10.2 Execution Order

1. {{ORDERED_TASK_1}}
2. {{ORDERED_TASK_2}}
3. {{ORDERED_TASK_3}}

### 10.3 Verification Checklist

- [ ] All tasks completed
- [ ] Project builds without errors
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] All RFC requirements covered (see Appendix A)

---

## 11. Migration / Compatibility

{{MIGRATION_DESCRIPTION}}

### 11.1 Breaking Changes

{{BREAKING_CHANGES_DESCRIPTION}}

### 11.2 Migration Path

{{MIGRATION_PATH_DESCRIPTION}}

---

## Appendix A: RFC Requirement Mapping

| RFC Requirement | Guide Section | Implementation |
|-----------------|---------------|----------------|
| {{REQ_1}} | Section {{SEC_1}} | {{IMPL_1}} |
| {{REQ_2}} | Section {{SEC_2}} | {{IMPL_2}} |

---

## Appendix B: Revision History

| Date | RFC Version | Changes |
|------|-------------|---------|
| {{DATE}} | {{RFC_VERSION}} | Initial guide |
