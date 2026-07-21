# fj

[![PyPI version](https://img.shields.io/pypi/v/fj-ai.svg)](https://pypi.org/p/fj-ai)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fj-ai.svg)](https://pypi.org/p/fj-ai)
[![CI](https://github.com/caesar0301/fj-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/caesar0301/fj-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🎥 [Watch the demo video on Vimeo](https://vimeo.com/1211730182)

**fj** is a one-shot coding-agent CLI for the terminal. Type a question, get an answer — no UI, no context-switching:

```bash
fj explain this repo
fj summarize README.md
fj -f what did we decide last time?
```

It runs on [soothe-nano](https://github.com/mirasoth/soothe-nano) — tools, skills, MCP, subagents, and progressive loading — with SQLite persistence so every thread is resumable.

> Package: **fj-ai** · Runtime: **soothe-nano**

---

## Install

```bash
pip install fj-ai
# or
uv tool install fj-ai
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
| `-t ID` / `--thread` | Continue (or pin) a specific thread |
| `-l` / `--list` | List recent threads (newest first) |
| `-n NUM` | How many threads `-l` shows (`0` = all) |
| `-c PATH` / `--config` | Use an alternate `nano.yml` |
| `-w DIR` / `--workspace` | Workspace root |
| `--no-stream` | Wait for the full answer instead of streaming |
| `-v` / `--verbose` | Mirror tool calls on stderr |

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
git clone https://github.com/caesar0301/fj-ai.git
cd fj-ai
make sync-dev
make test
make lint
```

CI runs format, lint, and tests on Python 3.11–3.13; releases go GitHub Release → PyPI.

## Powered by

Built on [soothe-nano](https://github.com/mirasoth/soothe-nano). For a full TUI coding agent from the same stack, see [mirasoth/soothe](https://github.com/mirasoth/soothe).

## License

MIT
