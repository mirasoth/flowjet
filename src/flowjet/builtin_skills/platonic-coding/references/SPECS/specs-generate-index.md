# Generate Index

## Objective

Scan all RFC files in the specs tree (root + declared namespaces) and generate/update the **root rollup index** (`rfc-index.md`) plus a **local index** (`rfc-index.md`) inside every declared namespace directory. Projects without namespaces fall back to the pre-3.0 behavior: a single flat table in the root index.

## Inputs

- **Specs Directory**: Path to the specs directory
- **Namespaces**: Declared in `.platonic.yml` (`namespaces:` section) if present; empty otherwise

## Scan Scope

1. **Specs root**: files matching `RFC-NNN-*.md` (no namespace prefix — `RFC-` followed directly by digits)
2. **Each declared namespace directory** (default `<specs>/<name>/`): files matching `RFC-<PREFIX>-NNN-*.md` where `<PREFIX>` equals that namespace's declared prefix
3. **Exclusions** (all levels): `rfc-history.md`, `rfc-index.md`, `rfc-namings.md`
4. **Undeclared subdirectories**: RFCs found in directories not declared as namespaces are a warning (report them; suggest `specs-partition` or adding the namespace to `.platonic.yml`)
5. Separate base RFCs from versioned RFCs (suffix `-<letter>.md`); versioned files belong to their parent's level/namespace

## Extract Metadata

For each base RFC, extract from file content:
- RFC ID (root: `NNN` from filename `RFC-NNN-<name>.md`; namespaced: `<PREFIX>-NNN` from `RFC-<PREFIX>-NNN-<name>.md`)
- Namespace (derived from the file's directory: root or a declared namespace)
- Title (from `# <RFC-ID>-<name>: Title`)
- Status (from `**Status**: ...`), Created, Last Updated (YYYY-MM-DD)
- Kind (from `**Kind**: ...` if present)

## Index Layering

### Root `rfc-index.md` (rollup)

Read and process `assets/templates/template-rfc-index.md` structure. Sections:

1. **Namespaces table** — one row per declared namespace:
   | Namespace | Prefix | Description | RFCs | Last Updated | Local Index |
   - RFCs = count of base RFCs in that namespace
   - Last Updated = max Last Updated among its RFCs
   - Local Index = link to `<namespace>/rfc-index.md`
2. **Root-Level RFCs table** — base RFCs at specs root (in namespaced projects these are the cross-cutting RFCs; in single-namespace mode this table lists ALL RFCs and mirrors legacy behavior):
   | RFC | Title | Kind | Status | Created | Last Updated | Version |
   - Version column: list version links (`[va](RFC-NNN-<name>-a.md), …`) or `-`
3. **Quick Links** — by Kind and by Status, root-level RFCs only (namespaced RFCs are discoverable via local indexes)

Target size for the rollup: **one screen**. Never inline full per-namespace RFC tables into the root index — that is what local indexes are for.

### Per-namespace local `<specs>/<ns>/rfc-index.md`

Generated for **every declared namespace** (always, regardless of size). Read and process `assets/templates/template-namespace-index.md`, replacing:
- `{{PROJECT_NAME}}` → project name
- `{{NAMESPACE_NAME}}` → namespace name
- `{{NAMESPACE_PREFIX}}` → declared prefix

Content: the full detail table for that namespace's base RFCs (same columns as the root root-level table, sorted by `NNN` ascending within the namespace), plus version links and quick links.

## Generation Steps

1. Scan specs root + all declared namespace directories (per Scan Scope)
2. Extract metadata from every base RFC
3. For each declared namespace:
   - Generate local `rfc-index.md` from the namespace template
   - Compute summary row for the root rollup
4. Update root `rfc-index.md`:
   - Replace Namespaces table, Root-Level RFCs table, and Quick Links sections with generated content
   - Update `**Last Updated**:` field to today's date
   - Preserve all other sections unchanged

## Table Rules

- **Sorting**: root-level RFCs by number ascending; namespaced RFCs by `NNN` ascending within each namespace
- **ID columns**: `[RFC-NNN-<name>](RFC-NNN-<name>.md)` at root; `[RFC-<PREFIX>-NNN-<name>](RFC-<PREFIX>-NNN-<name>.md)` in local indexes (same-directory links)
- **Root index links to namespaced RFCs**: use the qualified ID with a namespace-relative path (e.g., `[RFC-AUTH-001-session](auth/RFC-AUTH-001-session.md)`)
- **Status**: exact status from RFC metadata
- **Dates**: YYYY-MM-DD

## Verification

After updating, verify:

- Every declared namespace has a local `rfc-index.md`, regenerated and current
- The root rollup contains a row per namespace and no inline per-namespace detail tables
- All base RFCs appear in exactly one index table (root-level table or a local index)
- Version links are correct and point to files in the same directory as the parent
- No broken links, including cross-directory relative paths
- Undeclared subdirectory RFCs (if any) are reported as warnings

## Notes

- Single-namespace mode (no `namespaces:` in `.platonic.yml`): generate the flat root index only — identical to pre-3.0 behavior
- If an RFC has no title, use the filename as fallback
- Exclude Deprecated RFCs from Quick Links, but keep them in tables with status shown
- Never delete or hand-rewrite local indexes during generation; regenerate them wholesale from the template
