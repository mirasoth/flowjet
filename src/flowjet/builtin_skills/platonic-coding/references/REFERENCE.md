# Platonic Coding — Complete Reference

Detailed operation guide for Platonic Coding skill.

## Operations (25 total)

### BRAINSTORM (`references/brainstorm/`)
| Operation | Purpose |
|-----------|---------|
| `brainstorm` | Collaborative design exploration → approved draft + post-draft routing |

### INITIALIZATION (`references/init/`)
| Operation | Purpose |
|-----------|---------|
| `init-scaffold` | Create directories, config, templates |
| `init-scan` | Analyze existing codebase |
| `init-plan-modular-specs` | Propose RFC dependency graph |
| `init-recover-conceptual` | Generate conceptual RFC from code |
| `init-recover-architecture` | Generate architecture RFCs from code |
| `init-recover-impl-interface` | Generate impl interface RFCs (optional) |

### SPECIFICATION (`references/specs/`)
| Operation | Purpose |
|-----------|---------|
| `specs-refine` | Comprehensive validation + update |
| `specs-generate-history` | Update change history |
| `specs-generate-index` | Update RFC index (root rollup + per-namespace local indexes) |
| `specs-generate-namings` | Update terminology reference |
| `specs-validate-consistency` | Check cross-references |
| `specs-check-taxonomy` | Verify terminology usage |
| `specs-check-compliance` | Validate against RFC standard |
| `specs-partition` | Migrate flat specs/impl into namespaces (user-confirmed, mapping recorded) |

### IMPLEMENTATION (`references/impl/`)
| Operation | Purpose |
|-----------|---------|
| `impl-full` | End-to-end: spec → guide (incl. coding plan) → code + tests |
| `impl-create-guide` | Create guide from RFC |
| `impl-code` | Implement from existing guide |
| `impl-validate-guide` | Check guide vs RFC contradictions |
| `impl-update-guide` | Sync guide with RFC changes |

### REVIEW (`references/review/`)
| Operation | Purpose |
|-----------|---------|
| `review` | Spec compliance review (6-step, report-only) |

### WORKFLOW (`references/workflow/`)
| Phase | Activities |
|-------|------------|
| 1 | Optional BRAINSTORM mode → draft → RFC → `specs-refine` |
| 2 | Optional BRAINSTORM mode → `impl-full` |
| 3 | `review` → compliance report |

---

## Auto-Detection Decision Tree

```
Intent keywords in request? (brainstorm, discuss, investigate, explore,
                             deep analysis, deep dive, think through,
                             trade-offs, what's the best approach)
  → Yes (and no canonical op name) → BRAINSTORM mode
      → approved draft → post-draft routing → Phase 1 or Phase 2

Otherwise, inspect project state:

No Platonic infrastructure (no .platonic.yml AND no .platonic/specs/) ?
  → Has code? → recovery flow (init-scan → recover)
  → No code? → init-scaffold

Has specs but no RFCs?
  → Has drafts? → Phase 1 (draft → RFC)
  → No drafts? → Phase 1 (start fresh, optional BRAINSTORM mode)

Has RFCs but no guides?
  → Phase 2 (impl-full or impl-create-guide)

Has RFCs + guides?
  → In progress? → resume Phase 2
  → Complete? → Phase 3 (review)

Ambiguous? → Ask or resume current phase
```

**Note**: `.platonic.yml` is optional. Project metadata (name, language, framework) is auto-detected from host manifests (`Cargo.toml`, `package.json`, `pyproject.toml`, `go.mod`, etc.). Default paths (`.platonic/specs`, `.platonic/impl`, `.platonic/drafts`) are used unless overridden in `.platonic.yml`. The presence of `.platonic/specs/` (with Platonic files like `rfc-history.md`) is the primary signal that the project is already initialized. Create `.platonic.yml` only to override paths, set custom spec stages, or declare namespaces.

**Override**: Use canonical operations (`brainstorm`, `init-scaffold`, `specs-refine`, `impl-full`, `review`, `workflow --phase <N>`).

---

## Template Variables

Templates use `{{PLACEHOLDER}}` syntax. Common variables:

### Project-Level
- `{{PROJECT_NAME}}` — Project name
- `{{LANGUAGE}}` — Programming language
- `{{FRAMEWORK}}` — Framework or stack

### RFC-Level
- `{{RFC_NUMBER}}` — RFC identifier (e.g., "001")
- `{{TITLE}}` — RFC title
- `{{DATE}}` — Current date
- `{{AUTHORS}}` — Author name(s)

### Paths
- `{{SPECS_PATH}}` — Specs directory path (default: `.platonic/specs`; from `.platonic.yml` if present)
- `{{IMPL_PATH}}` — Implementation guides path (default: `.platonic/impl`; from `.platonic.yml` if present)
- `{{DRAFTS_PATH}}` — Design drafts path (default: `.platonic/drafts`; from `.platonic.yml` if present)

### Namespace-Level
- `{{NAMESPACE_NAME}}` — Namespace name (directory and declaration key)
- `{{NAMESPACE_PREFIX}}` — Namespace prefix (1–4 uppercase letters, user-confirmed)

---

## Naming Conventions

| Artifact | Scope | Pattern | Number field |
|----------|-------|---------|--------------|
| RFC | Root (cross-cutting) | `RFC-NNN-<name>.md` | `NNN`: exactly **three** numeric characters (`001`–`999`); global strict sequence |
| RFC | Namespace `<ns>` (prefix `PFX`) | `.platonic/specs/<ns>/RFC-PFX-NNN-<name>.md` | `NNN`: exactly three numeric characters; **independent strict sequence per namespace** |
| IG | Root | `IG-XXX-<name>.md` | `XXX`: exactly **three** numeric characters; global strict sequence |
| IG | Namespace `<ns>` | `.platonic/impl/<ns>/IG-PFX-XXX-<name>.md` | Independent sequence per namespace; mirrors the source RFC's namespace |

**Strict sequence**: When creating a new RFC or IG, assign the next unused number in order within its scope (root sequence and each namespace's sequence are independent). Do not skip numbers unless the user explicitly requests a specific number or gap. RFC and IG sequences are independent.

**Namespace prefixes**: 1–4 uppercase ASCII letters, unique across the project, `RFC`/`IG` reserved. Declared in `.platonic.yml` under `namespaces:`. Prefixes are proposed by the skill (2–4 candidates) and **confirmed by the user via `ask_user`** (if the host runtime exposes no structured questioning tool, present the candidates as numbered plain-text options and wait for the user's reply) — never auto-assigned. Namespace membership is derived from the file's directory (no metadata field).

---

## File Structure

Single-namespace mode (default — no `namespaces:` declared):

```
<project-root>/
├── .platonic.yml                   # OPTIONAL — only when overriding defaults, custom stages, or declaring namespaces
├── .platonic/
│   ├── specs/                      # RFC specifications (default path)
│   │   ├── rfc-history.md           # Change history (global)
│   │   ├── rfc-index.md             # Index (flat table, or rollup in namespaced mode)
│   │   ├── rfc-namings.md           # Terminology reference (global)
│   │   ├── RFC-001-world-view.md   # Individual RFC
│   │   └── RFC-002-message-queue.md
│   │
│   ├── impl/                       # Implementation guides
│   │   ├── README.md
│   │   ├── IG-001-user-authentication.md         # Impl guide for RFC-001-user-auth
│   │   └── IG-002-data-storage.md                # Impl guide for RFC-002-data-storage
│   │
│   └── drafts/                     # Phase 1 design drafts
│       ├── README.md
│       └── user-auth-design.md
│
└── <source-code>/                  # Your implementation
```

Namespaced mode (multi-service; `namespaces:` declared in `.platonic.yml`):

```
<project-root>/
├── .platonic.yml                   # Declares namespaces: name + prefix (+ optional paths)
├── .platonic/
│   ├── specs/
│   │   ├── rfc-history.md           # Global timeline (partition mappings recorded here)
│   │   ├── rfc-index.md             # One-screen ROLLUP: namespace summary + root RFC table
│   │   ├── rfc-namings.md           # Terminology reference (global)
│   │   ├── RFC-001-vision.md        # Cross-cutting RFCs stay at the root (RFC-NNN)
│   │   ├── auth/
│   │   │   ├── rfc-index.md         # Local index for this namespace
│   │   │   └── RFC-AUTH-001-session.md    # Independent sequence from 001
│   │   └── agentspace/
│   │       ├── rfc-index.md
│   │       └── RFC-AGSP-001-workspace.md
│   │
│   ├── impl/                       # Mirrors the specs namespaces
│   │   ├── README.md
│   │   ├── auth/
│   │   │   └── IG-AUTH-001-session.md
│   │   └── agentspace/
│   │       └── IG-AGSP-001-workspace.md
│   │
│   └── drafts/
│       └── ...
│
└── <source-code>/
```

**Note**: Spec templates (`rfc-standard.md`, `rfc-template.md`, design templates) are **not** copied into the user project. They live in the skill's `assets/` directory and are read from there when needed (RFC generation, compliance checks). This avoids duplicating templates into every project.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Wrong auto-detection | Use explicit operations (`init-scaffold`, `specs-refine`, `impl-full`, `review`) |
| Wrong placeholders | Check `.platonic.yml` paths (if present) match template values; if absent, defaults apply |
| Guide contradicts RFC | Run `impl-validate-guide`, then update guide or modify RFC |
| Specs not in index | Check `RFC-NNN-<name>.md` naming, run `specs-generate-index` |
| Missing terminology | Check term format in RFCs, run `specs-generate-namings` |
| Missing code refs in review | Use specific search terms, check naming conventions |
| Workflow stops at gate | Expected—say "no confirmations" to skip |
| `.platonic/specs/` too large to navigate (≥ 10 RFCs or ≥ 3 services) | Declare namespaces and run `specs-partition` (user-confirmed migration; mapping recorded in `rfc-history.md`) |
| RFC in a subdirectory not picked up by scans | Declare the subdirectory as a namespace in `.platonic.yml`, or move the RFC to a declared namespace / the root |
| Prefix mismatch (directory vs filename vs `.platonic.yml`) | `specs-check-compliance` reports the drift; fix the filename prefix or the declaration, then re-run |
| Cross-namespace link broken | Check relative path from the referencing file (`../<ns>/...`, `<ns>/...`), run `specs-validate-consistency` |
| Duplicate or skipped RFC/IG number | List existing numbers in the scope (root or namespace), propose the next sequential number, confirm with the user before renaming |
| `specs-partition` interrupted mid-migration | Check `rfc-history.md` for the recorded old-ID → new-ID mapping; finish the remaining renames manually (or re-run `specs-partition` on the untouched files), then run `specs-generate-index` |
| `.platonic/specs/` exists but is empty | Treat as Phase 1 start (not as an initialized project): ask the user whether to scaffold templates via `init-scaffold` or begin drafting a fresh RFC |

---

## Reference Files

- `references/brainstorm/` — Design exploration (brainstorm mode)
- `references/init/` — Initialization
- `references/specs/` — Specification management
- `references/impl/` — Implementation
- `references/review/` — Review
- `references/workflow/` — Workflow orchestration