# VERSION Mode

Two distinct version tracks:

| Track | What it versions | Commands |
|-------|------------------|----------|
| **Workspace** | Research artifacts in a project (plans, chapters, deliverables) | `version tag\|history\|diff\|backup\|list` |
| **Skill package** | The oh-my-research skill itself (semver + changelog) | `skill-version show\|check\|sync\|set\|bump` |

Do not mix them. Workspace tags live under `.omr/versions/`; skill semver lives in `SKILL.md` → `metadata.version`.

---

## Workspace versioning

Lightweight tags and backups for a research workspace.

### Trigger

```
version tag <label>
version history
version diff <a> <b>
version backup
version list
```

### Behavior

| Command | Action |
|---------|--------|
| `tag` | Record label + timestamp + artifact hashes/paths under `.omr/versions/` |
| `history` | List tags chronologically |
| `diff` | Summarize file-level changes between two tags/backups |
| `backup` | Timestamped copy of `docs/plans` + current synth mode dirs + `deliverables/` (including an optional `deliverables/wiki/`) into `.omr/backups/` |
| `list` | List backups and tags |

Script: `scripts/version_control.py` (mechanical tags/backups only).

### Practice

Tag after Gate A pass and after Gate D publish.

---

## Skill package versioning

Semver for the **oh-my-research** skill package (not a user research workspace).

### Source of truth

`skills/oh-my-research/SKILL.md` → `metadata.version` (e.g. `"1.1.3"`).

Kept in sync with:

- `.claude-plugin/marketplace.json` → `metadata.version` and `plugins[0].version`
- `CHANGELOG.md` (human-readable history)

### Trigger

```
skill-version show
skill-version check
skill-version sync
skill-version set <X.Y.Z> [--message "…"]
skill-version bump major|minor|patch [--message "…"]
```

Keywords: skill version, bump skill, changelog, release skill.

### Behavior

| Command | Action |
|---------|--------|
| `show` | Print `SKILL.md` `metadata.version` |
| `check` | Exit 0 only if marketplace matches `SKILL.md` |
| `sync` | Write `SKILL.md` version into `marketplace.json` |
| `set` | Set an explicit semver in `SKILL.md`, sync marketplace, prepend a `CHANGELOG.md` stub |
| `bump` | Semver bump (`major` / `minor` / `patch`), then same as `set` |

Script (from repo root):

```bash
python3 skills/oh-my-research/scripts/skill_version.py show
python3 skills/oh-my-research/scripts/skill_version.py check
python3 skills/oh-my-research/scripts/skill_version.py sync
python3 skills/oh-my-research/scripts/skill_version.py bump minor --message "Describe the change"
python3 skills/oh-my-research/scripts/skill_version.py set 2.0.0 --message "Breaking change summary"
```

### Semver policy

| Bump | When |
|------|------|
| **patch** | Docs/templates/scripts fixes; no behavior contract change |
| **minor** | New mode, gate, export capability, or compatible workflow enhancement |
| **major** | Breaking change to ops, artifact layout, or gate contracts |

### Agent checklist when releasing a skill change

1. Confirm the change warrants a bump (policy above).
2. Run `skill-version bump … --message "…"` (or `set`).
3. Fill in the new `CHANGELOG.md` section (Added / Changed / Fixed).
4. Run `skill-version check` — must pass before commit/tag.
5. Do **not** invent a parallel version string in README body text; point to `SKILL.md` / changelog.
