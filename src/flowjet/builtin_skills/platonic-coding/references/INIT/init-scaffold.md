# Scaffold Project

Create the Platonic Coding infrastructure for a project.

## Objective

Set up the directory structure, configuration file, and RFC infrastructure needed for Platonic Coding. Spec templates are kept in the skill's `assets/` directory and are not copied into the user project.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| Project name | Yes | — | Name of the project |
| Project root | Yes | Current directory | Root directory of the project |
| Language | No | Auto-detect | Primary programming language |
| Framework | No | Auto-detect | Framework if applicable |
| Specs path | No | `.platonic/specs` | Path for RFC specifications |
| Impl path | No | `.platonic/impl` | Path for implementation guides |
| Drafts path | No | `.platonic/drafts` | Path for design drafts |
| Custom stages | No | None | Custom spec stages (e.g. `["Core", "Storage", "API", "Infra"]`) |
| Create `.platonic.yml` | No | No | Set to yes only if non-default paths or custom stages are needed |

## Steps

### Step 1: Gather Project Information

If not provided:

1. **Auto-detect language** from build files:
   - `Cargo.toml` → Rust
   - `package.json` → JavaScript/TypeScript
   - `pyproject.toml` / `setup.py` / `requirements.txt` → Python
   - `go.mod` → Go
   - `pom.xml` / `build.gradle` → Java
   - `*.csproj` / `*.sln` → C#
2. **Auto-detect framework** from dependencies in build files
3. **Ask user** for project name if not provided (or derive from directory name / package name)
4. **Ask user** if they want non-default paths or custom spec stages — if not, skip Step 2 entirely
5. **Detect multi-service structure** (namespaced mode candidates):
   - Multiple language manifests in distinct top-level directories (2+ `go.mod`, `Cargo.toml`, `package.json`, `pyproject.toml` in different service dirs)
   - Container-compose files declaring 3+ services
   - A `services/` or `apps/` directory with 3+ independent components
   - Microservice repository layout (distinct deployment units per directory)

   If detected, **propose namespaces** (one per service/module) via the `ask_user` tool: present the detected services as a table (name, description, suggested namespace name), let the user confirm/merge/drop. **Prefixes are never auto-assigned silently**: for each confirmed namespace, present 2–4 uppercase prefix candidates (≤4 letters, per the heuristics in `specs-partition.md`) and ask the user to pick or provide their own. Recording namespaces is a legitimate reason to create `.platonic.yml` (see Step 2).

### Step 2: Create .platonic.yml (only if overrides or namespaces are needed)

**Skip this step by default.** Only create `.platonic.yml` when the user requested non-default paths, custom spec stages, or namespaces were confirmed in Step 1. If the user is happy with defaults (`.platonic/specs`, `.platonic/impl`, `.platonic/drafts`) and no custom stages and no namespaces, `.platonic.yml` is not created.

If overrides are needed:

1. Read `assets/templates/template-platonic.yml`
2. Uncomment and fill the relevant sections:
   - `paths:` — only if any path differs from defaults
   - `specs.stages:` — only if custom stages are requested
   - `namespaces:` — only if namespaces were confirmed in Step 1 (name, `prefix: <user-confirmed uppercase ≤4 letters>`, `description:`; optional per-namespace `specs:`/`impl:` path overrides)
3. Write to `<project-root>/.platonic.yml`
4. **Skip if file already exists** (read existing config instead; if it lacks a confirmed `namespaces:` section, merge the section in with the user's approval)

### Step 3: Create Specs Directory

1. Create `<specs-path>/` directory
2. Read and process RFC infrastructure templates from `assets/templates/`:
   - `template-rfc-history.md` → `rfc-history.md`
   - `template-rfc-index.md` → `rfc-index.md`
   - `template-rfc-namings.md` → `rfc-namings.md`
3. Replace `{{PROJECT_NAME}}` in each template
4. Write output files to specs directory
5. For **each declared namespace** (if any): create `<specs-path>/<namespace>/` and generate its local `rfc-index.md` from `assets/templates/template-namespace-index.md`, replacing `{{PROJECT_NAME}}`, `{{NAMESPACE_NAME}}`, and `{{NAMESPACE_PREFIX}}`
6. **Skip files that already exist**

**Note**: Spec templates (`rfc-standard.md`, `rfc-template.md`, design templates) are **not** copied into the user project. They live in the skill's `assets/` directory and are read from there when needed (e.g., compliance checks, RFC generation). This avoids duplicating templates into every project.

### Step 4: Create Impl Directory

1. Create `<impl-path>/` directory
2. Read `assets/templates/template-impl-readme.md`
3. Replace `{{PROJECT_NAME}}` → project name
4. Write to `<impl-path>/README.md`
5. For **each declared namespace** (if any): create `<impl-path>/<namespace>/` (mirror of the specs namespace directory; IGs for a namespace's RFCs live here)
6. **Skip if file already exists**

### Step 5: Create Drafts Directory

1. Create `<drafts-path>/` directory
2. Read `assets/templates/template-drafts-readme.md`
3. Replace `{{PROJECT_NAME}}` → project name
4. Write to `<drafts-path>/README.md`
5. **Skip if file already exists**

### Step 6: Verify

Confirm all expected files exist:
- `.platonic.yml` — **only if overrides or namespaces were requested**; absent is the normal case
- `<specs-path>/rfc-history.md`
- `<specs-path>/rfc-index.md`
- `<specs-path>/rfc-namings.md`
- `<specs-path>/<namespace>/rfc-index.md` — for each declared namespace
- `<impl-path>/README.md`
- `<impl-path>/<namespace>/` — for each declared namespace
- `<drafts-path>/README.md`

Report any files that were skipped (already existed) vs. newly created. Note whether `.platonic.yml` was created or skipped, and list the declared namespaces with their prefixes.

## Template Processing Rules

- `{{PROJECT_NAME}}`: Replace with exact project name (case-sensitive)
- `{{DATE}}`: Replace with current date in YYYY-MM-DD format
- `{{LANGUAGE}}`: Replace with detected/provided language (lowercase)
- `{{FRAMEWORK}}`: Replace with detected/provided framework (lowercase), or empty string
- Preserve all other content exactly as in templates
- Maintain markdown formatting and structure

## Notes

- If a file already exists, **skip it** (never overwrite without explicit user permission)
- Use exact capitalization provided for project name
- Create parent directories as needed
- The specs templates directory contains `rfc-standard.md` plus copies of the spec-kind templates for user reference and customization
