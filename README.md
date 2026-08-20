# FlowJet

[![PyPI version](https://img.shields.io/pypi/v/flowjet-agent.svg)](https://pypi.org/p/flowjet-agent)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/flowjet-agent.svg)](https://pypi.org/p/flowjet-agent)
[![CI](https://github.com/caesar0301/flowjet-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/caesar0301/flowjet-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🎥 [Watch the demo on Vimeo](https://vimeo.com/1211730182)

**FlowJet** is a friendly one-shot coding agent for your terminal. Ask a question in plain English, get an answer — no UI, no context-switching.

```bash
fj explain this repo                    # the short alias for flowjet-agent
fj -f what did we decide last time       # continue the last conversation
fjf what did we decide last time        # alias of fj -f
```

It runs on [soothe-nano](https://github.com/mirasoth/soothe-nano) — tools, skills, MCP, subagents, and progressive loading — with SQLite persistence so every conversation is resumable.

> Package: **flowjet-agent** · aliases: `fj`, `fjf` (=`-f`) · Runtime: [soothe-nano](https://github.com/mirasoth/soothe-nano) · Naming details: [docs/naming.md](docs/naming.md)

---

## Install

```bash
pip install flowjet-agent
# or
uv tool install flowjet-agent
```

Requires Python 3.11+.

## Configure

**Option A — Local model (guided setup):**

```bash
fj setup
```

This walks you through an OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, …) and writes the basics to `~/.soothe/config/nano.yml`.

**Option B — Cloud (no config file needed):**

```bash
export OPENAI_API_KEY=sk-...
fj summarize README.md
```

Without a `nano.yml`, FlowJet falls back to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

## Doctor

Check whether your machine is ready to run `fj` (tool binaries, providers, observability):

```bash
fj doctor                 # quick check
fj doctor --deep          # thorough check
fj doctor --live-llm      # actually call the model
fj doctor --format json   # machine-readable
```

---

## Conversations

Threads persist in SQLite, so you can pick up where you left off — continue the latest, jump to a specific one, or list them:

```bash
fj -f and now add tests          # continue this project's latest active thread
fj -t abc123 continue from here  # continue a specific thread
fj -l                            # list recent threads
```

`-f` is scoped to the project you are in — the git repo root, or the current directory when it is not a repo — so parallel work in other checkouts never hijacks your thread. `fj -l` still lists every thread; pick one up from anywhere with `-t ID`.

## Flags

```text
fj [options] [--] <query...>
```

| Flag | Meaning |
|------|---------|
| `-f` / `--follow` | Continue the latest active thread in this project directory |
| `-t ID` / `--thread` | Continue (or pin) a specific thread (overrides `-f`) |
| `-l` / `--list` | List recent threads (newest first) |
| `-n NUM` | How many threads `-l` shows (`0` = all) |
| `-c PATH` / `--config` | Use an alternate `nano.yml` |
| `-w DIR` / `--workspace` | Workspace root |
| `--no-stream` | Wait for the full answer instead of streaming |
| `-v` / `--verbose` | Mirror tool calls on stderr |

> `-t` and `-f` can be combined; `-t` wins (explicit id overrides follow).

Shell completion is AI-assisted — it predicts natural-language intents, not just flags:

```bash
eval "$(fj completion zsh)"     # or: fj completion bash
```

---

## Extend

### Skills

FlowJet ships with AgentSkills (planning, TDD, debugging, document tools, MCP builder, and more). Add your own in `nano.yml`:

```yaml
skills:
  - ~/.soothe/skills/my-reviewer
  - ./skills/deploy
```

Each skill is a `SKILL.md` with frontmatter; progressive loading keeps the catalog compact and loads skills on demand.

### MCP servers

Connect any Model Context Protocol server:

```yaml
mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

With `defer: true` (the default), MCP tools activate on demand.

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
