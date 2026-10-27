# Refine Specifications

## Objective

Comprehensively refine and validate all specifications in the specs directory, ensuring consistency, compliance, and generating updated dynamic files.

## Inputs

- **Specs Directory**: Path to the specs directory containing RFC files
- **Verbose Mode** (optional): If true, include detailed warnings in output

## Process Overview

This is a comprehensive operation that performs multiple checks and updates:

1. Validate consistency between RFC files
2. Check taxonomy consistency
3. Check standard compliance
4. Generate updated history, index, and namings files

## Step 1: Validate Consistency

**Read**: `references/specs/specs-validate-consistency.md` and apply it to the specs directory.

**Expected Output**: List of consistency errors and warnings

## Step 2: Check Taxonomy

**Read**: `references/specs/specs-check-taxonomy.md` and apply it to the specs directory.

**Expected Output**: Taxonomy consistency report

## Step 3: Check Standard Compliance

**Read**: `references/specs/specs-check-compliance.md` and apply it to the specs directory.

**Expected Output**: Compliance report with errors and warnings

## Step 4: Generate Dynamic Files

Perform these operations in order:

1. **Generate History**: Read `references/specs/specs-generate-history.md` and update rfc-history.md
2. **Generate Index**: Read `references/specs/specs-generate-index.md` and update rfc-index.md
3. **Generate Namings**: Read `references/specs/specs-generate-namings.md` and update rfc-namings.md

## Output Summary

After completing all steps, provide:

1. **Errors Found**: List all errors discovered during validation
2. **Warnings Found**: List all warnings (if verbose mode)
3. **Files Updated**: List of files that were modified
4. **Recommendations**: Any suggestions for improvement

## Structural Recommendation: Namespaces

When reporting recommendations, apply this health check:

- **Total RFC count ≥ 10, OR ≥ 3 clearly independent services/modules detected** (multiple language manifests, compose services, distinct top-level packages), AND no `namespaces:` declared in `.platonic.yml` → recommend partitioning the specs/impl tree into namespaces. Point the user to `specs-partition` for migrating an existing flat layout (or to `init-plan-modular-specs` for planning new namespaced specs).
- Existing namespaces but RFCs piling up in undeclared subdirectories → suggest either declaring those directories as namespaces or moving the files via `specs-partition`.

Do not execute the migration as part of `specs-refine` — it is a separate, user-confirmed operation.

## Execution Order

**Important**: Execute steps in this exact order:

1. Validation checks (Steps 1, 2, 3) - these are read-only
2. Generation operations (Step 4) - these modify files

This ensures you have complete information before making changes.

## Error Handling

- If critical errors are found, report them but continue with other operations
- If a file cannot be read, skip it and report the issue
- If generation fails for one file, continue with others

## Verification

After completion, verify:

- All dynamic files (history, index, namings) are updated
- No broken references exist
- All RFCs comply with `assets/templates/template-rfc-standard.md`
- Terminology is consistent across files

## Notes

- Always read the referenced reference files before executing their operations
- Preserve existing content when updating files (only modify specified sections)
- Update "Last Updated" dates in modified files to today's date
