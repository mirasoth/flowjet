# Changelog

All notable changes to **flowjet** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> History from 0.1.0–0.2.0 below was released as the separate `flowjet-server`
> distribution, now merged into `flowjet`. See [docs/upgrade.md](docs/upgrade.md).

## [Unreleased]

### Added

- **Rich terminal rendering for `fj` CLI output (TTY-only, minimal landing).**
  Final agent answers are now rendered as Markdown (headings, lists, tables,
  syntax-highlighted code blocks) and `fj threads -l` renders as a styled
  table when stdout is a terminal. Rendering lives in the new
  `flowjet.cli.render` module; `rich` is imported lazily (never on `fj -V`,
  `-h`, or completion paths) and every helper degrades to the existing
  plain-text output when stdout is piped or rich is unavailable, so scripted
  and piped output stays byte-identical. Progress-line rendering (ephemeral
  status, tool verbs) is unchanged.

- **Sandbox disk-watermark guard (`sandbox.min_free_bytes`).** A new
  `min_free_bytes` setting (bytes, default `0` = disabled) makes the ArcBox
  sandbox manager probe guest free space at session open and refuse the turn
  with a readable `SandboxDiskFullError` when it falls below the watermark —
  turning a write-heavy turn's mid-run ENOSPC spiral (whose cleanup commands
  hit the approval gate) into one upfront failure. The probe is fail-open: a
  broken probe warns but never blocks a turn. Separately, a failed workspace
  open (this guard or any other) now surfaces as a terminal `RunFailed` event
  (`code="workspace_open_error"`) with a best-effort `close_session`, instead
  of a raw exception escaping the stream with no terminal event for clients.

## [2.1.9] — 2026-10-27

### Changed

- **Refreshed builtin skills bundle.** Shipped two new research skills and
  retired a stale one: added `autoresearch` (an autonomous research loop with an
  orchestrator, scoring, and a security checklist) and `oh-my-research` (a
  structured evidence → synthesis pipeline with scripts and pattern presets),
  and removed the superseded `research-bootstrap` skill. The `platonic-coding`
  skill was reworked — its spec/IMPL/WORKFLOW references were tightened, a new
  `specs-partition.md` reference added, and the old `coding-plan-template.md` /
  `impl-guide-template.md` drafts dropped in favor of the consolidated template
  namespace. The top-level `builtin_skills/README.md` (a stale pointer) was
  removed; skills are still auto-registered via `register_builtin_skill_root`.

## [2.1.8] — 2026-10-26

### Fixed

- **PostgreSQL checkpointer is now wired for the server surface.**
  `Checkpointers.open()` (the `/v1/responses` + ACP server path) used to warn
  “Checkpointer backend 'postgresql' is not wired for the flowjet server surface
  yet” and yield `None`, so thread state never survived a turn — a deployment
  whose `persistence.default_backend` is `postgresql` silently ran every turn as
  a fresh conversation. It now builds an `AsyncPostgresSaver` on nano's shared
  checkpoints pool (`resolve_checkpointer()` → `(None, pool)`), opens the pool,
  and runs `setup()` once per process under nano's advisory lock
  (`SharedCheckpointerPool.setup_checkpointer`), so concurrent workers cannot
  race LangGraph's DDL. The shared pool is deliberately **not** closed on exit
  (it is process-wide). Failure still degrades to “no persistence” with a
  warning instead of failing startup; unknown backends keep the old behavior.

## [2.1.7] — 2026-10-25

### Added

- **Configurable workspace watched subdirectories.** A new
  `workspace_watched_subdirs` setting (env `FLOWJET_WORKSPACE_WATCHED_SUBDIRS`,
  comma-separated) flows from Settings →
  `SyncAwareWorkspaceResolver(watched_subdirs=...)` → `WorkspaceManager`, which
  pre-creates the configured subtrees at workspace open and wires them into the
  DirtyTracker. `None`/empty keeps the engine defaults (`input`/`working`/`output`)
  — behavior unchanged — and unsafe entries fail loud at workspace open rather
  than silently dropping sync coverage.

### Changed

- **Default identity no longer carries a personal creator byline.**
  `FLOWJET_CREATOR` is now empty (the soothe identity renderer omits
  "invented by {creator}" when the creator is blank) and
  `FLOWJET_IDENTITY_FRAGMENT` drops the byline lines, so identity answers name
  only (`{assistant_name}`). The vendor denylist (incl. Soothe/soothe-nano) is
  unchanged. Explicit `agent.assistant_identity` in deployment config still wins
  (e.g. MiraCloud branding).
- **Soothe dependency pin raised to `>=1.2.3,<2.0.0`** to match the coordinated
  release.

## [2.1.6] — 2026-10-24

### Fixed

- **ArcBox tool sandboxes stay usable across recycles, crashes and restarts.**
  The manager trusted its in-memory lease map, and the agent graph pinned its
  sandbox id at build time, so a guest that died behind a still-`ready` daemon
  record (host sleep, idle recycle, daemon restart) left the worker talking to a
  corpse: every file/shell tool failed and the agent reported an empty
  workspace even though the host tree was fully staged. `open_workspace` now
  probes readiness once per turn — a control-plane `info()` tier that catches a
  record outliving its VM plus terminal states, then a guest round-trip that
  catches a wedged guest — and kills, drops and replaces a lease that fails.
  Every new guest, whether spawned or adopted, is seeded from the host
  workspace, and in-flight run counts carry over so peer open/close pairs stay
  balanced. The agent cache key is now workspace **+ sandbox id**, so a respawn
  rebuilds the graph against the live guest.
- **Crash and restart recovery.** VMs are created with a labelled orphan
  deadline (`idle_timeout` + `on_idle=kill`) that the reaper re-arms every 60 s,
  so a process that dies leaves nothing behind — the daemon reaps it, with no
  cross-process coordination and no startup kill-list. On first use the manager
  scans owner-scoped sandboxes and adopts a surviving VM, pulling guest state to
  the host before pushing (recovering a crashed turn's artifacts) instead of
  spawning a duplicate; a failed create reconnects the client and retries once.
- **Every control-plane RPC is bounded** (`kill`/`set_lifecycle` 15 s, `connect`
  by `connect_timeout`). The SDK's per-RPC deadline is opt-in and was
  unconfigured: one wedged call stalled the reaper loop, and a stalled heartbeat
  reads to the daemon exactly like a dead owner — which gets healthy, in-use VMs
  reaped at their deadlines.

### Changed

- `sandbox.orphan_timeout_seconds` defaults to `max(900, 3 × idle_timeout_seconds)`
  instead of a fixed 900, and an explicit value is validated only when the
  sandbox is enabled — existing configs keep parsing unchanged. New keys:
  `recover_orphans` (adopt surviving VMs after a restart) and `owner` (label
  namespace, env `FLOWJET_SANDBOX_OWNER`) so planes sharing one ArcBox daemon
  never adopt or reap each other's sandboxes. See RFC-005 §5.1/§5.2.

## [2.1.5] — 2026-10-24

### Fixed

- **`ask_user` pauses render as Markdown on ACP/UI hosts.** A clarification
  turn's reply reused the CLI terminal block (space-indented `⏸ Paused for
  input:` followed by `• option` lines). Hosts that render replies as Markdown
  collapse the indentation, so the pause and its options displayed as a single
  run-on paragraph. The ACP path now emits `format_questions_markdown()`: a
  bold pause heading, a bold question (Q1:/Q2: numbering for multiple
  questions), and options as `- **label** — description` bullets, keeping the
  `(Recommended)` → ★ convention. The CLI keeps the plain-text block.

## [2.1.4] — 2026-10-23

### Added

- **Resumable `ask_user` pauses via shared thread-state checkpointer.** The
  server now persists agent thread state (LangGraph checkpoint) to a shared
  SQLite database (WAL mode + busy_timeout) so that `ask_user` pauses survive
  pool-worker switches and server restarts. A second turn on the same session
  resumes the paused interrupt and delivers the user's input text as the
  answer — no more re-asking the same question after a worker rotation. The
  `server_checkpointer` setting (`"auto"` by default, `"off"` for legacy
  stateless behavior) controls the policy end-to-end: Settings →
  `ServerRuntimeBuilder` → `build_isolating_nano_backend` →
  `AgentAdapterBase`, which opens the checkpointer once per worker, attaches
  it at build time, and survives taint rebuilds.

### Changed

- **CI now enforces mypy type compliance.** A `make typecheck` (mypy) gate
  was added to the CI pipeline, and type annotations were fixed across the
  CLI, core, and server packages to achieve full compliance.

## [2.1.3] — 2026-10-23

### Fixed

- **CLI: every failure path now surfaces a message — no more silent exits.**
  The CLI could exit with no output (SIGTERM/SIGHUP, plugin `sys.exit`, broken
  pipes, empty answers) and destroyed the original error stack even with `-v`.
  This closes every identified gap in the error-to-output flow:

  - `RunFailed` now carries `exc_type` + traceback; `stream_query` raises
    `AgentRunError` so the CLI reports the real exception type and, with `-v`,
    the original in-run stack instead of a re-raise site.
  - SIGTERM/SIGHUP cancel the run gracefully: "interrupted by SIGTERM" with
    conventional `128+signal` exit codes (was: instant silent death).
  - Empty-answer runs warn on stderr ("agent produced no output · N tool calls
    failed · last tool error") and exit 3.
  - Partial narration is flushed to stderr before any failure/timeout/interrupt
    message — a provider drop no longer loses the whole answer.
  - `--timeout SECONDS` cancels a stuck run, reporting the last activity.
  - `FJ_LOG_FILE=<path>` keeps WARNING+ with full tracebacks in a rotating log
    for post-mortem diagnosis (incl. `logger.exception` from plugins).
  - Multi-line errors truncated to one line now hint "run with -v".
  - `BrokenPipeError`: exit 141 with a message; shutdown flush noise silenced
    via `devnull` dup2 (`fj q | head`).
  - Teardown suppresses `CancelledError` so it cannot mask the real result.
  - Server parity: pool `worker_error`, OpenAI-compatible and ACP failures
    populate/render `exc_type` + traceback (ACP shows "Error: <Type>: <msg>").
  - Minor: thread-snapshot check failures are logged; config-load errors
    honor `-v` with a traceback; plugin `sys.exit(0)` still fails loudly.

### Changed

- **ArcBox tool sandbox: guest network is now off by default**
  (`sandbox.network` defaults to `false`, was `true`). With `true` the guest is
  NAT'ed through the ArcBox host and the daemon only knows ENABLED|NONE, so
  everything the host can route to — internal network and corporate VPN
  included — was reachable from agent shell commands. With `false` the guest
  boots without a network device (no route, no DNS): shell/code execution can
  reach neither the public internet nor internal services. Web search/crawl is
  unaffected — `web_search`/`fetch_url` are host-placement tools and never run
  in the guest. Opt back in per deployment (`sandbox.network: true` in the
  nano.yml) when the guest really needs egress.

## [2.1.2] — 2026-10-21

### Changed

- **Bump `soothe` to 1.2.1.** The runtime dependency floor moves from
  `>=1.2.0` to `>=1.2.1,<2.0.0` to track the upstream fix release. No flowjet
  API or behavior changes; the locked dependency set is otherwise unchanged.

## [2.1.1] — 2026-10-21

### Fixed

- **ACP clarification turns no longer end empty.** When the agent paused with
  `ask_user` questions over ACP, the questions were only surfaced as an
  intermediate agent thought — but hosts accumulate message chunks as the
  turn's reply, so a clarification turn ended with no content at all. The ACP
  agent now also emits the questions block as a message chunk (rendered via
  `format_questions_block`), so the user sees the questions in the host's reply
  surface and answers there.

- **`format_questions_block` supports non-CLI hosts.** The resume footer
  ("Resume with: fjf -t <thread> <your answer>") was hardcoded for the CLI.
  ACP and other non-CLI hosts now pass `resume_hint=""` to omit the
  CLI-specific footer; the user answers in the host's own input surface.
  The CLI path is unchanged (footer still shown by default).

- **Drop the direct `arcbox` dependency from the `server` extra.** The arcbox
  SDK ships transitively via soothe-nano (a dependency of soothe), so the
  explicit `arcbox>=0.1.0` pin in `pyproject.toml` was redundant and could
  drift out of sync. The sandbox import error message is updated to point at
  the transitive path instead of instructing `pip install arcbox`.

## [2.1.0] — 2026-10-18

### Changed

- **`flowjet.core` layout restructure.** The runtime-protocol package is
  regrouped by responsibility; behavior is unchanged:
  - `core/backends/` → **`core/runtime/`** (the `RuntimeBackend`
    implementations: `direct` / `isolation` / `fake`); `runtime/isolation`
    keeps its module structure.
  - `core/backends/tool_sandbox.py` → **`core/sandbox/`** split into
    `settings` (`ToolSandboxSettings` + `SandboxSettingsLoader`),
    `arbox` (`ArcBoxToolSandboxManager` + the new `WorkspaceStager` host↔guest
    transfer class) and `resolver` (`SandboxAwareWorkspaceResolver`).
  - `core/bootstrap.py` → **`core/agent/`** split into `config`
    (`FlowJetConfigLoader`), `skills` (`BuiltinSkills`), `workspace`
    (`Workspaces` / `Checkpointers`), `factory` (`AgentFactory`,
    `ModeRoutedSootheAgent`) and `wiring` (`ServerRuntimeBuilder`, absorbing
    the server-assembly helpers from `server/http/app.py`).
  - `core/tool_stream.py` + `core/tool_results.py` → **`core/streaming/`**
    (`ToolCallArgAccumulator`, `PartialArgsParser`, `ToolResultInspector`) plus
    `streaming/presentation.py` (`ToolCallSummarizer`,
    `StepProgressFormatter`, `OutputTextChunker`, `AiTextExtractor` — moved out
    of the stream mapper).
  - `core/backend.py` → **`core/backend_config.py`** (backend *selection*; the
    implementations live in `core/runtime/`).
  - The duplicated nano/soothe adapter lifecycle and the two identical
    isolating-backend factories are collapsed into
    `core/bridges/base.py` (`AgentAdapterBase`, `create_server_agent_instance`,
    `IsolatingBackendBuilder`); `NanoAgentAdapter` / `SootheAgentAdapter` are
    now thin subclasses. `InteractionMode.from_metadata()` is the single
    request-mode parser (previously duplicated in the stream mapper and the
    server mode gate); `mapping.extract_ask_user_interrupts` is public API.
  - Standalone helper functions across these modules were regrouped into
    classes; import paths for `FlowJetConfigLoader.load`,
    `SandboxSettingsLoader.load`, `ToolResultInspector.*`,
    `PartialArgsParser.parse` and `InteractionMode.from_metadata` replace the
    old free functions. `core/__init__.py` now also exports `Backend` and
    `resolve_backend`.

### Added

- **ArcBox tool sandbox (RFC-005).** Tool calls — shell commands and workspace
  file operations — can now run inside a per-workspace ArcBox Linux microVM
  via soothe-nano 2.0's `ArcBoxBackend`. Enabled by a `sandbox:` section in
  the nano.yml (`enabled`, `image`, `vcpus`, `mem_mib`, `network`,
  `workspace_root`, `default_timeout`, `idle_timeout_seconds`,
  `max_sandboxes`); the section's placement-policy keys (`on_deny`,
  `placement_overrides`, `max_shuttle_bytes`) pass through to soothe-nano
  unchanged. The AgentRuntime isolation is unchanged (thread pool); the
  agent loop and credentials stay on the host, only the execution surface
  moves into the guest. The host workspace stays the integration point:
  `SandboxAwareWorkspaceResolver` stages host→guest at session open and
  guest→host at close (before any workspace-sync checkpoint), skipping
  unchanged files via a size/mtime manifest. See
  [RFC-005](docs/specs/RFC-005-arcbox-tool-sandbox.md).

- **Dynamic `max_sandboxes` compute-sizing.** `sandbox.max_sandboxes` now
  accepts `None` (in addition to an explicit int). When set to `None`, the
  cap is computed at startup from the host's logical CPU count: 70% of CPU
  is treated as usable, divided by the per-sandbox `vcpus`, with a hard
  minimum of 8 (so small hosts and CI runners stay usable). An explicit
  int still pins the cap (back-compat). The startup log now reports whether
  the cap was computed or explicit.

- **`max_sandboxes: 0` (unlimited) and env overrides.** Setting
  `sandbox.max_sandboxes: 0` disables LRU eviction entirely — all idle
  sandboxes stay alive until the idle reaper or shutdown reclaims them.
  Two env vars allow operator overrides without editing nano.yml:
  `FLOWJET_SANDBOX_MAX` (int; `0` = unlimited) pins the cap;
  `FLOWJET_SANDBOX_MAX_PERCENT` (1–100, default 70) tunes the CPU usable
  fraction when `max_sandboxes` is `None`. The `max_sandboxes` field is now
  also declared on soothe-nano's `SandboxConfig` (`int | None`, `ge=0`,
  default `8`) as the single source of truth for the cap, so the operator
  can set it in the `sandbox:` section without a flowjet-specific override.

### Removed

- **Whole-worker arcbox isolation (`FLOWJET_ISOLATION_MODE=arcbox`).** The
  microVM-per-workspace *worker* mode (arcbox_vm_pool / arcbox_worker /
  arcbox_protocol) is deleted — superseded by the ArcBox tool sandbox above.
  `FLOWJET_ISOLATION_MODE`, all `FLOWJET_ARCBOX_*` settings, and the
  `validate_isolation_compatibility` startup guard are gone; the thread pool
  is the only isolation pool. The `arcbox` SDK dependency stays (used by the
  tool sandbox).

## [2.0.11] — 2026-10-15

### Changed

- **Bypass mode is now the CLI default.** The `-b`/`--bypass` flag was removed;
  bypass mode (skip all security enforcement) is now the default interaction
  mode for the CLI surface, since `fj` runs on the user's own machine. Use
  `-a`/`--ask` for read-only Q&A with guardrails. The `bypass_mode` parameter
  was removed from `build_agent`; the server surface still rejects `bypass`
  via `require_mode()`. Docs (`server.md`, `upgrade.md`, `modes.py`) updated.

## [2.0.10] — 2026-10-14

### Changed

- **Bump soothe and soothe-nano to the latest.** `soothe` `1.0.22 → 1.1.0`
  and `soothe-nano` `1.3.3 → 1.4.2`. The version caps were lifted:
  `soothe>=1.1.0,<2.0.0` and `soothe-nano>=1.4.2,<1.5.0`. The standalone
  `soothe-sdk` package was removed in the new release; its modules merged
  into `soothe` and `soothe-nano`. All FlowJet import paths were migrated:
  `soothe_sdk.utils.serde` → `soothe_nano.utils.serde`,
  `soothe_sdk.utils.formatting` → `soothe_nano.utils.formatting`,
  `soothe_sdk.tools.metadata` → `soothe_nano.tools.metadata`, and
  `soothe_sdk.display.message_processing` → `soothe.display.message_processing`.
  The graceful try/except fallbacks in `progress.py` and `tool_stream.py`
  now resolve to the real implementations instead of falling through to
  fallbacks.

## [2.0.9] — 2026-09-24

### Fixed

- **Suppress noisy third-party warnings at startup.** `requests` emits
  `RequestsDependencyWarning` when the installed `urllib3` / `chardet` /
  `charset_normalizer` versions fall outside its supported range, and
  `soothe`'s `TypeSafeClassifier` triggers LangChain's `LangChainBetaWarning`.
  Both are version-mismatch or beta-API notices the user cannot act on, so
  they are now silenced at the earliest point of each entry point. A new
  `core/_warnings.py` module exposes `suppress_known_warnings()`, called from
  both the CLI (`cli.py`) and server (`server/__main__.py`) `main()` before
  the heavy agent stack is imported.

## [2.0.8] — 2026-09-24

### Added

- **`ask_user` interrupt/resume in the CLI.** The nano runtime now surfaces
  soothe's `ask_user` interrupt so the agent can pause mid-run to ask
  structured questions and resume on a follow-up invocation. `RunRequest`
  gains `resume_value`, which the direct and nano backends forward into
  LangGraph's `Command(resume=...)` instead of starting a new turn.
  `mapping.py` extracts the `ask_user` questions and interrupt ids from a
  `__interrupt__` payload and carries them on `InterruptWaiting`; `stream.py`
  renders the questions block (options, recommended marker, resume hint) and
  returns an `INTERRUPTED` sentinel instead of "Done" when the graph pauses.
  `cli.py` detects a pending `ask_user` interrupt on the thread snapshot,
  prints the questions, and feeds the user's query text as the resume answer
  — so `fjf -t <thread> <answer>` continues the paused run.

## [2.0.7] — 2026-09-23

### Changed

- **Bump soothe-nano to the latest.** `soothe-nano` `1.3.0 → 1.3.1`. The
  `>=1.3.0,<1.4.0` spec already permitted the upgrade, so no version cap
  change was needed; the lock is re-resolved. All FlowJet import paths into
  soothe/soothe-nano are unchanged and continue to resolve.

## [2.0.6] — 2026-09-21

### Changed

- **Bump soothe runtime to the latest.** `soothe` `1.0.12 → 1.0.14` and
  `soothe-nano` `1.2.28 → 1.3.0`. The `<1.3.0` cap on `soothe-nano` was lifted
  to `<1.4.0` because `soothe 1.0.14` now requires `soothe-nano>=1.3.0`. The
  upgrade adds one transitive dependency, `langchain-typesafe`. All FlowJet
  import paths into soothe/soothe-nano (`SootheConfig`, `create_nano_agent`,
  `create_dual_mode_nano_agent`, `create_soothe_agent`, `resolve_checkpointer`,
  `register_builtin_skill_root`, `FrameworkFilesystem`, `diagnose`, etc.) are
  unchanged and continue to resolve.

## [2.0.5] — 2026-09-20

### Changed

- **Config moved off `~/.soothe` — `FLOWJET_HOME` is now the authority.**
  The config file resolves to `$FLOWJET_HOME/config/nano.yml` (default
  `~/.flowjet/config/nano.yml`) instead of `$SOOTHE_HOME/config/nano.yml`, so an
  exported `SOOTHE_HOME` can no longer drag flowjet back onto `~/.soothe`.
  `SOOTHE_HOME` itself is left untouched: CLI data (thread pins, locks,
  completion history), logs, agents, plugins and the sqlite databases still live
  there. Upgrades keep working — an existing `~/.soothe/config/nano.yml` (plus a
  sibling `soothe.yml`) is copied into `$FLOWJET_HOME/config/` **once**, on first
  run, and the originals are left in place, so the move is reversible.
- **`fj setup` no longer aborts when the LLM endpoint is unreachable.** A failed
  or empty `/models` probe (connection refused, HTTP error, unresolved
  `${ENV_VAR}`) now prints a `warning:` and falls through to manual model entry
  — offering the models already saved for the selected provider, or accepting a
  typed model id. The provider and router profile are still written, so a config
  can be initialised before the model server is running; the run ends with a note
  to re-check via `fj doctor`.

## [2.0.4] — 2026-09-19

### Fixed

- **`fj -V` is instant (1.78s → 0.06s).** It paid the full `soothe_nano` +
  `flowjet.core.bootstrap` import cost on every invocation just to print a
  version string. The stdlib-only logging helpers moved out of `agent.py` into
  `cli.py`, `main()` parses args before setting up logging so `-V`/`-h` exit
  first, and the `-c/--config` help text now resolves lazily.
  (`agent.py` keeps thin delegation wrappers, so existing imports and
  monkeypatching are unaffected.)

## [2.0.3] — 2026-09-18

### Added

- **Plan-step and middleware-phase progress in the CLI.** The nano bridge now
  maps the host (soothe) loop's todo list and middleware phase updates into
  step/tool progress events, so the terminal shows `Step 2/3 · Create a2.txt`
  instead of a bare `Working` line. Late-parsing tool args refresh the status
  line once, and `write_todos` bookkeeping is suppressed as a tool call (it
  already drives the step line).

## [2.0.2] — 2026-09-18

### Added

- **Duo backends — `soothe` or `soothe-nano`.** `FLOWJET_BACKEND` (CLI, default
  `soothe`) and `FLOWJET_SERVER_BACKEND` (HTTP/ACP, default `nano`) select which
  runtime builds the agent. `soothe` is a host layer over soothe-nano, so the
  engine stays installed either way; the two surfaces switch independently
  because the server needs a dual-mode agent (AGENT + ASK graphs per request),
  which soothe does not expose — with `FLOWJET_SERVER_BACKEND=soothe` the server
  builds one host agent per mode and routes on `interaction_mode`.

### Changed

- The CLI now builds its agent through the `soothe` host runtime by default
  (host middleware, `request_plan_mode` / `ask_user` tools, configurable
  persona). Set `FLOWJET_BACKEND=nano` for the previous behaviour.

## [2.0.1] — 2026-09-17

### Added

- **ACP sessions run in the client's directory.** `FlowJetAcpAgent` now records
  the `cwd` from `session/new`, `session/load`, `session/resume` and
  `session/fork` and forwards it as the run's `metadata.workspace`. Previously
  the client `cwd` was accepted and discarded, so every ACP session ran in a
  hashed workspace under `FLOWJET_HOME`.

### Changed

- **The assistant identifies as FlowJet, not Soothe.** soothe-nano prepends its
  own `<ASSISTANT_IDENTITY>` block — "a helpful AI assistant" named `Soothe` —
  to every system prompt tier, and only parameterises it by `agent.name`.
  `flowjet.core.identity` now installs a FlowJet template (coding agent, creator
  line, and an explicit "never identify as Soothe / soothe-nano / Claude /
  ChatGPT / Gemini / Anthropic / OpenAI / Google" rule) and `apply_profile`
  defaults `agent.name` to `FlowJet` on both the CLI and server surfaces. An
  explicit `agent.name` or `agent.system_prompt` in `nano.yml` still wins.
- **Workspace resolution is caller-driven by default.**
  `FLOWJET_ALLOW_EXTERNAL_WORKSPACE` now defaults to `true`, so a workspace
  outside `FLOWJET_HOME` is honoured rather than rejected. This is not a
  sandbox escape — tools remain confined to whichever workspace is selected
  (`allow_paths_outside_workspace` is still `false`); the boundary moves to the
  caller's directory instead of disappearing. Set
  `FLOWJET_ALLOW_EXTERNAL_WORKSPACE=false` to restore forced hashed
  per-session workspaces.

## [2.0.0] — 2026-09-17 — unified CLI + server

**Breaking.** `flowjet-server` is merged into this repository and ships as one
distribution, `flowjet`. See [RFC-004](docs/specs/RFC-004-unified-package.md).

### Added

- **One distribution, two surfaces.** `flowjet.core` (shared runtime),
  `flowjet.cli` (was `fj_ai`) and `flowjet.server` (was `flowjet_server`).
- **`fj serve`** — run the HTTP service from the CLI (alias of `flowjet-server`,
  flags: `--host`, `-p/--port`, `--api-key`, `--nano-config`).
- **Optional `[server]` extra.** `pip install flowjet` pulls one runtime
  dependency (soothe-nano); FastAPI/uvicorn/ACP/pydantic-settings are opt-in
  and lazily imported so `fj` never loads them.
- **`DirectRuntimeBackend`** — the CLI now runs on the same `RuntimeBackend`
  contract and `RuntimeEvent` stream as SSE and ACP.
- **`Narration` event** — pre-tool-call text is available to the terminal for
  live preview while remaining invisible to protocol clients.
- **`SurfaceProfile`** (`flowjet.core.modes`) — the CLI's permissive workspace
  and the server's workspace confinement are now explicit, per-surface
  invariants; `bypass` mode is rejected on the server surface.
- Auth now uses `hmac.compare_digest` instead of `!=`.

### Changed

- Distribution renamed `flowjet-agent` → `flowjet`; version single-sourced from
  `flowjet.__version__` (the server no longer hard-codes `0.2.0`).
- Builtin skills moved to `flowjet/builtin_skills` and are registered for both
  surfaces.
- `langchain-core` is now an explicit `server` dependency (it was imported but
  undeclared).

### Removed

- The `fj_ai` and `flowjet_server` import namespaces. No compatibility shims —
  see [docs/upgrade.md](docs/upgrade.md) for the migration table.

## [0.2.0] — 2026-09-16

### Added

- **ACP (Agent Client Protocol) support.** flowjet-server now exposes an ACP
  `Agent` over a WebSocket endpoint at `/acp`. Other ACP clients (Zed, custom
  integrations) connect via `ws://host:port/acp` and drive the same
  nano-backed `RuntimeBackend` used by the OpenAI-compatible Responses API.
  The implementation bridges `RuntimeEvent` streams (RunStarted, Progress,
  OutputTextDelta, ToolStarted/Completed, RunCompleted) to ACP
  `session/update` notifications (agent_message_chunk, agent_thought_chunk,
  tool_call/tool_call_update) and returns `PromptResponse` with
  `stopReason=end_turn` + token usage. Initialize, session/new,
  session/load, session/list, session/prompt, session/cancel, and
  session/close are all supported.

### Changed

- **Bumped `soothe-nano` dependency** from `>=1.2.23,<2.0.0` to
  `>=1.2.28,<2.0.0` (latest release).
- **Added `agent-client-protocol[http]`** as a runtime dependency
  (`>=0.12.1,<1.0.0`), providing the ACP SDK server + WebSocket transport.

## [0.1.1] — 2026-09-05

### Fixed

- **litellm corrupted-install fix.** The previous image (v0.1.0) shipped a
  broken `litellm` 1.99.0 wheel: `litellm/__init__.py` was listed in the
  dist-info RECORD but missing from disk, so Python treated the package as an
  empty namespace package and every `/v1/responses` call failed with
  `module 'litellm' has no attribute 'acompletion'`. Reinstalling litellm with
  `uv pip install --force-reinstall litellm==1.99.0` restores
  `litellm/__init__.py` and `acompletion` becomes available again. The Docker
  image now rebuilds the venv cleanly so the fix is baked into the published
  image.

### Verified

Full E2E suite (`examples/e2e_http_api.py`) passes against the live server:

| Endpoint | Method | Result |
|---|---|---|
| `/health` | GET | ✅ `{"status":"ok",...}` |
| `/v1/models` | GET | ✅ returns `default` model |
| `/v1/responses` (stream=false) | POST | ✅ status `completed`, real LLM text |
| `/v1/responses/{id}` | GET | ✅ retrieve returns stored response |
| `/v1/responses/{id}` | DELETE | ✅ `deleted:true`, subsequent GET → 404 |
| `/v1/responses` (SSE, report) | POST | ✅ `response.created` → `output_text.delta` → `response.completed` |
| `/v1/responses` (SSE, progress) | POST | ✅ includes `response.flowjet.progress` stages |
| `/v1/responses` (SSE, developer) | POST | ✅ completes; no tool args leaked to wire |
| unknown model | POST | ✅ HTTP 404 `model_not_found` |
| missing id | GET | ✅ HTTP 404 `response_not_found` |

## [0.1.0] — initial release

OpenAI Responses–compatible HTTP service backed by soothe-nano (≥1.2.23).
Includes ask/agent interaction modes, three SSE projection modes
(report / progress / developer), thread-pool isolation (RFC-002), production
isolation suite (RFC-003), and a self-contained Docker deploy stack
(PostgreSQL + pgvector + flowjet-server).

[0.1.1]: https://github.com/caesar0301/flowjet-server/releases/tag/v0.1.1
[0.1.0]: https://github.com/caesar0301/flowjet-server/releases/tag/v0.1.0
