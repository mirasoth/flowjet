# fj

**fj** is a one-shot coding-agent CLI — everything after the command is the query:

```bash
fj explain this repo
fj -f what did we decide last time?
fj summarize README.md
```

It embeds [soothe-nano](https://github.com/mirasoth/soothe-nano) — tools, skills, MCP, subagents, and progressive loading — with SQLite persistence.

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

```bash
fj setup
```

`fj setup` is a guided setup for a local OpenAI-compatible server (Ollama, LM Studio, vLLM, ...) — it updates only endpoint/key/model basics in `~/.soothe/config/nano.yml` and keeps other keys intact.

**Cloud (no config file):**

```bash
export OPENAI_API_KEY=sk-...
fj summarize README.md
```

Missing `nano.yml` falls back to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

### 3. Run

```bash
fj who are you
fj list Python files in this directory
```

## Usage

```text
fj setup
fj completion zsh|bash
fj [options] [--] <query...>
```

| Flag | Meaning |
|------|---------|
| `-c PATH` / `--config` | Alternate `nano.yml` |
| `-t ID` / `--thread` | Alone: pin active thread; with query: continue it |
| `-f` / `--follow` | Continue the latest active thread |
| `-l` / `--list` | List latest threads (newest first; default 20) |
| `-n NUM` | Threads to list with `-l` (`0` = all); requires `-l` |
| `-w DIR` / `--workspace` | Workspace root |
| `--no-stream` | Wait for the full answer instead of streaming tokens |
| `-v` / `--verbose` | Mirror tool calls and custom events on stderr |
| `-V` / `--version` | Version |
| `--` | Force remaining argv into the query |

**Query modes:**

```text
fj QUERY...              # start a new thread (default)
fj -f QUERY...           # continue the latest active thread
fj -t ID QUERY...        # continue a specific thread
fj -t ID                 # pin thread as active (no query)
```

- Queries start a **new thread** by default; use `-f` to continue the latest or `-t` to continue/pin a specific one.
- `-f` and `-t` are mutually exclusive; `-n` requires `-l`; `-l` takes no query.
- One query per thread at a time; different threads may run concurrently.
- With `-v`, `fj` prints the thread `<id>` on stderr before the run.

### Shell completion

```bash
# zsh
eval "$(fj completion zsh)"
# bash
eval "$(fj completion bash)"
# persist in ~/.zshrc / ~/.bashrc
```

Tab completion predicts natural-language intents (not only flags) using the router **`fast`** model from `nano.yml` — it does not start the coding agent. If `fast` is omitted, it falls back to `default`.

## Defaults

| Concern | Default |
|--------|---------|
| Config | `~/.soothe/config/nano.yml` (`SOOTHE_HOME` overrides home) |
| Checkpoints | SQLite at `~/.soothe/data/soothe_checkpoints.db` |
| Workspace | CWD (`SOOTHE_WORKSPACE`) |
| Output | Progress on stdout line 1 (tools + AI narration); final answer printed once (`--no-stream` hides narration preview) |

## Builtin skills

fj ships AgentSkills under `fj_ai/builtin_skills/` (planning, TDD, debugging, document tools, and more) and registers them with soothe-nano on startup. They appear in progressive skill discovery alongside nano’s own builtins.

Add your own by pointing `nano.yml` at skill folders (`SKILL.md` + frontmatter):

```yaml
skills:
  - ~/.soothe/skills/my-reviewer
  - ./skills/deploy
```

Progressive skills are on by default (compact catalog + load on demand). Tune under `progressive_skills:` in `nano.yml`.

## MCP servers

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

## Powered by

**fj** is built on [soothe-nano](https://github.com/mirasoth/soothe-nano) — tools, skills, MCP, subagents, and progressive loading, with SQLite persistence. For a full TUI coding agent from the same stack, see [mirasoth/soothe](https://github.com/mirasoth/soothe).

## Development

```bash
git clone https://github.com/caesar0301/fj-ai.git
cd fj-ai
make sync-dev
make test
make lint
```

- **CI** — format, lint, tests on Python 3.11–3.13; build + `twine check`
- **Release** — GitHub Release → PyPI

## License

MIT
