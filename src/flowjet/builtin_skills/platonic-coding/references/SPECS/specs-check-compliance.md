# Check Standard Compliance

## Objective

Validate that all RFC files comply with the conventions defined in `assets/templates/template-rfc-standard.md`.

## Inputs

- **Specs Directory**: Path to the specs directory
- **Reference**: `assets/templates/template-rfc-standard.md` (skill asset, for validation rules; fall back to `<specs-path>/templates/rfc-standard.md` or root `rfc-standard.md` if present in older projects)

## Steps

1. **Read rfc-standard.md**
   - Prefer the skill asset `assets/templates/template-rfc-standard.md`
   - Fall back to `<specs-path>/templates/rfc-standard.md` or `<specs-path>/rfc-standard.md` for projects scaffolded before templates were kept in the skill
   - Understand required metadata fields
   - Understand status values and transitions
   - Understand structure requirements
   - Understand formatting conventions
   - Understand the dual ID formats (root-level `RFC-NNN` vs namespaced `RFC-<PREFIX>-NNN`)

2. **Scan All RFC Files**
   - Find all files matching `RFC-*.md` pattern in the specs root AND in every namespace directory declared in `.platonic.yml`
   - Root files must match `RFC-NNN-<name>.md` (no prefix); namespace files must match `RFC-<PREFIX>-NNN-<name>.md` with the namespace's declared prefix
   - Exclude supporting files: `rfc-history.md`, `rfc-index.md`, `rfc-namings.md`
   - RFCs in undeclared subdirectories → warning (suggest `specs-partition` or declaring the namespace)

3. **Check Metadata Fields**
   For each RFC, verify:
   - **Required fields present**: Status, Authors, Created, Last Updated
   - **Status value valid**: Must be Draft, Review, Frozen, or Deprecated
   - **Date format**: Must be YYYY-MM-DD
   - **ID format**: Root-level must match `RFC-NNN-<name>`; namespaced must match `RFC-<PREFIX>-NNN-<name>`. `NNN` is exactly three numeric characters (`001`–`999`)
   - **Optional fields**: Depends on, Supersedes (if present, must be valid format — qualified IDs like `RFC-AUTH-001-session` are valid everywhere)

4. **Check Namespace-Prefix Consistency** (namespaced mode only)
   For each RFC in a namespace directory, verify three-way consistency:
   - Directory: the RFC lives in the directory of a namespace declared in `.platonic.yml`
   - Filename prefix: `RFC-<PREFIX>-...` where `<PREFIX>` equals that namespace's declared prefix
   - Declared prefix: prefix matches `^[A-Z]{1,4}$`, is unique across namespaces, and is not `RFC`/`IG`
   - Any drift between directory, filename prefix, and declaration → **error**

5. **Check Structure**
   For each RFC, verify:
   - **Title format**: `# <RFC-ID>-<name>: Title` (e.g., `# RFC-001-world-view: ...` or `# RFC-AUTH-001-session: ...`)
   - **Abstract section**: Section 1 should be Abstract
   - **Scope section**: Should have Scope and Non-Goals
   - **Proper heading levels**: Consistent use of ##, ###, etc.

6. **Check Frozen RFC Rules**
   For RFCs with Status: Frozen:
   - **No direct edits**: File should not be modified (only via versions)
   - **Version format**: If versioned, must follow the parent's format: `RFC-NNN-<name>-<letter>.md` or `RFC-<PREFIX>-NNN-<name>-<letter>.md`
   - **Version location**: Versioned files must live in the same directory as their parent
   - **Version metadata**: Must have Parent RFC, Version, Changes fields

7. **Check Versioned RFC Rules**
   For versioned RFCs:
   - **Parent exists**: Parent RFC must exist in the same directory
   - **Version number**: Must be sequential (a, b, c, ...)
   - **Full content**: Must contain complete RFC, not just diffs
   - **Changes section**: Must document what changed

8. **Check Number Format & Sequence**
   - Every `NNN` is exactly three numeric characters (`001`–`999`), zero-padded
   - Sequence checks are **bucketed by scope**:
     - Root-level RFCs form a contiguous sequence from `001` (single global sequence)
     - Each namespace's RFCs form their own contiguous sequence from `001`, independent of other namespaces and of the root sequence
   - Gap or non-padded number within a bucket → **warning** (error only if clearly accidental; allow if user explicitly requested a non-sequential number)

9. **Check Formatting**
   - **Markdown syntax**: Valid markdown
   - **Links**: Valid link format `[text](file.md)`; cross-namespace links must resolve relative to the referencing file (`../<ns>/...`, `<ns>/...`, or `../...`)
   - **Tables**: Valid table format
   - **Code blocks**: Properly formatted

10. **Generate Report**
   Create a report with:
   - **Errors**: Violations that must be fixed
   - **Warnings**: Issues that should be addressed

## Validation Rules

### Required Metadata Fields

- **Status**: MUST be present, MUST be one of: Draft, Review, Frozen, Deprecated
- **Authors**: MUST be present
- **Created**: MUST be present, MUST be YYYY-MM-DD format
- **Last Updated**: MUST be present, MUST be YYYY-MM-DD format

### Status Rules

- **Draft**: Can be edited in place
- **Review**: Ready for review, can be edited
- **Frozen**: Cannot be edited, must create version for changes
- **Deprecated**: No longer active

### Structure Rules

- **Title**: Must start with `# <RFC-ID>-<name>: Title` (root-level `RFC-NNN-<name>` or namespaced `RFC-<PREFIX>-NNN-<name>`)
- **Number format**: `NNN` MUST be exactly three numeric characters (`001`–`999`), zero-padded
- **Prefix format**: Namespaced RFCs MUST use the namespace's declared prefix (`^[A-Z]{1,4}$`, unique, not `RFC`/`IG`)
- **Strict sequence**: Base RFC numbers SHOULD form a contiguous sequence from `001` with no gaps, **within each scope independently** (root sequence and each namespace's sequence are checked separately; warn on gaps unless documented user intent)
- **Abstract**: Section 1 must be Abstract
- **Scope**: Should have Scope and Non-Goals section
- **Sections**: Use consistent numbering (1, 2, 3...)

### Frozen RFC Rules

- **Immutability**: Frozen RFCs cannot be edited directly
- **Versioning**: Changes require creating RFC-NNN-<name>-<letter>.md
- **Version format**: <letter> must be a single lowercase letter (a, b, c, ... z)

### Versioned RFC Rules

- **Parent RFC**: Must specify Parent RFC field
- **Version**: Must specify Version field (001, 002...)
- **Changes**: Must specify Changes field describing what changed
- **Full content**: Must contain complete RFC content

## Output Format

### Errors

```
❌ Errors Found:
- RFC-001: Missing required field "Authors"
- RFC-002: Invalid status "Invalid" (must be Draft, Review, Frozen, or Deprecated)
- RFC-003: Frozen RFC was modified directly (should create version instead)
- RFC-004-001: Missing "Parent RFC" field
- RFC-005: Date format invalid "2026/01/28" (must be YYYY-MM-DD)
```

### Warnings

```
⚠️  Warnings:
- RFC-001: Missing "Abstract" section
- RFC-002: Section numbering inconsistent
- RFC-003: Depends on Draft RFC (prefer Frozen dependencies)
- RFC-004: Last Updated date is older than Created date
```

### Verification Checklist

After checking, verify:

- [ ] All required metadata fields are present
- [ ] All status values are valid
- [ ] All dates are in correct format
- [ ] All IDs match their scope's format (root `RFC-NNN`; namespaced `RFC-<PREFIX>-NNN` matching the declared prefix)
- [ ] Namespace-prefix consistency: directory ↔ filename ↔ `.platonic.yml` declaration
- [ ] Root and per-namespace sequences are contiguous from `001` (or gaps are intentional/user-requested)
- [ ] Frozen RFCs are not modified directly
- [ ] Versioned RFCs follow the correct format and live beside their parent
- [ ] Structure follows `assets/templates/template-rfc-standard.md` conventions
- [ ] Formatting is consistent

## Notes

- **Errors** block compliance and should be fixed
- **Warnings** are suggestions for improvement
- **Frozen RFC edits** are critical errors
- **Missing required fields** are errors
- **Format issues** are usually warnings unless they break parsing

## Reference

Always refer to `assets/templates/template-rfc-standard.md` for:
- Exact field requirements
- Status transition rules
- Versioning rules
- Structure templates
- Formatting conventions
