# fj

**fj** is a one-shot coding-agent CLI — everything after the command is the query:

```bash
fj who is your name
fj 修改这个文件。
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
| Output | Progress on stdout line 1; final answer when done |

## Usage

```text
fj setup
fj [options] [--] <query...>
```

| Flag | Meaning |
|------|---------|
| `-c PATH` / `--config` | Alternate `nano.yml` |
| `-t ID` / `--thread` | Reuse LangGraph thread id |
| `-w DIR` / `--workspace` | Workspace root |
| `--no-stream` | Final-only answer (progress still on TTY) |
| `-v` / `--verbose` | Mirror tool/custom events on stderr |
| `-V` / `--version` | Version |
| `--` | Force remaining argv into the query |

```bash
fj setup
fj who is your name
fj -v refactor the CLI parser
fj --thread demo-1 continue: what files did you touch?
fj -w ~/code/myapp find TODO comments
```

## Add skills

Point nano at skill folders (`SKILL.md` + frontmatter) in `nano.yml`:

```yaml
skills:
  - ~/.soothe/skills/my-reviewer
  - ./skills/deploy
```

```text
~/.soothe/skills/my-reviewer/
  SKILL.md
```

## Powered by

**fj** is built on [soothe-nano](https://github.com/mirasoth/soothe-nano) — tools, skills, MCP, subagents, and progressive loading, with SQLite persistence.

```markdown
---
name: my-reviewer
description: Review Python PRs for style and security
---

# Reviewer

When asked to review code, check for ...
```

Progressive skills are on by default (compact catalog + load on demand). Tune under `progressive_skills:` in `nano.yml`.

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

```bash
git clone https://github.com/caesar0301/fj-ai.git
cd fj-ai
make sync-dev
make test
make lint

# optional local soothe-nano:
#   uv add --editable ../soothe/packages/soothe-nano
uv run fj who is your name
```

```text
src/fj_ai/
  cli.py       # argv → query
  config.py    # nano.yml loader
  agent.py     # create_nano_agent + sqlite
  stream.py    # stdout streaming
nano.yml
.github/workflows/
  ci.yml
  release.yml
```

- **CI** — format, lint, tests on Python 3.11–3.13; build + `twine check`
- **Release** — GitHub Release / `workflow_dispatch` → PyPI

## License

MIT
