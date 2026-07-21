# fj

**fj** is a one-shot coding-agent CLI — everything after the command is the query:

```bash
fj who is your name
fj explain this file
fj explain the auth flow in this repo
```

It embeds [soothe-nano](https://github.com/mirasoth/soothe-nano) (tools, skills, MCP, subagents, progressive loading) with SQLite persistence and config at `~/.soothe/config/nano.yml`.

> Package name: **fj-ai**. Runtime: **soothe-nano**.

## Quick start

### 1. Install

```bash
pip install fj-ai
# or
uv tool install fj-ai
```

Requires Python 3.11+.

### 2. Config

Run guided setup for a local OpenAI-compatible server (Ollama, LM Studio, vLLM, ...):

```bash
fj setup
```

`fj setup` updates only endpoint/key/model basics in `~/.soothe/config/nano.yml` and keeps
other existing config keys as-is.

You can still copy the bundled example manually:

```bash
mkdir -p ~/.soothe/config
cp nano.yml ~/.soothe/config/nano.yml
```

[`nano.yml`](nano.yml) is the minimal local profile; everything else uses soothe-nano defaults.

```bash
# start your local server / pull a model, then:
fj who are you
fj list Python files in this directory
```

**Cloud (no config file):**

```bash
export OPENAI_API_KEY=sk-...
fj summarize README.md
```

Missing `nano.yml` falls back to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

### 3. Defaults

| Concern | Default |
|--------|---------|
| Config | `~/.soothe/config/nano.yml` (`SOOTHE_HOME` overrides home) |
| Checkpoints | SQLite at `~/.soothe/data/soothe_checkpoints.db` |
| Workspace | CWD (`SOOTHE_WORKSPACE`) |
| Output | Progress on stdout line 1 (tools + AI narration); final answer printed once (`--no-stream` hides narration preview) |

## Usage

```text
fj setup
fj completion zsh|bash
fj -l
fj -l -n 50
fj --reset
fj --reset <query...>
fj -t <thread-id>
fj -t <thread-id> <query...>
fj [options] [--] <query...>
```

| Flag | Meaning |
|------|---------|
| `-c PATH` / `--config` | Alternate `nano.yml` |
| `-t ID` / `--thread` | Alone: pin active thread; with query: continue it |
| `-l` / `--list` | List latest threads (newest first; default 20) |
| `-n NUM` | Threads to list with `-l` (`0` = all); requires `-l` |
| `--reset` | Start a new active thread (alone, or with a query) |
| `-w DIR` / `--workspace` | Workspace root |
| `--no-stream` | Disable token streaming; print final answer only |
| `-v` / `--verbose` | Mirror tool/custom events on stderr |
| `-V` / `--version` | Version |
| `--` | Force remaining argv into the query |

Queries continue the **latest active thread** by default. Use `--reset` to start fresh, or `-t` alone to pin a thread. `-l` cannot be combined with a query / `--reset` / `-t`; `--reset` and `-t` are mutually exclusive.
```bash
# put fj on PATH (pick one)
uv tool install fj-ai
# or: export PATH="/Users/chenxm/Workspace/fj-ai/.venv/bin:$PATH"

# enable Tab completion (zsh)
eval "$(fj completion zsh)"
# persist in ~/.zshrc:
#   eval "$(fj completion zsh)"
```

Tab completion predicts natural-language intents (not only flags). It uses the
router **`fast`** model from `nano.yml` via soothe-nano — it does **not** start
the coding agent. Configure an optional fast role:

```yaml
router_profiles:
  - name: default
    router:
      default: "local:llama3.2"
      fast: "local:llama3.2:1b"
```

If `fast` is omitted, completion falls back to `default`.

**Note:** Tab only works when `fj` is resolvable for the same command you type
(on `PATH`, or as an absolute/venv path). If completion is not installed or
`fj` is missing, Tab falls through silently.

## Builtin skills

fj ships AgentSkills under `fj_ai/builtin_skills/` (planning, TDD, debugging,
document tools, and more) and registers them with soothe-nano on startup.
They appear in progressive skill discovery alongside nano’s own builtins.

## Add skills

Point nano at skill folders (`SKILL.md` + frontmatter) in `nano.yml`:

```yaml
skills:
  - ~/.soothe/skills/my-reviewer
  - ./skills/deploy

# Or register a whole package root of builtins:
builtin_skill_roots:
  - ./my-package/builtin_skills
```

```text
~/.soothe/skills/my-reviewer/
  SKILL.md
```

```markdown
---
name: my-reviewer
description: Review Python PRs for style and security
---

# Reviewer

When asked to review code, check for ...
```

Progressive skills are on by default (compact catalog + load on demand). Tune under `progressive_skills:` in `nano.yml`.

## Powered by

**fj** is built on [soothe-nano](https://github.com/mirasoth/soothe-nano) — tools, skills, MCP, subagents, and progressive loading, with SQLite persistence.

## Add MCP servers

```yaml
mcp_builtins:
  - playwright

mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    defer: true
    enabled: true
```

With `defer: true` (default), MCP tools activate on demand.

## Agent features

fj is a thin CLI over **soothe-nano** (soothe-deepagents + soothe-sdk).

| Layer | Behavior |
|-------|----------|
| **Tools** | Core tools at startup; deferred via `search_tools` |
| **Skills** | Compact listings + `search_skills` / `invoke_skill` |
| **MCP** | Deferred by default; activated on demand |

Also included: builtin tool groups, ready subagents (planner, explorer, research, browser), workspace scoping, YAML/env config, SQLite persistence, and middleware (limits, timeouts, retries).

## Compared to other agents

For a full TUI coding agent from the same stack, see [mirasoth/soothe](https://github.com/mirasoth/soothe).

| | **fj / soothe-nano** | **soothe** | **OpenCode** | **Pi-style** |
|--|----------------------|------------|--------------|--------------|
| Shape | Thin one-shot CLI | Full TUI + optional daemon | Full TUI product (JS/TS) | Minimal loops |
| Agent loop | CoreAgent (ReAct) | Strange Loop: plan → assess → execute | Product agent loop | Single / lean loop |
| Goals | One query → answer | Goal-oriented; autopilot multi-goal DAG | Session / product UX | Usually single turn |
| Autopilot | — | Daemon schedule, dreaming, cron, veritas | — | — |
| Tools / skills / MCP | Progressive | Same core + TUI / loop durability | Product surface | Often fixed |
| Config | `nano.yml` | `nano.yml` + `soothe.yml` | App / project config | Code / light config |
| Best when | Scriptable coding in a repo | Interactive + 24/7 goal orchestration | Daily interactive coding | Experiments |

- **vs soothe:** shared CoreAgent; fj is argv → answer; soothe adds Strange Loop, TUI, and autopilot.
- **vs OpenCode:** rich TUI product vs argv → answer (fj) or goal-orchestration stack (soothe).
- **vs Pi-style:** lean loops vs progressive loading, workspace security, sqlite threads.

## Development

Requires a sibling [soothe](https://github.com/mirasoth/soothe) checkout at
`../soothe` (see `[tool.uv.sources]` in `pyproject.toml`) until
`soothe-nano>=0.9.9` is on PyPI — then remove the path source and lock against
the registry.

```bash
git clone https://github.com/caesar0301/fj-ai.git
cd fj-ai
make sync-dev
make test
make lint

uv run fj who is your name
```

```text
src/fj_ai/
  agent.py          # create_nano_agent + sqlite + fj defaults
  builtin_skills/   # AgentSkills tree (registered at startup)
  cli.py            # argv → query / setup / completion
  config.py         # nano.yml loader
  skills.py         # register_fj_builtin_skills()
  stream.py         # stdout streaming
  completion/       # Tab intent completion (fast model, no agent)
  shell/            # zsh/bash completion scripts
nano.yml
.github/workflows/
  ci.yml
  release.yml
```

- **CI** — format, lint, tests on Python 3.11–3.13; build + `twine check`
- **Release** — GitHub Release / `workflow_dispatch` → PyPI

## License

MIT
