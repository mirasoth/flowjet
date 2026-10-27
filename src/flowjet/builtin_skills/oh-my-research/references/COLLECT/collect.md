# COLLECT Mode

User URLs plus **default four-bucket discovery**. After each source is recorded, **download + convert it to full-text Markdown** so ANALYZE can read the entire paper — not just the abstract.

## Trigger

```
collect <url|doi|arxiv|github|hf|path|"search query">
```

Also: paste of URLs; "search for …"; auto-route from intent detection; a topic with no URLs.

**Init-on-demand:** if no `AGENTS.md` / `.omr/`, run INIT first with inferred topic, then collect.

## Default mix (always four buckets)

By default COLLECT **always** fills **papers, web, github, and search** — even if the user only pasted arXiv/DOI/PDF links. Assign user URLs to their bucket; **seed the other default buckets** from the research topic (`AGENTS.md` question, or inferred from pasted sources).

**Always spawn unless opted out:** papers, web, github, search.

**Opt-in only:** datasets / HuggingFace / models — when the topic clearly needs them or the user asked.

**Opt-out** (explicit): `papers only`, `skip github`, `no web`, `don't search`, etc. Then run only the remaining default buckets.

A single pasted URL is **not** a reason to skip the other three default buckets.

Modest per-bucket targets (adapt to scope; do not harvest unbounded):

| Bucket | Default target |
|--------|----------------|
| papers | User paper URLs **plus** arXiv/OpenAlex (or similar) until about **5** papers, or a deliberately narrow corpus |
| web | User pages **plus** about **3–5** topic-relevant articles/docs |
| github | User repos **plus** about **2–3** relevant repos |
| search | Record queries used (`S-xxx.query.txt`); leftover URLs go to wave 2 |

Workers **discover in parallel** and do not wait for each other. Search leftovers that are papers/repos/pages may be collected in a **short wave 2** after merge — do not steal IDs mid-wave.

## Parallel collection (one agent per bucket)

Workers must **not** write `docs/index/papers-index.json` concurrently. Coordinator protocol:

1. Infer topic; dedupe user sources; classify; seed empty default buckets with discovery tasks + caps.
2. Read `docs/index/papers-index.json` and **pre-assign** IDs for known items **and** reserved slots per bucket. Do **not** write the index yet. Unused reserved IDs are dropped at merge.
3. Write `.omr/collect-batch.json` (topic, caps, assignments).
4. Launch **four subagents in one parallel tool turn** (plus datasets only if opted in). Each follows `references/COLLECT/agents/bucket-worker.md`.
5. Merge: `python3 scripts/collect_cli.py --merge-inbox --workspace .`
6. Optional wave 2 for leftover URLs (new reserved IDs, same inbox/merge).
7. Post-collect validation + **Gate M**.

Each worker records with:

```bash
python3 scripts/collect_cli.py "<source>" --workspace . --id P-001 --bucket papers --inbox
```

**Fallback:** if the runtime cannot spawn subagents, still cover all four default buckets, sequentially. Never leave a half-merged index.

## Full-Text Conversion (Non-negotiable)

Every convertible source **must** be downloaded and converted to full-text GitHub-Flavored Markdown. The `.source.txt` placeholder alone is insufficient — ANALYZE depends on reading the full paper content.

**Papers layout:** raw binaries go to `materials/papers-raw/<ID>.<ext>`; converted Markdown goes to `materials/papers/<ID>.md` (same stem, different suffix). Other buckets still write `materials/<bucket>/<ID>.md`.

**Conversion chain (try in order, stop at first success):**

| Step | Tool | Handles | When |
|------|------|---------|------|
| 1 (preferred) | **anydoc** (`npx -y @firecrawl/anydoc`) | `.pdf`, `.doc/.docx`, `.ppt/.pptx`, `.xls/.xlsx`, `.odt/.ods/.odp`, `.rtf`, `.epub`, `.csv` | Always try first — best structural fidelity |
| 2 (fallback) | `pymupdf` → `pdfplumber` | `.pdf` text extraction | anydoc unavailable or fails |
| 3 (fallback) | `markdownify` + `beautifulsoup4` | `.html` web pages | anydoc doesn't handle raw HTML |
| 4 (passthrough) | copy | `.md`, `.markdown`, `.txt` | Already Markdown — no conversion needed |

**anydoc availability:** if `npx` is missing or anydoc fails to install, the fallback libraries are used. If all converters fail, record `materials/failed/<ID>.failed.txt` with the reason and continue — do not block other sources.

**Install anydoc if missing:**

```bash
# anydoc needs Node 20+; it is fetched on first run, no install step
npx -y @firecrawl/anydoc --version   # verify
```

**Fallback libraries (optional, install only if anydoc is unavailable):**

```bash
pip install pymupdf pdfplumber markdownify beautifulsoup4
```

Script: `scripts/material_to_markdown.py` — downloads the source (arxiv SDK / DOI redirect / direct URL / local file), converts via the chain above, persists paper binaries to `materials/papers-raw/<ID>.<ext>`, writes Markdown to `materials/papers/<ID>.md` (other buckets: `materials/<bucket>/<ID>.md`), and records failures to `materials/failed/`.

**Batch conversion of pre-downloaded files:** If the user has already downloaded a batch of PDFs (e.g. via `curl`/`wget`) into `materials/papers-raw/` without corresponding `.md` files, use:

```bash
python3 scripts/material_to_markdown.py --convert-dir materials/papers-raw --workspace .
```

This scans the directory for convertible files (`.pdf`, `.docx`, `.html`, etc.) that lack a corresponding `.md` file, and writes Markdown to `materials/papers/<stem>.md`. The material ID is derived from the filename stem (e.g. `2506.23852.pdf` → ID `2506.23852`). Legacy mixed PDFs still sitting in `materials/papers/` convert in place if you pass `--convert-dir materials/papers`.

## Handlers

| Input | Handler | Dest (create only when writing) | Convert to `.md`? |
|-------|---------|------|------|
| arxiv / DOI / PDF paper URL | paper | `materials/papers-raw/<ID>.pdf` + `materials/papers/<ID>.md` | **Yes** — download PDF to `papers-raw`, convert via anydoc |
| Generic http(s) page | web | `materials/web/<ID>.md` | **Yes** — fetch HTML, convert via markdownify |
| github.com/… | github | `materials/github/<ID>.source.txt` | No (repo, not a document) |
| huggingface.co/… | huggingface | `materials/datasets/<ID>.source.txt` | No (dataset/model card) |
| Local file (`.pdf`, `.docx`, …) | paper | `materials/papers-raw/<ID>.<ext>` + `materials/papers/<ID>.md` | **Yes** — copy into `papers-raw`, convert via anydoc |
| Local `.md` / `.txt` | paper/web | `materials/<bucket>/<ID>.md` | Passthrough (already text) |
| Free-text query | search | `materials/search/<ID>.query.txt` | No (query, not a document) |
| Failures | — | `materials/failed/<ID>.failed.txt` | — |

**Do not** pre-create the full `materials/{papers-raw,papers,web,…}` tree. Create only the bucket that receives this source. Index files under `docs/index/` appear when the first index entry is written.

Prefer arxiv SDK / direct PDF when available. Optional Chrome MCP for screenshots of web pages.

Scripts: `scripts/collect_cli.py` (records source + invokes converter; `--inbox` / `--merge-inbox` for parallel workers) and `scripts/material_to_markdown.py` (download + convert). Routing, naming, depth, and search prioritization are **LLM-driven** per this doc — adapt handlers and destinations to the source type. Parallel workers: `references/COLLECT/agents/bucket-worker.md`.

## Indexes

Update `docs/index/`:

- `papers-index.json` + `papers-index.md`
- `web-index.json` (optional)
- `github-index.json` (optional)

Assign stable IDs: `P-001`, `W-001`, `G-001`, …

**Index entry fields for converted materials:**

```json
{
  "id": "P-001",
  "source": "https://arxiv.org/abs/1706.03762",
  "title": "Attention Is All You Need",
  "path": "materials/papers-raw/P-001.source.txt",
  "raw_path": "materials/papers-raw/P-001.pdf",
  "markdown_path": "materials/papers/P-001.md",
  "markdown_status": "converted",
  "markdown_method": "anydoc"
}
```

If conversion failed, `markdown_status: "failed"` and `markdown_failure_reason` is set; `markdown_path` is empty. `raw_path` is empty if no binary was written.

## Philosophy

- Deliver materials **with full-text Markdown** — do not over-extract, but do not under-extract either
- By default collect **papers + web + github + search** in parallel (topic discovery), even when the user only pasted one type — unless they explicitly opt out
- Graceful fallback: record failure, continue other inputs
- After successful collect with ≥1 material → run **Gate M** (Materials Sufficiency & Source Diversity) before marking `analyze` ready
- Gate M checks: minimum count, source-type diversity (papers/web/github/datasets/models), topic coverage, recency, obvious gaps, full-text availability
- Gate M shows a **diversity report** to the user and asks: collect more source types or proceed to analyze?
- If a paper conversion failed, warn the user that ANALYZE will run on abstract-only for that paper (degraded mode)
- **Post-collect validation (mandatory remediation, v1.5):** after COLLECT, verify that for every convertible file in `materials/papers-raw/`, a corresponding `materials/papers/<stem>.md` exists, and that every indexed papers/web entry has `markdown_status: "converted"`. If not, **run the batch converter before Gate M** — do not leave sources downloaded but never converted (this is the common failure mode where ANALYZE silently runs in degraded abstract-only mode):

  ```bash
  # Convert pre-downloaded binaries (e.g. curl'ed PDFs)
  python3 scripts/material_to_markdown.py --convert-dir materials/papers-raw --workspace .
  # Convert / retry every indexed source lacking a non-empty .md
  python3 scripts/material_to_markdown.py --index --workspace .
  ```

  Gate M treats unconverted entries as a **fail** until this remediation has run; only sources that still fail afterwards (paywall, broken link) may proceed as flagged degraded-mode materials.

## Gate M — Source Diversity & Sufficiency Check

After saving materials, updating indexes, **and running the mandatory post-collect conversion remediation**, run Gate M (see `GATES.md` for full checklist). The gate checks:

1. **Minimum count**: ≥3 materials (or narrow-scope note)
2. **Source-type diversity**: default buckets papers, web, github, search should be populated unless the user opted out; also datasets/models when the topic needs them
3. **Topic coverage**: materials touch ≥2 research sub-questions
4. **Recency**: ≥1 source from last 2 years
5. **Obvious gaps**: no entire sub-question area empty
6. **Full-text Markdown availability**: check `markdown_status` in the index. Unconverted entries with remediation not yet run → **fail** (run `material_to_markdown.py --index` first). Still failing after remediation → **warn** (degraded mode allowed, flagged per-material).

**Show the user a diversity report:**

```
Source Type Inventory:
  papers/    : N items  ✓/⚠/✗
  web/       : N items  ✓/⚠/✗
  github/    : N items  ✓/⚠/✗
  search/    : N items  ✓/⚠/✗
  datasets/  : N items  ✓/⚠/✗
  models/    : N items  ✓/⚠/✗
Sub-question coverage: Q1 ✓  Q2 ⚠  Q3 ✗  Q4 ✓
Suggested missing types: [list relevant to topic]
```

**Outcomes:**
- **pass** → mark `analyze` ready in tree-state; recommend `analyze`
- **warn** → suggest specific source types to collect; user decides: collect more or proceed
- **fail** → do not unlock analyze; recommend specific collect actions

Write result to `.omr/quality-gates/gate-m.json`.

## Chat reply

List saved paths, new IDs, conversion status (method used / failures), **Gate M diversity report**, Gate M status, recommended next: `analyze` (if pass) or `collect <suggested sources>` (if warn/fail).
