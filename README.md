# FlowJet

[![PyPI version](https://img.shields.io/pypi/v/flowjet.svg)](https://pypi.org/p/flowjet)
[![Python versions](https://img.shields.io/pypi/pyversions/flowjet.svg)](https://pypi.org/p/flowjet)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A coding agent that lives in your terminal.** Ask a question, get an answer — no UI, no context switching. When you need to drive it from code, the same agent runs as a service with an OpenAI-compatible HTTP API and ACP over WebSocket.

<!-- DEMO PLACEHOLDER ---------------------------------------------------------
     Replace this block with the recorded GIF once it is ready. Use an absolute
     URL so the image also renders in the PyPI description (relative paths do
     not resolve there):

     ![fj running in the terminal](https://raw.githubusercontent.com/caesar0301/flowjet/main/docs/assets/fj-demo.gif)
---------------------------------------------------------------------------- -->

> _Demo GIF coming soon — `fj` in action._

| Surface | Command | Use it when |
|---------|---------|-------------|
| CLI | `fj` | You want answers in your terminal |
| Service | `flowjet-server` | An app, editor, or SDK drives the agent |

Built on [soothe-nano](https://github.com/mirasoth/soothe-nano): tools, skills, MCP and subagents, with conversations saved locally so you can pick up where you left off.

---

## CLI

Requires Python 3.11+.

```bash
pip install flowjet
fj setup                     # guided: writes ~/.flowjet/config/nano.yml
fj "explain this repo"
```

```bash
fj explain this repo
fj -f "and now add tests"    # continue the latest thread in this project
fjf "what did we decide?"    # shortcut for fj -f
fj -l                        # list recent threads
```

`-f` is scoped to your current project, so work in other checkouts never hijacks your thread.

On an interactive terminal, `fj` shows a live dashboard: a status badge, a one-line strip (step X/N, elapsed, tokens, last updated), the current action, an activity history (tool calls plus the agent's intermediate reasoning between them) and an answer preview. Piped or redirected output stays plain text with no progress content. Display is tunable via `NO_COLOR`, `FJ_FORCE_COLOR`, `FJ_PROGRESS_WIDTH` and `FJ_SNAPSHOT`.

Shell completion predicts full queries, not just flags:

```bash
eval "$(fj completion zsh)"   # or: fj completion bash
```

Something off? Run `fj doctor` (add `--deep` or `--live-llm` for a full check).

---

## Server

```bash
pip install 'flowjet[server]'   # adds the HTTP stack
flowjet-server                  # port 8618 (or: fj serve --port 8618)
```

```python
from openai import OpenAI

client = OpenAI(api_key="local", base_url="http://127.0.0.1:8618/v1")
print(client.responses.create(model="default", input="Hello"))
```

Per-request options go in `extra_body.flowjet`:

| Field | Values | Meaning |
|-------|--------|---------|
| `session` | string | Isolates workspace + conversation thread |
| `interaction_mode` | `agent` (default) / `ask` | `ask` is hard read-only |
| `projection` | `report` / `progress` / `developer` | How much SSE detail to expose |

Walkthroughs for the OpenAI SDK, raw HTTP, and ACP: [examples/README.md](examples/README.md) · deployment: [deploy/README.md](deploy/README.md).

---

## Configuration

Both the CLI and server read `nano.yml` — the CLI from `$FLOWJET_HOME/config/nano.yml` (default `~/.flowjet/config/nano.yml`), the server from `/flowjet/config/nano.yml`. `fj setup` writes one for you; for server deployments, mount your own. A minimal example:

```yaml
providers:
  - name: default
    provider_type: openai
    api_base_url: "http://127.0.0.1:11434/v1"
    api_key: "ollama"
    models:
      - llama3.2

router_profiles:
  - name: default
    router:
      default: "default:llama3.2"

active_router_profile: default
```

Skills and MCP servers go in the same file:

```yaml
skills:
  - ~/.soothe/skills/my-reviewer

mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

Skills are `SKILL.md` files loaded on demand; MCP tools are deferred by default.

---

## Development

```bash
git clone https://github.com/caesar0301/flowjet.git
cd flowjet
make sync-dev && make test && make lint
```

## License

MIT
