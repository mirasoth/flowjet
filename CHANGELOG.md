# Changelog

All notable changes to **flowjet** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> History from 0.1.0–0.2.0 below was released as the separate `flowjet-server`
> distribution, now merged into `flowjet`. See [docs/upgrade.md](docs/upgrade.md).

## [Unreleased]

## [2.3.7] — 2026-11-29

### Fixed

- **Loop crash on worker resume** (`'dict' object has no attribute 'parent_step_id'` in RECONCILE): decompose proposals now round-trip through the checkpointer as model objects instead of plain dicts, so a park/resume no longer crashes RECONCILE.

### Changed

- Raise the `soothe` floor to `>= 1.3.12`: picks up the loop-crash fix above, plus TUI improvements — live timers use compact clock format (`11:10` instead of `11m 10s`; `01:11:01` for hours) and token stats are split (thinking row shows per-goal consumption, status bar always shows accumulated loop total with semantic suffixes like `3.8M` instead of `3814.9K`).


## [2.3.6] — 2026-11-27

### Added
- **Wire image attachments land in the turn workspace (IG-CORE-012; requires soothe >= 1.3.9 with `soothe.workspace.attachments`).** The OpenAI-compatible entry points (Responses `input` blocks, Chat Completions `messages`) and the ACP prompt path no longer silently drop image blocks: inline data-URL / ACP image blocks are validated (MIME allowlist + aliases, base64, 20 MiB / 8-image limits) and carried on `RunRequest.attachments`. After the workspace materializes at turn open, the isolating backend prunes stale attachments (age-based TTL, shared 7-day default) and lands the rest under `.soothe/cache/attachments/<sha256[:16]>.<ext>` (content-addressed, idempotent — engine-local cache, excluded from workspace sync) and appends the landed paths plus a vision-tool hint to the input text; the vision tools execute host-side and read the real paths, so the flow works in every sandbox mode. Landing failures degrade to a text-only turn. Remote (non-data-URL) image references are skipped.

### Fixed
- Sandbox push/pull reserved-directory parity: the private `.soothe` namespace is skipped in both directions — previously the pull side did not skip it, so a guest-written `.soothe/**` leaked back into the host workspace. Push and pull skip sets are now symmetric.

### Changed
- Raise the `soothe` floor to `>= 1.3.10` (soothe-nano 2.1.2): `analyze_image` / `extract_text_from_image` get a 180 s per-tool timeout (both wrap a full multimodal model call that routinely exceeds the 60 s default on large images) and the loop's step-close assessment is bounded by a 120 s deadline.

## [2.3.5] — 2026-11-26

### Fixed

- **Worker release regression in the persisted-turn path.** Holding the terminal event until the workspace commit (IG-CORE-011) broke out of the pool's event generator before it consumed the worker's `done` control frame, so `_release_worker` never ran: the worker stayed busy, `requests_completed` stayed at 0, and subsequent requests on a single-worker pool could stall. The backend now drains the pool generator to completion while holding the terminal event, then commits and surfaces the outcome. Regression test in `tests/integration/http/test_production_isolation_http.py`.

### Changed

- **Workspace sync is single-root and single-writer (IG-CORE-011; requires the unreleased soothe with the single-root `TurnScopedWorkspaces`).** `workspace_sync_source` now points at the workspaces root itself (e.g. `s3://bucket/workspaces`): each run's backend is rooted at `<source>/<run_id>` and serves both the plain content tree (authoritative file store) and the engine-private manifest (`<run_id>/.workspace/manifest.json`). The `{workspace}` template setting `workspace_content_source` is **removed** — `FLOWJET_WORKSPACE_CONTENT_SOURCE` and `FLOWJET_WORKSPACE_SYNC_SOURCE` collapse into one URI (drop the former when upgrading; the source now points at `workspaces/`, not `system/engine`). Hosts must serialize turns per workspace (agentspace enforces this at its prompt gate).
- **Turn completion = persisted, visibly.** `close_session` returns the engine's `TurnCommit` (persisted/version/error); the runtime backend commits **before** surfacing the terminal event and ends a successful run whose commit failed as `RunFailed(code="workspace_persist_failed")` instead of a silent log line. A failed commit keeps the workspace open so the dirty set survives to the next turn.
- **Workspace sync is content-authoritative (IG-CORE-010 Stage B; requires the unreleased soothe with `TurnScopedWorkspaces` over the content-authoritative engine).** The plain content tree (`workspace_content_source`, a URI template with a `{workspace}` placeholder) is the authoritative file store: materials materialize from it at session open and dirty writes/deletions mirror back at checkpoint, with the sync manifest as the atomic commit point (version+1, optimistic concurrency). The CAS blob double-write, the per-run SQLite state store, and the background uploader are gone. The resolver still only maps the ACP cwd to a run id and builds the sync backends; the per-turn lifecycle (manifest load, content materialization, reconcile gating, last-turn-out close) is owned by the soothe facade.
- **`FLOWJET_WORKSPACE_CAS_ROOT` setting removed.** The CAS root had a single consumer (the deleted state-store staging path); `workspace_cas_root` is gone from `Settings`, `ServerRuntimeBuilder.build`/`workspace_resolver`, and the resolver constructor. Remove the env var from deployments when upgrading.

## [2.3.4] — 2026-11-25

### Changed

- Bump the Soothe floor to `soothe>=1.3.7`: brings the approval dock (`Ctrl+R`), manual clarification mode with approve-and-remember grants, per-tool multi-tool approval gates, `ask_user` closure hardening (every ask terminates in an answer, an honest unanswered sentinel, or a park), execution token-stat accuracy (`token_usage_source` on wire events, completion synthesis in goal snapshots, estimated totals marked in the TUI), and TUI thinking/todo/files pane fixes (non-italic reasoning, no overflow cap on todo panes, leading `+N more` overflow line).

## [2.3.3] — 2026-11-24

### Changed

- Bump the Soothe floor to `soothe>=1.3.6` (which pulls `soothe-nano>=2.0.13`): brings automatic same-thread step retry with re-plan continuation, the `soothe[observability]` extra, and the daemon hardening release (checkpoint/heartbeat/pool fixes, workspace-marker ownership sidecar so `drain_goal_runtime` never signals a forged or recycled PID).

## [2.3.2] — 2026-11-24

### Fixed

- **Shell tools broke on the Landlock tier**: require `soothe>=1.3.5` (which pulls `soothe-nano>=2.0.12`) so `run_command`/`run_python` capture-offload redirects — and the interpreter venv prefix read — no longer fail before execution on the degraded Linux sandbox tier.

## [2.3.1] — 2026-11-24

### Fixed

- **Bake `bubblewrap` into the server image** so the `os_sandbox` Linux tier selects bwrap+seccomp instead of falling back to degraded Landlock. The Debian runtime installs `bubblewrap` alongside chromium, and the prebuilt base image was refreshed so release builds inherit `/usr/bin/bwrap` without an initContainer or PATH override.

## [2.3.0] — 2026-11-24

### Added

- **OS-primitive sandbox backend (`os_sandbox`).** Tool calls can now run inside an OS-level sandbox — Seatbelt on macOS, bubblewrap+seccomp on Linux — giving real isolation without hardware virtualization or a guest image. `os_sandbox` uses identity path mapping (guest paths are host paths), so no host↔guest workspace staging is needed; the agent operates on the real workspace directory, confined by the OS boundary. A new `sandbox_mode` setting (`auto` / `os_sandbox` / `off`, default `auto`) controls the default: when no explicit `sandbox:` section is present in the nano.yml, `auto` enables `os_sandbox` with production defaults; `off` disables the sandbox entirely. An explicit `sandbox:` section always wins. Override via `--sandbox-mode` on `fj serve` or the `FLOWJET_SANDBOX_MODE` env var. New `config/nano-os-sandbox.yml` ships a ready reference config.

### Changed

- **Multi-backend sandbox config format (breaking).** The flat `sandbox.image` / `vcpus` / `mem_mib` / `network` / `workspace_root` / `default_timeout` / `connect_timeout` / `idle_timeout_seconds` fields are no longer supported. Use the discriminated `sandbox.backend.type` + `sandbox.backend.<type>.*` format instead (e.g. `type: arcbox` + `arcbox: { image, vcpus, mem_mib, … }`, or `type: os_sandbox` + `os_sandbox: { … }`). Pool-management keys (`max_sandboxes`, `min_free_bytes`, `idle_timeout_seconds`) stay at the `sandbox:` top level; backend-specific lifecycle fields move under `sandbox.backend.<type>` and are passed verbatim to nano's `create_sandbox_backend` factory. `config/nano-sandbox-soothe.yml` was renamed to `config/nano-arcbox-sandbox.yml` and migrated to the new format.

- **Sandbox lifecycle is now fully backend-agnostic.** flowjet no longer imports or calls the arcbox SDK directly — the create/connect/kill lifecycle is owned by soothe-nano's `create_sandbox_backend()` factory, which flowjet calls per workspace. Removed ~1060 lines of arcbox-specific coupling (`_import_arcbox`, `_new_client`, `_create`, `_kill_lease`, pad reclamation, orphan scanning/adoption, heartbeat/set_lifecycle, and the `reserved_pad_path` / `recover_orphans` / `orphan_timeout_seconds` / `owner` settings). `ArcBoxToolSandboxManager` renamed to `ToolSandboxManager`. Crash cleanup is now handled by nano's `_SandboxManager` (`idle_timeout` + `on_idle="kill"` at the daemon level). flowjet keeps its pool-management responsibilities: per-workspace backend pool with LRU eviction, idle reaper, host↔guest workspace staging, and the disk watermark guard.

- **`soothe` floor bumped to `>=1.3.4`** (`uv.lock` refreshed; `soothe-nano` → 2.0.11). Picks up the latest soothe 1.3.4 runtime and the nano multi-backend sandbox factory; no other flowjet-facing API changes.

## [2.2.5] — 2026-11-19

### Fixed

- **`fjf` no longer reprints historical questions before a fresh one.** With consecutive `ask_user` turns, resuming a paused thread used to echo the checkpoint's pending (already answered) question panel before `stream_query` rendered the new question — so the previous questions stacked above the latest one. The resume path now only sets `resume_value` and leaves question rendering to `stream_query`, which renders exactly one panel using the newest question set even when a run emits several `__interrupt__` chunks. Regression tests in `tests/unit/test_cli.py`, `tests/unit/test_stream.py` and `tests/integration/test_cli_stream_progress.py`.

## [2.2.4] — 2026-11-17

### Changed

- **The live dashboard panel title is now the liveness status display.** The `FlowJet Agent` label is gone; the status badge (`● LIVE` / `✓ DONE` / `✗ FAILED` / `⏸ PAUSED`) and the step/elapsed/tokens/last-updated strip now share the title border on one line, with the spinner still animating while the run is live. The body starts directly with the current action, so the two former heading/meta rows no longer consume vertical space. Narrow terminals progressively compact the strip (tighter separators, then values only, then an ellipsis). Non-TTY output is unchanged.

- **The dashboard's narration preview now shares the current-action line.** The separate `Answer · …` row (and its blank spacer) is gone; intermediate AI narration is appended inline after ` · ` on the first body row, styled dim green and width-bounded together with the action so narrow terminals still stay on one line. The liveness title remains directly above. Non-TTY output is unchanged.

- **`soothe` floor bumped to `>=1.3.3`** (`uv.lock` refreshed). Picks up the latest soothe 1.3.3 runtime; no flowjet-facing API changes.

## [2.2.3] — 2026-11-16

### Fixed

- **Friendlier CLI errors.** Raw provider/library exceptions often chain the same type name several times (e.g. `InternalServerError: litellm.InternalServerError: InternalServerError: OpenAIException - Missing credentials…`). `format_cli_error` now strips those redundant type-name prefixes and maps known errors (missing credentials, auth, rate limit, context-length, connection) to a one-line summary plus an actionable hint on a second line (`→ Set OPENAI_API_KEY … / Run flowjet setup`). Unknown errors keep their type and message, just without the noise. Regression tests in `tests/unit/test_errors.py`.

### Changed

- **`soothe` floor bumped to `>=1.3.2`** (`uv.lock` refreshed). Picks up the latest soothe 1.3.2 runtime; no flowjet-facing API changes.

- **Removed legacy soothe config migration.** `~/.soothe/config` is no longer auto-copied into the flowjet home on first use — the flowjet home (`~/.flowjet/config/nano.yml`) is the single source of truth. `flowjet.home.ensure_flowjet_config` / `migrate_legacy_config` and their call sites in `cli/setup_cmd.py`, `core/agent/config.py` and `server/__main__.py` are gone; `tests/unit/test_home.py` trimmed accordingly. Existing copied configs are left in place.

- **Slimmer CLI help.** `_cli_description` / `_cli_epilog` and the per-flag `help` strings are condensed to the essentials; the `doctor-fix` command and verbose notes were pruned from the epilog (the command still works). Default new-provider name in `fj setup` is `default` (was `flowjet-default`).

## [2.2.2] — 2026-11-13

### Changed

- **Dashboard snapshot is now disabled by default.** The live progress panel is erased when the run finishes, leaving only the final answer. Set `FJ_SNAPSHOT=1` (or `true`/`yes`) to keep the DONE / FAILED / PAUSED snapshot visible above the answer, as in previous versions.

- **`✓ Done` status footer is now suppressed by default.** The run ends with just the final answer. Pass `-v` (or set `FJ_LOG_LEVEL=debug`) to surface the `✓ Done · <duration> · <tokens> · <thread_id>` summary footer.

## [2.2.1] — 2026-11-11

### Changed

- **`soothe` floor bumped to `>=1.3.1`** (`uv.lock` refreshed). Picks up the latest soothe 1.3.1 runtime — Proactive Coverage Evaluation (PCE) and the TUI stream-cancel fix; no flowjet-facing API changes.

## [2.2.0] — 2026-11-10

### Changed

- **`soothe` floor bumped to `>=1.3.0`** (`uv.lock` refreshed). Picks up the latest soothe 1.3.0 runtime; no flowjet-facing API changes.

## [2.1.16] — 2026-11-09

### Changed

- **`soothe` floor bumped to `>=1.2.10`** (`uv.lock` refreshed). Picks up the latest soothe runtime; no flowjet-facing API changes.

## [2.1.15] — 2026-11-09

### Fixed

- **Activity lists completed tool calls only; the in-flight tool call has its own line.** `Activity` now renders only rows with a completion marker (`✓` / `✗`). Reasoning stretches, phase mirrors and in-flight / partial tool calls no longer get a row there (reasoning is still reduced into the dashboard state for ACP parity and stays on the Answer line). The line directly below `Elapsed … · Tokens … · Updated …` is reserved for the tool call currently being executed: partial `soothe.tool.started` chunks grow that one line in place even before the arguments have fully arrived, `ToolStarted` replaces it with the complete call, and the completion clears it while appending a single `✓` row. Completed rows and reasoning rows now have independent rolling caps, so a burst of narration cannot evict a `✓` row. The heading reads `Activity (N)` with the cumulative number of completed tool calls in the run, even though the panel shows only the most recent rows. Non-TTY output is unchanged byte-for-byte.

## [2.1.14] — 2026-11-07

### Fixed

- **In-flight tool activity no longer duplicates per partial arg chunk.** As tool arguments streamed in (e.g. a growing `run_command sleep 180 && …` command), each partial refresh appended a new `· run_command …` row to the dashboard Activity tail instead of updating the single in-flight row in place. Partial `soothe.tool.started` progress events now route to `update_tool_activity()`, which grows the existing row's label in place; the completed event marks that same row `✓` (no duplicate `·` row above the `✓`).
- **Brief in-flight tool rows are dropped from the Activity tail.** Quick tool calls (read_file, grep, ls, …) previously left a `·` stub visible between completed rows. Bare in-flight event rows (`·`) that have been visible for under 5 seconds are now filtered from the rendered history; long-running commands (sleep 180, slow builds) cross the threshold and stay visible. Same-tool completions fold into the in-flight row in place rather than leaving a stale `·` beside the `✓`.

### Changed

- **`soothe` floor bumped to `>=1.2.9`** (`uv.lock` refreshed).

## [2.1.13] — 2026-11-06

### Added

- **Token totals in the CLI footer.** `✓ Done` now reports cumulative usage, aggregated from provider usage deltas, reconciled with soothe's turn-end total and estimated when a provider reports none. The same totals reach the ACP and OpenAI-compat projections via `RunCompleted.usage`.

### Changed

- **Multi-line live progress dashboard replaces the single-line status line.** On a TTY, `fj`/`fjf` redraw one fixed region in place (Rich `Live`): status badge, a one-line step/elapsed/tokens/updated strip, the current action, an activity history (tool calls plus the agent's reasoning between them) and a live answer preview. DONE / FAILED / PAUSED snapshots stay above the answer or the questions; verbose and log lines print outside the live region. Tool rows in `Activity` show `<tool> <args>` with no repeated status prefix. Non-TTY output is unchanged byte-for-byte.
- **Partitioned `ask_user` questions on TTY.** Numbered `Q1:`/`Q2:` sections, a `★` recommended marker, wrapped descriptions and a standalone resume hint. The in-run pause and `fjf` resume share one renderer; non-TTY keeps the historical plain-text block. Answering stays manual via `fjf -t … <answer>`.
- **`soothe` floor bumped to `>=1.2.8`** for improved token accounting (`uv.lock` refreshed).

## [2.1.12] — 2026-10-31

### Fixed

- **Defensive `flowjet.cli.render` imports.** The lazy `from flowjet.cli.render import …` calls in `cli/stream.py` (`AnswerWriter.finish`) and `cli/threads.py` (`write_thread_list`) raised `ModuleNotFoundError: No module named 'flowjet.cli.render'` on stale or partial installs (e.g. wheels predating 2.1.10 that don't ship `render.py`), killing the run after output was already buffered. Both imports are now wrapped in `try/except ImportError` and degrade to the existing plain-text path — the documented contract that every rendering helper falls back to plain text. Regression tests in `tests/unit/test_render.py` block the module via `sys.modules` and assert the fallback content.

### Changed

- **Centralized id generation.** Every site that called `uuid4()` directly (ACP session/run ids, OpenAI-compat message/chatcmpl ids, sandbox instance ids, isolation-pool worker/request ids, CLI thread ids, e2e demo) now routes through shared helpers in `flowjet.core.ids`. All emitted ids are uniformly 16 hex chars (64 bits) under their respective prefixes; the full 32/36-char uuid forms are no longer used.
- **Session/thread ids drop the `fj-` prefix.** Ids are now bare 16-hex tokens (e.g. `550e8400e29b7800`). The prefix carried no entropy and was redundant — the token alone is what the CLI footer and `fjf` active-thread pointer use to continue a session.
- **Pause-question title no longer bold in markdown egress.** `format_questions_markdown` keeps the question title in normal font so it reads as prose, while the ⏸ heading and option labels stay bold.

## [2.1.11] — 2026-10-30

### Added

- **Reserved-pad reclaim (`sandbox.reserved_pad_path`).** The guest image reserves 3 GiB as a sparse `/pad.img` so the ArcBox rootfs formatter sizes real headroom into every sandbox; capacity alone doesn't help (the pad occupies what it reserves), so `open_workspace` deletes it once per created or adopted sandbox, before the `min_free_bytes` probe, converting reserved capacity into free space. Absolute guest path; empty (default) disables. Idempotent and fail-open: a broken `rm` leaves image-capacity slack, never blocks a turn. Pair with `agentspaceFlowjet.sandbox.minFreeBytes` (512 MiB) and the ArcBox dmsetup CoW deployment in `deploy/README.md`.

- **`FJ_LOG_LEVEL`.** A standard level name (case-insensitive) lifts the WARNING floor for the root logger, the `FJ_LOG_FILE` rotating mirror, and — with `-v` — the compact console handler. Recommended pairing: `FJ_LOG_LEVEL=debug FJ_LOG_FILE=<path>`, so DEBUG detail (e.g. nano bridge per-tool timings) lands in the file while the console stays clean. Invalid names warn and are ignored.

- **In-flight tool-arg streaming.** Partial tool-call JSON now updates the UI continuously instead of once at completion: the bridge's per-call refresh gate becomes a time throttle (`TOOL_ARGS_REFRESH_INTERVAL_S`, default 0.2 s — one frame per interval per call) and every `soothe.tool.started` refresh carries its `tool_call_id`. On ACP each refresh projects to `tool_call_update(status="in_progress")` with `raw_input`/`locations`; the agent-thought mirror fires once per call. DEBUG now logs per-tool wall-clock timings.

- **Configurable `ask_user` egress format (`FLOWJET_CLARIFICATION_FORMAT`).** `markdown` (default, byte-identical to the historical wire so generic ACP hosts see no change), `json` (structured envelope `{"type":"ask_user","version":1,"interrupt_ids":[...],"questions":[...]}` — an `application/json` resource block on ACP, a `response.flowjet.clarification` SSE event on the OpenAI surface), or `both` (frontends dedupe via `interrupt_ids`). Answering is unchanged in every mode. Shared projection lives in `flowjet.server.clarification`.

## [2.1.10] — 2026-10-30

### Added

- **Rich terminal rendering (TTY-only).** Final answers render as Markdown (headings, lists, tables, highlighted code); `fj threads -l` renders a styled table. New `flowjet.cli.render`; `rich` is imported lazily (never on `fj -V`, `-h` or completion) and every helper degrades to the existing plain text, so piped/scripted output stays byte-identical. Progress-line rendering unchanged.

- **Sandbox disk watermark (`sandbox.min_free_bytes`).** Bytes, default `0` = disabled. Probes guest free space at session open and refuses the turn with `SandboxDiskFullError`, turning a write-heavy turn's mid-run ENOSPC spiral (whose cleanup hits the approval gate) into one upfront failure. Probe is fail-open: broken probe warns, never blocks. A failed workspace open now also surfaces as a terminal `RunFailed(code="workspace_open_error")` with best-effort `close_session`, instead of a bare exception with no terminal event.

## [2.1.9] — 2026-10-27

### Changed

- **Refreshed builtin skills.** Added `autoresearch` and `oh-my-research`; removed superseded `research-bootstrap`. `platonic-coding` reworked — tightened spec/IMPL/WORKFLOW refs, new `specs-partition.md`, old `coding-plan-template.md`/`impl-guide-template.md` drafts dropped for the consolidated template namespace. Removed the stale top-level `builtin_skills/README.md`; auto-registration via `register_builtin_skill_root` unchanged.

## [2.1.8] — 2026-10-26

### Fixed

- **PostgreSQL checkpointer wired for the server surface.** `Checkpointers.open()` warned *“not wired for the flowjet server surface yet”* and yielded `None`, so a deployment with `persistence.default_backend: postgresql` silently ran every turn as a fresh conversation. It now builds an `AsyncPostgresSaver` on nano's shared checkpoints pool (`resolve_checkpointer()` → `(None, pool)`) and runs `setup()` once per process under nano's advisory lock (`SharedCheckpointerPool.setup_checkpointer`), so concurrent workers cannot race LangGraph's DDL. The pool is process-wide and deliberately not closed on exit. Failure still degrades to “no persistence” with a warning.

## [2.1.7] — 2026-10-25

### Added

- **Configurable workspace watched subdirectories.** `workspace_watched_subdirs` (env `FLOWJET_WORKSPACE_WATCHED_SUBDIRS`, comma-separated) flows Settings → `SyncAwareWorkspaceResolver(watched_subdirs=...)` → `WorkspaceManager`, which pre-creates the subtrees at open and wires them into the DirtyTracker. `None`/empty keeps `input`/`working`/`output`; unsafe entries fail loud at open rather than silently dropping sync coverage.

### Changed

- **Default identity drops the personal creator byline.** `FLOWJET_CREATOR` is empty (the soothe renderer omits “invented by …” when blank) and `FLOWJET_IDENTITY_FRAGMENT` drops the byline lines, so identity answers name only `{assistant_name}`. Vendor denylist unchanged; explicit `agent.assistant_identity` still wins (e.g. MiraCloud branding).
- **Soothe pin raised** to `>=1.2.3,<2.0.0`.

## [2.1.6] — 2026-10-24

### Fixed

- **ArcBox sandboxes stay usable across recycles, crashes and restarts.** The manager trusted its in-memory lease map and the graph pinned its sandbox id at build time, so a guest that died behind a still-`ready` record (host sleep, idle recycle, daemon restart) left every file/shell tool failing and the workspace looking empty. `open_workspace` now probes readiness once per turn — a control-plane `info()` tier (record outliving its VM, terminal states), then a guest round-trip (wedged guest) — and kills, drops and replaces a failed lease. Every new guest is seeded from the host workspace, in-flight run counts carry over, and the agent cache key is now workspace **+ sandbox id**, so a respawn rebuilds against the live guest.
- **Crash and restart recovery.** VMs get a labelled orphan deadline (`idle_timeout` + `on_idle=kill`) re-armed every 60 s, so a dead process leaves nothing behind — the daemon reaps it with no cross-process coordination or startup kill-list. On first use the manager adopts a surviving owner-scoped VM, pulling guest state to the host first (recovering a crashed turn's artifacts) instead of spawning a duplicate; a failed create reconnects and retries once.
- **Every control-plane RPC is bounded** (`kill`/`set_lifecycle` 15 s, `connect` by `connect_timeout`). The SDK deadline was opt-in and unconfigured: one wedged call stalled the reaper, and a stalled heartbeat reads as a dead owner — reaping healthy, in-use VMs.

### Changed

- `sandbox.orphan_timeout_seconds` defaults to `max(900, 3 × idle_timeout_seconds)` instead of a fixed 900, and an explicit value is validated only when the sandbox is enabled. New keys: `recover_orphans` (adopt surviving VMs after restart) and `owner` (label namespace, env `FLOWJET_SANDBOX_OWNER`) so planes sharing one daemon never adopt or reap each other's sandboxes. See RFC-005 §5.1/§5.2.

## [2.1.5] — 2026-10-24

### Fixed

- **`ask_user` pauses render as Markdown on ACP/UI hosts.** The reply reused the CLI's space-indented block, and Markdown hosts collapse the indentation into one run-on paragraph. The ACP path now emits `format_questions_markdown()`: bold pause heading, bold `Q1:`/`Q2:`-numbered questions, options as `- **label** — description` bullets, keeping the `(Recommended)` → ★ convention. CLI keeps the plain-text block.

## [2.1.4] — 2026-10-23

### Added

- **Resumable `ask_user` pauses via shared checkpointer.** Thread state (LangGraph checkpoint) persists to a shared SQLite DB (WAL + busy_timeout), so pauses survive worker switches and restarts and a second turn on the same session resumes the interrupt with the user's text as the answer. `server_checkpointer` (`"auto"` default, `"off"` for legacy stateless) drives Settings → `ServerRuntimeBuilder` → `build_isolating_nano_backend` → `AgentAdapterBase`, opened once per worker and surviving taint rebuilds.

### Changed

- **CI enforces mypy.** Added a `make typecheck` gate and fixed annotations across the CLI, core and server packages to full compliance.

## [2.1.3] — 2026-10-23

### Fixed

- **CLI: every failure path surfaces a message — no silent exits.** Closes every identified gap in the error-to-output flow:

  - `RunFailed` carries `exc_type` + traceback; `stream_query` raises `AgentRunError`, so `-v` reports the real exception type and original in-run stack.
  - SIGTERM/SIGHUP cancel gracefully: “interrupted by SIGTERM” with `128+signal` exit codes (was: instant silent death).
  - Empty answers warn on stderr (*N tool calls failed · last tool error*) and exit 3.
  - Partial narration flushes to stderr before any failure/timeout/interrupt message.
  - `--timeout SECONDS` cancels a stuck run, reporting last activity.
  - `FJ_LOG_FILE=<path>` keeps WARNING+ with full tracebacks in a rotating log for post-mortems.
  - Truncated multi-line errors hint “run with -v”; `BrokenPipeError` exits 141 with shutdown noise silenced (`fj q | head`).
  - Teardown suppresses `CancelledError` so it cannot mask the result.
  - Server parity: pool `worker_error`, OpenAI and ACP failures render `exc_type` + traceback (ACP: `Error: <Type>: <msg>`).
  - Minor: snapshot-check failures logged; config-load errors honor `-v`; plugin `sys.exit(0)` still fails loudly.

### Changed

- **ArcBox guest network off by default** (`sandbox.network` `true` → `false`). With `true` the guest is NAT'ed through the host and the daemon only knows ENABLED|NONE, so everything the host can route to — internal network and corporate VPN included — was reachable from agent shell commands. With `false` the guest boots with no network device (no route, no DNS). `web_search`/`fetch_url` are host-placement tools, unaffected. Opt back in per deployment when the guest really needs egress.

## [2.1.2] — 2026-10-21

### Changed

- **Bump `soothe` to 1.2.1** (floor `>=1.2.0` → `>=1.2.1,<2.0.0`). No flowjet API or behavior change; locked set otherwise unchanged.

## [2.1.1] — 2026-10-21

### Fixed

- **ACP clarification turns no longer end empty.** Questions were only an intermediate agent thought, and hosts accumulate message chunks as the reply, so the turn ended with no content. The ACP agent now also emits them as a message chunk via `format_questions_block`.
- **`format_questions_block` supports non-CLI hosts.** ACP and other non-CLI hosts pass `resume_hint=""` to omit the CLI resume footer; they answer in their own input surface. CLI unchanged.
- **Dropped the direct `arcbox` pin from the `server` extra.** It ships transitively via soothe-nano, so the explicit `arcbox>=0.1.0` was redundant and could drift; the import error now points at the transitive path.

## [2.1.0] — 2026-10-18

### Changed

- **`flowjet.core` layout restructure** — regrouped by responsibility, behavior unchanged:
  - `core/backends/` → **`core/runtime/`** (`direct`/`isolation`/`fake`; `runtime/isolation` keeps its layout).
  - `backends/tool_sandbox.py` → **`core/sandbox/`**: `settings`, `arbox` (`ArcBoxToolSandboxManager` + new `WorkspaceStager`), `resolver` (`SandboxAwareWorkspaceResolver`).
  - `core/bootstrap.py` → **`core/agent/`**: `config`, `skills`, `workspace`, `factory`, `wiring` (`ServerRuntimeBuilder` absorbs the assembly helpers from `server/http/app.py`).
  - `tool_stream.py` + `tool_results.py` → **`core/streaming/`** plus `presentation.py` (`ToolCallSummarizer`, `StepProgressFormatter`, `OutputTextChunker`, `AiTextExtractor`).
  - `core/backend.py` → **`core/backend_config.py`** (selection only; implementations live in `core/runtime/`).
  - Duplicated adapter lifecycle and the two identical isolating-backend factories collapse into `core/bridges/base.py` (`AgentAdapterBase`, `create_server_agent_instance`, `IsolatingBackendBuilder`); `NanoAgentAdapter`/`SootheAgentAdapter` are thin subclasses. `InteractionMode.from_metadata()` is the single request-mode parser; `mapping.extract_ask_user_interrupts` is public API.
  - Helpers regrouped into classes — import paths for `FlowJetConfigLoader.load`, `SandboxSettingsLoader.load`, `ToolResultInspector.*`, `PartialArgsParser.parse` and `InteractionMode.from_metadata` replace the old free functions. `core/__init__.py` also exports `Backend` and `resolve_backend`.

### Added

- **ArcBox tool sandbox (RFC-005).** Shell and workspace file tools run in a per-workspace ArcBox microVM via soothe-nano 2.0's `ArcBoxBackend`, enabled by a `sandbox:` section (`enabled`, `image`, `vcpus`, `mem_mib`, `network`, `workspace_root`, `default_timeout`, `idle_timeout_seconds`, `max_sandboxes`); placement-policy keys (`on_deny`, `placement_overrides`, `max_shuttle_bytes`) pass through unchanged. Runtime isolation stays the thread pool — agent loop and credentials remain on the host, only execution moves into the guest. `SandboxAwareWorkspaceResolver` stages host→guest at open and guest→host at close (before workspace sync), skipping unchanged files via a size/mtime manifest. See [RFC-005](.platonic/specs/RFC-005-arcbox-tool-sandbox.md).
- **Dynamic `max_sandboxes` compute-sizing.** Accepts `None`: 70% of logical CPUs ÷ per-sandbox `vcpus`, hard minimum 8 (small hosts and CI runners stay usable). An explicit int still pins the cap; startup logs which path was taken.
- **`max_sandboxes: 0` (unlimited) + env overrides.** `0` disables LRU eviction entirely — idle reaper and shutdown still reclaim. `FLOWJET_SANDBOX_MAX` pins the cap (`0` = unlimited); `FLOWJET_SANDBOX_MAX_PERCENT` (1–100, default 70) tunes the usable CPU fraction when the cap is computed. The field is also declared on soothe-nano's `SandboxConfig` (`int | None`, `ge=0`, default `8`) as the single source of truth.

### Removed

- **Whole-worker arcbox isolation (`FLOWJET_ISOLATION_MODE=arcbox`).** The microVM-per-workspace *worker* mode (arcbox_vm_pool / arcbox_worker / arcbox_protocol) is deleted, superseded by the tool sandbox above. `FLOWJET_ISOLATION_MODE`, all `FLOWJET_ARCBOX_*` settings and `validate_isolation_compatibility` are gone; the thread pool is the only isolation pool. The `arcbox` SDK dependency stays.

## [2.0.11] — 2026-10-15

### Changed

- **Bypass mode is now the CLI default.** `-b`/`--bypass` removed; bypass (skip all security enforcement) is the CLI default since `fj` runs on the user's own machine — use `-a`/`--ask` for guarded read-only Q&A. `bypass_mode` removed from `build_agent`; the server still rejects `bypass` via `require_mode()`. Docs (`server.md`, `upgrade.md`, `modes.py`) updated.

## [2.0.10] — 2026-10-14

### Changed

- **Bump soothe 1.0.22 → 1.1.0 and soothe-nano 1.3.3 → 1.4.2**; caps lifted to `soothe>=1.1.0,<2.0.0` and `soothe-nano>=1.4.2,<1.5.0`. `soothe-sdk` was removed upstream — its modules merged into `soothe` and `soothe-nano`. Migrated imports: `soothe_sdk.utils.serde` / `utils.formatting` / `tools.metadata` → `soothe_nano.*`, `soothe_sdk.display.message_processing` → `soothe.display.message_processing`. The try/except fallbacks in `progress.py` and `tool_stream.py` now resolve to the real implementations.

## [2.0.9] — 2026-09-24

### Fixed

- **Suppress noisy third-party startup warnings.** `RequestsDependencyWarning` (urllib3/chardet version mismatch) and `LangChainBetaWarning` (from soothe's `TypeSafeClassifier`) are unactionable notices, silenced at the earliest point of each entry point via `core/_warnings.py::suppress_known_warnings()` — called from the CLI and server `main()` before the agent stack imports.

## [2.0.8] — 2026-09-24

### Added

- **`ask_user` interrupt/resume in the CLI.** `RunRequest.resume_value` is forwarded by the direct and nano backends as `Command(resume=...)` instead of starting a new turn. `mapping.py` extracts questions and interrupt ids from `__interrupt__` onto `InterruptWaiting`; `stream.py` renders the block (options, recommended marker, resume hint) and returns an `INTERRUPTED` sentinel; `cli.py` prints the questions and feeds the query text as the answer, so `fjf -t <thread> <answer>` continues the paused run.

## [2.0.7] — 2026-09-23

### Changed

- **Bump soothe-nano 1.3.0 → 1.3.1.** Already permitted by `>=1.3.0,<1.4.0`; lock re-resolved, imports unchanged.

## [2.0.6] — 2026-09-21

### Changed

- **Bump soothe 1.0.12 → 1.0.14 and soothe-nano 1.2.28 → 1.3.0.** The `<1.3.0` cap lifted to `<1.4.0` because soothe 1.0.14 requires soothe-nano≥1.3.0; adds `langchain-typesafe`. All flowjet import paths into soothe/soothe-nano are unchanged.

## [2.0.5] — 2026-09-20

### Changed

- **Config moved off `~/.soothe` — `FLOWJET_HOME` is the authority.** Config resolves to `$FLOWJET_HOME/config/nano.yml` (default `~/.flowjet/config/nano.yml`), so an exported `SOOTHE_HOME` can no longer drag flowjet back. CLI data (thread pins, locks, completion history), logs, agents, plugins and the sqlite DBs still live under `SOOTHE_HOME`. On first run an existing `~/.soothe/config/nano.yml` (+ sibling `soothe.yml`) is copied into `$FLOWJET_HOME/config/` **once**, originals left in place — the move is reversible.
- **`fj setup` no longer aborts on an unreachable LLM endpoint.** A failed or empty `/models` probe prints a `warning:` and falls through to manual model entry (saved models for the provider, or a typed id). Provider and router profile are still written; the run ends with a note to re-check via `fj doctor`.

## [2.0.4] — 2026-09-19

### Fixed

- **`fj -V` is instant (1.78s → 0.06s).** It paid the full `soothe_nano` + `core.bootstrap` import cost to print a version string. The stdlib-only logging helpers moved to `cli.py`, `main()` parses args before setting up logging so `-V`/`-h` exit first, and the `-c/--config` help text resolves lazily. `agent.py` keeps thin delegation wrappers.

## [2.0.3] — 2026-09-18

### Added

- **Plan-step and middleware-phase progress.** The bridge maps the host loop's todo list and phase updates into step/tool events, so the terminal shows `Step 2/3 · Create a2.txt` instead of a bare `Working`. Late-parsing tool args refresh the status line once; `write_todos` is suppressed as a tool call (it drives the step line).

## [2.0.2] — 2026-09-18

### Added

- **Duo backends — `soothe` or `soothe-nano`.** `FLOWJET_BACKEND` (CLI, default `soothe`) and `FLOWJET_SERVER_BACKEND` (HTTP/ACP, default `nano`) select the runtime. The surfaces switch independently because the server needs a dual-mode agent (AGENT + ASK graphs per request), which soothe does not expose — with `FLOWJET_SERVER_BACKEND=soothe` it builds one host agent per mode and routes on `interaction_mode`.

### Changed

- The CLI builds through the `soothe` host runtime by default (host middleware, `request_plan_mode`/`ask_user` tools, configurable persona). Set `FLOWJET_BACKEND=nano` for the previous behavior.

## [2.0.1] — 2026-09-17

### Added

- **ACP sessions run in the client's directory.** `FlowJetAcpAgent` records `cwd` from `session/new|load|resume|fork` and forwards it as `metadata.workspace`; previously the client `cwd` was accepted and discarded, so every session ran in a hashed `FLOWJET_HOME` workspace.

### Changed

- **The assistant identifies as FlowJet, not Soothe.** soothe-nano prepends its own `<ASSISTANT_IDENTITY>` block (named `Soothe`) to every system prompt tier. `flowjet.core.identity` now installs a FlowJet template (coding agent, creator line, and an explicit “never identify as Soothe / soothe-nano / Claude / ChatGPT / Gemini / Anthropic / OpenAI / Google” rule) and `apply_profile` defaults `agent.name` to `FlowJet` on both surfaces. An explicit `agent.name`/`system_prompt` still wins.
- **Workspace resolution is caller-driven by default.** `FLOWJET_ALLOW_EXTERNAL_WORKSPACE` now defaults to `true`, honouring a workspace outside `FLOWJET_HOME`. Not a sandbox escape — tools remain confined to the selected workspace (`allow_paths_outside_workspace` still `false`); the boundary moves to the caller's directory. Set `false` to restore forced hashed per-session workspaces.

## [2.0.0] — 2026-09-17 — unified CLI + server

**Breaking.** `flowjet-server` is merged into this repository and ships as one distribution, `flowjet`. See [RFC-004](.platonic/specs/RFC-004-unified-package.md).

### Added

- **One distribution, two surfaces** — `flowjet.core` (shared runtime), `flowjet.cli` (was `fj_ai`), `flowjet.server` (was `flowjet_server`).
- **`fj serve`** — run the HTTP service from the CLI (`--host`, `-p/--port`, `--api-key`, `--nano-config`).
- **Optional `[server]` extra** — `pip install flowjet` pulls one runtime dependency (soothe-nano); FastAPI/uvicorn/ACP/pydantic-settings are opt-in and lazily imported so `fj` never loads them.
- **`DirectRuntimeBackend`** — the CLI runs on the same `RuntimeBackend` contract and `RuntimeEvent` stream as SSE and ACP.
- **`Narration` event** — pre-tool-call text previews in the terminal while staying invisible to protocol clients.
- **`SurfaceProfile`** (`flowjet.core.modes`) — the CLI's permissive workspace and the server's confinement are explicit per-surface invariants; `bypass` is rejected on the server surface.
- Auth uses `hmac.compare_digest` instead of `!=`.

### Changed

- Distribution renamed `flowjet-agent` → `flowjet`; version single-sourced from `flowjet.__version__`.
- Builtin skills moved to `flowjet/builtin_skills` and registered for both surfaces.
- `langchain-core` is now an explicit `server` dependency (was imported but undeclared).

### Removed

- The `fj_ai` and `flowjet_server` import namespaces. No compatibility shims — see [docs/upgrade.md](docs/upgrade.md) for the migration table.

## [0.2.0] — 2026-09-16

### Added

- **ACP (Agent Client Protocol) support.** An ACP `Agent` over WebSocket at `/acp` (Zed, custom integrations) drives the same nano-backed `RuntimeBackend` as the Responses API. Bridges `RuntimeEvent`s to `session/update` notifications (agent_message_chunk, agent_thought_chunk, tool_call/tool_call_update) and returns `PromptResponse` with `stopReason=end_turn` + usage; supports initialize and session new/load/list/prompt/cancel/close.

### Changed

- **Bumped `soothe-nano`** from `>=1.2.23,<2.0.0` to `>=1.2.28,<2.0.0`.
- **Added `agent-client-protocol[http]`** `>=0.12.1,<1.0.0` (ACP SDK server + WebSocket transport).

## [0.1.1] — 2026-09-05

### Fixed

- **litellm corrupted-install fix.** v0.1.0's image shipped a broken litellm 1.99.0 wheel — `litellm/__init__.py` was in the dist-info RECORD but missing from disk, so Python treated it as an empty namespace package and every `/v1/responses` call failed with `module 'litellm' has no attribute 'acompletion'`. Force-reinstalling restores it; the image now rebuilds the venv cleanly.

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

OpenAI Responses–compatible HTTP service backed by soothe-nano (≥1.2.23). Ask/agent interaction modes, three SSE projection modes (report / progress / developer), thread-pool isolation (RFC-002), production isolation suite (RFC-003), and a self-contained Docker deploy stack (PostgreSQL + pgvector + flowjet-server).

[0.1.1]: https://github.com/caesar0301/flowjet-server/releases/tag/v0.1.1
[0.1.0]: https://github.com/caesar0301/flowjet-server/releases/tag/v0.1.0
