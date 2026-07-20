# fj

**fj** is a one-shot coding-agent CLI. Everything after the command is the query:

```bash
fj who is your name
fj 修改这个文件。
fj explain the auth flow in this repo
```

It embeds [soothe-nano](https://github.com/mirasoth/soothe-nano) — a full coding CoreAgent (tools, skills, MCP, subagents, progressive loading) — with **default SQLite** persistence and config at **`~/.soothe/config/nano.yml`**.

> **fj-ai** is the Python package name; the agent runtime is **soothe-nano**. This README documents both the CLI and the agent capabilities you get underneath.

## Quick start

### 1. Install

```bash
pip install fj-ai
# or
uv tool install fj-ai
```

Requires Python 3.11+.

### 2. Minimal config (no external SaaS)

Copy the example and point it at a **local** OpenAI-compatible server (Ollama, LM Studio, vLLM, …). No Tavily, Langfuse, Postgres, or browser stack required.

```bash
mkdir -p ~/.soothe/config
cp nano.yml ~/.soothe/config/nano.yml
# or run without installing into ~/.soothe:
#   fj -c ./nano.yml who are you
```

The repo-root [`nano.yml`](nano.yml) is a validated minimal profile: local OpenAI-compatible provider (Ollama), SQLite, search/research/browser subagents off.

Start Ollama (or your local server), pull a model, then:

```bash
fj who are you
fj list Python files in this directory
```

**Zero-config alternative** (cloud API, still no extra services):

```bash
export OPENAI_API_KEY=sk-...
# optional: export OPENAI_BASE_URL=https://api.openai.com/v1
fj summarize README.md
```

If `~/.soothe/config/nano.yml` is missing, soothe-nano bootstraps from `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

### 3. What fj sets up for you

| Concern | Default |
|--------|---------|
| Config | `~/.soothe/config/nano.yml` (`SOOTHE_HOME` overrides home) |
| Checkpoints | SQLite at `~/.soothe/data/soothe_checkpoints.db` |
| Workspace | Current working directory (`SOOTHE_WORKSPACE`) |
| Output | Ephemeral progress on stdout line 1; final answer only when done |

## Usage

```text
fj [options] [--] <query...>
```

| Flag | Meaning |
|------|---------|
| `-c PATH` / `--config` | Alternate `nano.yml` |
| `-t ID` / `--thread` | Reuse a LangGraph thread id (multi-turn via sqlite) |
| `-w DIR` / `--workspace` | Workspace root for file/shell tools |
| `--no-stream` | Same final-only answer (progress still shown on a TTY) |
| `-v` / `--verbose` | Also mirror tool/custom events on stderr |
| `-V` / `--version` | Version |
| `--` | Force remaining argv into the query (including leading `-`) |

Examples:

```bash
fj who is your name
fj 修改这个文件。
fj -v refactor the CLI parser to support Unicode
fj --thread demo-1 continue from last turn: what files did you touch?
fj -w ~/code/myapp find TODO comments
```

## Add skills

Skills are folders with a `SKILL.md` (frontmatter + instructions). Point nano at them in `nano.yml`:

```yaml
skills:
  - ~/.soothe/skills/my-reviewer
  - ./skills/deploy
```

Example skill layout:

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

**Progressive skills** (on by default): the agent keeps a compact catalog in context and loads full skill bodies on demand via `search_skills` / `invoke_skill`, with optional intent prefetch on cold threads. Tune under `progressive_skills:` in `nano.yml` (budget %, core skills, semantic search).

## Add MCP servers

MCP is opt-in. Either enable builtins or declare servers:

```yaml
# Builtin names (playwright, github, slack, postgres, gdrive, …)
mcp_builtins:
  - playwright

# Or explicit servers (stdio / SSE / HTTP / websocket)
mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    defer: true          # progressive: tools listed, activated when needed
    enabled: true
```

**Progressive MCP**: with `defer: true` (default), MCP tools are not dumped into the full tool array; the agent discovers and activates them as needed within a listing budget (`progressive_mcp:`).

## Agent features (soothe-nano / fj-ai)

fj is a thin CLI; the agent is **soothe-nano**, built on **soothe-deepagents** + **soothe-sdk**.

### Progressive loading

| Layer | Behavior |
|-------|----------|
| **Tools** | Core tools bound at startup; deferred tools discovered via `search_tools` (`progressive_tools`) |
| **Skills** | Compact listings + `search_skills` / `invoke_skill`; intent prefetch on turn 0 |
| **MCP** | Servers deferred by default; tools activated on demand |

This keeps the context window small on every turn while still exposing a large capability surface.

### Coding product defaults (beyond raw deepagents)

- Builtin tool groups: shell/execution, file ops, HTTP, data, datetime, optional search
- Ready subagents: planner, explorer, deep/academic research, browser-use (disable what you do not need)
- Workspace scoping + path security policies
- YAML / env config factory (`SootheConfig`)
- SQLite-first persistence (Postgres optional in nano for larger deployments)
- Middleware: context limits, tool timeouts, rate-limit retries, edit coalescing, role routing

### Optimizations inspired by / layered on deepagents

deepagents provides the harness (filesystem, shell, todos, subagents, context management). soothe-nano adds production-shaped defaults and progressive discovery so a coding agent can run in a repo without hand-wiring every tool and prompt. fj then packages that as a single argv → agent CLI with sqlite threads and cwd as workspace.

## Compared to other agents

| | **fj / soothe-nano** | **deepagents** | **OpenCode** | **Pi / pi-agent style** |
|--|----------------------|----------------|--------------|-------------------------|
| Shape | Library + thin CLI | Python harness library | Full TUI product (JS/TS) | Minimal / research-oriented agent loops |
| Install surface | `pip install fj-ai` | `pip install deepagents` | Native/npm installer | Varies by project |
| Config | `~/.soothe/config/nano.yml` | Code-first | App/project config | Usually code or light config |
| Tools in context | Progressive (core + search) | Bring-your-own / harness set | Product tool surface | Often smaller fixed sets |
| Skills | Progressive SKILL.md catalog | Base / custom | Product skills/plugins | Optional / custom |
| MCP | First-class, deferred by default | Via adapters if you wire them | Product MCP support | Depends on fork |
| Persistence | SQLite default under `~/.soothe/data` | Pluggable checkpointer | Product session store | Often ephemeral |
| Subagents | Planner / research / browser ready | You define `task` agents | Product multi-agent UX | Usually single loop |
| Best when | Scriptable coding agent in a repo | Custom harness control | Interactive daily coding IDE-in-terminal | Experiments, minimal loops |

**vs deepagents:** use deepagents when you want the harness and full control; use fj/nano when you want coding defaults, progressive skills/tools/MCP, and a one-line CLI.

**vs OpenCode:** OpenCode is a rich interactive TUI product. fj is intentionally small — argv in, streamed answer out — while sharing the same class of capabilities (tools, MCP, skills) through soothe-nano.

**vs Pi-agent-style agents:** Pi-oriented agents emphasize lean loops and simplicity. fj trades a bit of that minimalism for progressive loading, workspace security, and sqlite threads so longer coding sessions stay practical.

## Development

```bash
git clone https://github.com/caesar0301/fj-ai.git
cd fj-ai
make sync-dev
make test
make lint

# Run against a local soothe-nano checkout (optional):
#   uv add --editable ../soothe/packages/soothe-nano
uv run fj who is your name
```

### Project layout

```text
src/fj_ai/
  cli.py       # argv → query, asyncio entry
  config.py    # ~/.soothe/config/nano.yml loader
  agent.py     # create_nano_agent + sqlite checkpointer
  stream.py    # stdout streaming
nano.yml                 # minimal local config
.github/workflows/
  ci.yml
  release.yml
```

### CI / release

- **CI** — format, lint, unit tests on Python 3.11–3.13; build + `twine check`
- **Release** — on GitHub Release publish (or workflow_dispatch), build and publish to PyPI (`UV_PUBLISH_TOKEN` or OIDC trusted publishing)

## License

MIT
