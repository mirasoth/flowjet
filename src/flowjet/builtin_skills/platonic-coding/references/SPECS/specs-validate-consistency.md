# Validate Consistency

## Objective

Check consistency between RFC files, including cross-references, dependencies, and metadata.

## Inputs

- **Specs Directory**: Path to the specs directory

## Steps

1. **Scan All RFC Files**
   - Find all files matching `RFC-*.md` pattern in the specs root AND in every namespace directory declared in `.platonic.yml` (convention: root `RFC-NNN-<name>.md`, namespaced `RFC-<PREFIX>-NNN-<name>.md`; e.g. RFC-001-world-view.md, auth/RFC-AUTH-001-session.md)
   - Exclude supporting files: `rfc-history.md`, `rfc-index.md`, `rfc-namings.md`

2. **Extract Metadata from Each RFC**
   For each RFC, extract:
   - RFC ID (root: `RFC-NNN`; namespaced: qualified `RFC-<PREFIX>-NNN`)
   - Namespace (derived from the file's directory)
   - Status
   - Dependencies (from `**Depends on**: ...`)
   - Supersedes (from `**Supersedes**: ...`)
   - Title

3. **Check Dependencies**
   For each RFC:
   - Parse dependencies from "Depends on" field
   - Check if each dependency exists as an RFC file (search the whole specs tree — dependencies may cross namespaces)
   - Verify dependency format (root `RFC-NNN-<name>` or qualified `RFC-<PREFIX>-NNN-<name>`)
   - Report missing dependencies

4. **Check Cross-References**
   For each RFC:
   - Scan content for RFC references (patterns: `RFC-NNN`, `RFC-<PREFIX>-NNN`, `[RFC-XXXX](...)`)
   - Extract all referenced RFC IDs (both formats)
   - Check if referenced RFCs exist anywhere in the specs tree
   - Verify link targets resolve relative to the referencing file (`../<ns>/...` from one namespace to another, `<ns>/...` from root)
   - Report broken references

5. **Check Circular Dependencies**
   - Build dependency graph
   - Detect cycles in the graph
   - Report any circular dependencies found

6. **Check Metadata Consistency**
   - Verify RFC number in filename matches title
   - Verify status values are valid (Draft, Review, Frozen, Deprecated)
   - Verify date formats are YYYY-MM-DD
   - Check for missing required fields

7. **Generate Report**
   Create a report with:
   - **Errors**: Critical issues that must be fixed
   - **Warnings**: Issues that should be addressed

## Validation Rules

### Dependency Validation

- **Format**: Dependencies should be in format `RFC-XXXX` or `RFC-XXXX, RFC-YYYY` — either root-level (`RFC-NNN`) or qualified namespaced IDs (`RFC-<PREFIX>-NNN`); qualified IDs are globally unique and may reference any namespace
- **Existence**: Each dependency must exist as an RFC file somewhere in the specs tree
- **Status**: Prefer depending on Frozen RFCs over Draft RFCs (warning, not error)

### Cross-Reference Validation

- **Patterns to find**: 
  - `RFC-XXXX` (root-level)
  - `RFC-<PREFIX>-XXXX` (namespaced)
  - `[RFC-XXXX](filename.md)` and `[RFC-<PREFIX>-XXXX](...)`
  - `RFC-XXXX-<letter>` / `RFC-<PREFIX>-XXXX-<letter>` (versioned references)
- **Existence**: Referenced RFCs must exist anywhere in the specs tree
- **Link validity**: Links should point to correct files with working relative paths across namespace directories

### Metadata Validation

- **Required fields**: Status, Authors, Created, Last Updated
- **Status values**: Must be one of: Draft, Review, Frozen, Deprecated
- **Date format**: Must be YYYY-MM-DD
- **RFC ID**: Must match between filename and title (root `RFC-NNN` or qualified `RFC-<PREFIX>-NNN`)

## Output Format

### Errors

```
❌ Errors Found:
- RFC-002: Depends on RFC-999 which doesn't exist
- RFC-003: References RFC-888 which doesn't exist
- RFC-004: Invalid status "InvalidStatus" (must be Draft, Review, Frozen, or Deprecated)
```

### Warnings

```
⚠️  Warnings:
- RFC-001: Depends on RFC-002 which is Draft (prefer Frozen dependencies)
- RFC-003: RFC number in title (0003) doesn't match filename (RFC-004.md)
- RFC-005: Missing "Last Updated" field
```

## Verification Checklist

After validation, check:

- [ ] All dependencies exist
- [ ] All cross-references are valid
- [ ] No circular dependencies
- [ ] All metadata is consistent
- [ ] All status values are valid
- [ ] All dates are in correct format

## Notes

- **Errors** are critical and should block further operations
- **Warnings** are suggestions but don't block operations
- **Circular dependencies** are always errors
- **Missing RFCs** referenced in content are warnings (might be planned)
- **Missing RFCs** in dependencies are errors (explicit dependency must exist)
