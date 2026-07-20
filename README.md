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

Copy the example for a local OpenAI-compatible server (Ollama, LM Studio, vLLM, …):

```bash
mkdir -p ~/.soothe/config
cp nano.yml ~/.soothe/config/nano.yml
# or: fj -c ./nano.yml who are you
```

[`nano.yml`](nano.yml) is a minimal local profile; everything else uses soothe-nano defaults.

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

| | **fj / soothe-nano** | **deepagents** | **OpenCode** | **Pi-style** |
|--|----------------------|----------------|--------------|--------------|
| Shape | Library + thin CLI | Python harness | Full TUI (JS/TS) | Minimal loops |
| Install | `pip install fj-ai` | `pip install deepagents` | Native/npm | Varies |
| Config | `~/.soothe/config/nano.yml` | Code-first | App/project | Code / light config |
| Tools | Progressive | BYO / harness | Product surface | Often fixed |
| Skills | Progressive SKILL.md | Base / custom | Product plugins | Optional |
| MCP | First-class, deferred | Via adapters | Product MCP | Depends |
| Persistence | SQLite under `~/.soothe` | Pluggable | Product store | Often ephemeral |
| Subagents | Planner / research / browser | You define | Product UX | Usually single loop |
| Best when | Scriptable coding in a repo | Full harness control | Interactive TUI | Experiments |

- **vs deepagents:** harness + control vs coding defaults + one-line CLI.
- **vs OpenCode:** rich TUI vs argv in → answer out.
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
