# Partition Specs into Namespaces

Migrate an existing flat specs/impl layout into a namespaced layout (one directory + ID prefix per service or module). This is a **user-confirmed, git-tracked, mapping-recorded** operation — never run it silently.

## Objective

Take a project whose RFCs all live flat in `.platonic/specs/` (IDs `RFC-NNN`) and reorganize them into namespace directories with qualified IDs (`RFC-<PREFIX>-NNN`), rewriting all cross-references and recording a full old-ID → new-ID mapping.

## When to Use

- Total RFC count ≥ 10, or ≥ 3 independent services/modules in the project
- `.platonic/specs/` or `.platonic/impl/` is too large to navigate manually
- Existing hand-made subdirectories exist but are not declared in `.platonic.yml` (regularize them)

Do NOT use when the project is small (< 10 RFCs, single service) — flat is fine.

## Preconditions

1. **Clean git working tree** — migration uses `git mv` so renames are tracked; verify with `git status` and **ask the user** if the tree is dirty
2. **User invoked or approved the operation** — propose it, but never trigger automatically
3. Backups are unnecessary (git history is the backup), but the user may request a branch first

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| Specs path | No | `.platonic/specs` | Flat specs directory |
| Impl path | No | `.platonic/impl` | Flat impl directory |
| Namespace plan | Yes | — | Produced in Step 2, confirmed by user |
| ID mapping record | Yes | — | Written to `rfc-history.md` in Step 7 |

## Process

### Step 1: Inventory

1. Scan the specs root: all base RFCs (`RFC-NNN-<name>.md`), versioned files (`-<letter>.md`), and impl guides (`IG-NNN-<name>.md`)
2. Scan for **existing subdirectories** (e.g., a hand-created `.platonic/specs/realdeep/`) — these are pre-partitioned clusters that need regularizing, not migrating
3. Extract metadata: titles, kinds, `Depends on`, cross-references between RFCs
4. Build an initial cross-reference map (which RFCs reference which)

### Step 2: Propose Namespace Plan

Cluster RFCs by:

1. **Existing subdirectories** — RFCs already in a subdirectory become that namespace as-is (they keep their files but may be renumbered if their IDs don't follow the qualified format)
2. **Title/semantic grouping** — RFCs whose titles, `Stage` fields, or target modules clearly belong to one service (use `init-scan`-style heuristics: subsystem boundaries, dependency clusters)
3. **Cross-cutting RFCs stay at the root** — conceptual designs, system-wide contracts, anything referenced by 2+ clusters. Do not force every RFC into a namespace.
4. **User hints** — if the user names the services, use their partition directly

Present the plan as a table via the `ask_user` tool (plain-text questions do not pause the loop):

```markdown
| Cluster | → Namespace | Prefix (candidates) | RFCs | Notes |
|---------|-------------|--------------------|------|-------|
| auth/session, auth/device | auth | AUTH (recommended) | 3 | |
| workspace, task runner | agentspace | AGSP, ASP | 5 | |
| world-view, glossary | (root, cross-cutting) | — | 2 | stays RFC-NNN |
```

### Step 3: Confirm Prefixes via ask_user

For **each** proposed namespace, present 2–4 prefix candidates and ask the user to pick or provide their own:

- **Candidate generation heuristics**:
  - Service name ≤ 4 letters → direct uppercase (`auth` → **AUTH**)
  - Multi-word → initials (`miracloud gateway` → **MGW**)
  - Long word → vowel-stripped compression (`agentspace` → **AGSP**) or salient syllable (`realdeep` → **RD**)
- **Rules**: `^[A-Z]{1,4}$`; unique across namespaces; `RFC`/`IG` reserved. Mark the recommended candidate and why.
- The user may batch-confirm all prefixes in one table if the clusters were uncontested.

### Step 4: Final Plan Confirmation (hard gate)

Before touching any file, re-present the complete migration plan via `ask_user`:

- Namespace table (name, prefix, description, directory)
- Renumbering: per namespace, assign `001, 002, …` preserving the original relative order of the old global numbers (stable ordering)
- File move preview: old path → new path, including versioned files (which follow their parents) and IG guides (which land in the mirrored namespace impl directory with per-namespace `IG-<PREFIX>-NNN` numbering)
- The count of cross-references that will be rewritten

**Do not proceed until the user explicitly confirms.**

### Step 5: Write `.platonic.yml`

Add the confirmed `namespaces:` section (create the file if absent — this is one of the three legitimate reasons to create it):

```yaml
namespaces:
  auth:
    prefix: AUTH
    description: Authentication and identity
  agentspace:
    prefix: AGSP
    description: Agent workspace service
```

### Step 6: Execute the Migration

For each namespace, in dependency-safe order:

1. Create `.platonic/specs/<ns>/` and `.platonic/impl/<ns>/`
2. `git mv` each base RFC to its new path with the new qualified ID filename (`.platonic/specs/RFC-035-session.md` → `.platonic/specs/auth/RFC-AUTH-001-session.md`)
3. Move versioned files with their parents, updating filename IDs the same way
4. Move impl guides to `.platonic/impl/<ns>/IG-<PREFIX>-NNN-<name>.md`, renumbered in the namespace's independent IG sequence (preserving relative order)
5. Update each moved RFC's title line (`# <new-ID>-<name>: ...`) and its `Depends on`/`Supersedes`/`Parent RFC` fields
6. **Rewrite cross-references across the entire specs and impl trees**: every occurrence of an old ID (`RFC-035`, `[RFC-035-session](RFC-035-session.md)`, …) becomes the new qualified ID with a corrected relative link path. Scan moved files AND files remaining at the root.

### Step 7: Record the ID Mapping (mandatory)

Append to `rfc-history.md` under today's date a permanent mapping block:

```markdown
### YYYY-MM-DD — Namespace Partition

**Namespaces created**: auth (AUTH), agentspace (AGSP)
**Cross-reference rewrite**: N references updated

| Old ID | New ID |
|--------|--------|
| RFC-035-session | RFC-AUTH-001-session |
| RFC-036-device-token | RFC-AUTH-002-device-token |
| IG-004-session | IG-AUTH-001-session |
```

This table is the only defense for external references (code comments, MR descriptions, old issues) that cite pre-migration IDs. **Never omit it.**

### Step 8: Regenerate Supporting Files

1. Generate local `rfc-index.md` in every namespace directory (see `specs-generate-index.md`)
2. Regenerate the root rollup `rfc-index.md`
3. Regenerate `rfc-namings.md` (source RFC IDs changed)
4. `rfc-history.md` keeps all prior events untouched (IDs in old events stay as they were — history is not rewritten); only the partition mapping is appended

### Step 9: Verify

1. Run `specs-validate-consistency`: all dependencies and cross-references resolve, no cycles
2. Run `specs-check-compliance`: per-namespace sequences contiguous, prefix consistency passes
3. `git status` shows only renames + regenerated supporting files; no RFC content lost (diff should show metadata/link changes only)
4. Report the summary: namespaces created, RFCs moved, references rewritten, mapping recorded

## Rollback

If anything goes wrong before commit: `git checkout -- . && git clean -fd .platonic/` restores the pre-migration state (renames tracked by git make this cheap). After commit, revert the migration commit.

## Rules

- **Never delete files** — only move/rename via `git mv`
- **Never renumber silently** — the mapping table is mandatory
- **Never rewrite history events** — old IDs in past history entries stay as they were
- **Frozen RFCs CAN be moved** — this is a filing change, not a content change; the version file mechanism is unaffected (content must remain byte-identical apart from the title-ID, metadata references, and cross-reference rewrites)
- **One namespace per RFC** — cross-cutting RFCs stay at the root; if a cluster genuinely spans two namespaces, it is root-level by definition

## Example

**Input**: flat `.platonic/specs/` with 14 RFCs (identity service 4, agentspace 7, conceptual 3), flat `.platonic/impl/` with 6 IGs.

**Output**:
- `.platonic/specs/RFC-001-vision.md` (root, unchanged)
- `.platonic/specs/identity/RFC-IDN-001..004-*.md` (renumbered from old 002/005/009/012)
- `.platonic/specs/agentspace/RFC-AGSP-001..007-*.md`
- `.platonic/impl/identity/IG-IDN-001..002-*.md`, `.platonic/impl/agentspace/IG-AGSP-001..004-*.md`
- `.platonic.yml` with `namespaces:`; rollup + 2 local indexes regenerated; mapping table appended to `rfc-history.md`
