# FlowJet

[![PyPI version](https://img.shields.io/pypi/v/flowjet-agent.svg)](https://pypi.org/p/flowjet-agent)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/flowjet-agent.svg)](https://pypi.org/p/flowjet-agent)
[![CI](https://github.com/caesar0301/flowjet-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/caesar0301/flowjet-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🎥 [Watch the demo video on Vimeo](https://vimeo.com/1211730182)

**FlowJet** (`flowjet-agent`) is a one-shot coding-agent CLI for the terminal. Type a question, get an answer — no UI, no context-switching:

```bash
fj explain this repo                    # alias of flowjet-agent
fj -f what did we decide last time
fjf what did we decide last time       # alias of fj -f
```

It runs on [soothe-nano](https://github.com/mirasoth/soothe-nano) — tools, skills, MCP, subagents, and progressive loading — with SQLite persistence so every thread is resumable.

> Package / formal CLI: **flowjet-agent** · aliases: **fj**, **fjf** (= `-f`) · Runtime: **soothe-nano** · Repo: **[flowjet-agent](https://github.com/caesar0301/flowjet-agent)**

See [docs/naming.md](docs/naming.md) for the formal naming model.

---

## Install

```bash
pip install flowjet-agent
# or
uv tool install flowjet-agent
```

Requires Python 3.11+.

## Configure

**Option A — Local model (guided):**

```bash
fj setup
```

Walks you through an OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, …) and writes the basics to `~/.soothe/config/nano.yml`.

**Option B — Cloud (no config file):**

```bash
export OPENAI_API_KEY=sk-...
fj summarize README.md
```

Missing `nano.yml` falls back to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

## Doctor

Check whether this machine can run fj (tool binaries, providers, observability).
Requires ``soothe-nano`` with the ``diagnose`` API (1.0.8+):

```bash
fj doctor
fj doctor --deep
fj doctor --live-llm
fj doctor --format json
```

## Run

```bash
fj who are you
fj list Python files in this directory
fj refactor the parser to use dataclasses
```

---

## Conversation

Threads persist across runs in SQLite. Continue the latest, jump to a specific one, or list them:

```bash
fj -f and now add tests          # continue latest active thread
fj -t abc123 continue from here  # continue a specific thread
fj -l                            # list recent threads
```

## Flags

```text
fj [options] [--] <query...>
```

| Flag | Meaning |
|------|---------|
| `-f` / `--follow` | Continue the latest active thread |
| `-t ID` / `--thread` | Continue (or pin) a specific thread (overrides `-f`) |
| `-l` / `--list` | List recent threads (newest first) |
| `-n NUM` | How many threads `-l` shows (`0` = all) |
| `-c PATH` / `--config` | Use an alternate `nano.yml` |
| `-w DIR` / `--workspace` | Workspace root |
| `--no-stream` | Wait for the full answer instead of streaming |
| `-v` / `--verbose` | Mirror tool calls on stderr |

> `-t` and `-f` may be used together; `-t` wins (explicit id overrides follow).

Shell completion (AI-assisted, predicts natural-language intents, not just flags):

```bash
eval "$(fj completion zsh)"     # or: fj completion bash
```

---


---

## Extend

### Skills

fj ships AgentSkills (planning, TDD, debugging, document tools, MCP builder, and more) and supports your own via `nano.yml`:

```yaml
skills:
  - ~/.soothe/skills/my-reviewer
  - ./skills/deploy
```

Each skill is a `SKILL.md` with frontmatter; progressive loading keeps the catalog compact and loads on demand.

### MCP servers

Connect any Model Context Protocol server:

```yaml
mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

With `defer: true` (default), MCP tools activate on demand.

---

## Development

```bash
git clone https://github.com/caesar0301/flowjet-agent.git
cd flowjet-agent
make sync-dev
make test
make lint
```

CI runs format, lint, and tests on Python 3.11–3.13; releases go GitHub Release → PyPI.

## Powered by

Built on [soothe-nano](https://github.com/mirasoth/soothe-nano). For a full TUI coding agent from the same stack, see [mirasoth/soothe](https://github.com/mirasoth/soothe).

## License

MIT
