# FlowJet naming

**Status:** Approved  
**Date:** 2026-07-26  
**Updated:** 2026-07-26 (formal CLI + aliases; repo `flowjet-agent`)

## Identity

| Object | Value | Role |
|--------|-------|------|
| Product brand | **FlowJet** | Human-facing product name |
| PyPI / `[project].name` | **`flowjet-agent`** | Installable distribution |
| Source repository | **`flowjet-agent`** | GitHub repo (`caesar0301/flowjet-agent`) |
| Formal CLI | **`flowjet-agent`** | Canonical console entrypoint |
| CLI alias | **`fj`** | Same as `flowjet-agent` |
| CLI alias | **`fjf`** | Same as `flowjet-agent -f` / `fj -f` |
| Python import package | **`fj_ai`** | Internal module path (kept for compatibility) |

## Rules

1. **Brand in prose** — Prefer “FlowJet” for the product.
2. **Formal CLI** — Document and prefer ``flowjet-agent`` in install guides and packaging.
3. **Aliases** — ``fj`` is a short alias of ``flowjet-agent``; ``fjf`` is a short alias of ``flowjet-agent -f`` (follow this project's latest thread).
4. **Install name** — Always ``pip install flowjet-agent`` / ``uv tool install flowjet-agent``.
5. **Import path** — Keep ``from fj_ai…`` and ``src/fj_ai/`` unless a later RFC migrates the package directory.
6. **One-liner** — Package / formal CLI / repo: **flowjet-agent** · aliases: **fj**, **fjf** · Runtime: **soothe-nano**.

## Example

```bash
pip install flowjet-agent

flowjet-agent explain this repo
fj explain this repo                    # alias of flowjet-agent
fjf what did we decide last time?       # alias of flowjet-agent -f
```
