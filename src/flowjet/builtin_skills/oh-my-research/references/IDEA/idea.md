# IDEA Mode (optional)

Capture speculative thoughts outside the formal evidence pipeline. Supports Idea-First and Loop idea-dev.

## Trigger

```
idea "What if memory behaves like a write-ahead log?"
```

Keywords: idea, brainstorm, speculate, what if, hypothesis (when not clearly asking for full analyze).

## Steps

1. Ensure workspace (init-on-demand if needed).
2. Write `docs/ideas/YYYY-MM-DD-<slug>.md` (creates `docs/ideas/` only because this file is written). Include timestamp, free-form insight, optional links to materials/decisions later.
3. If Loop idea-dev active → present Gate L (iterate vs advance).
4. Update tree-state / loop-state as needed.

## Template

`assets/templates/idea-note-template.md`

## Routing after note

Post-step menu: continue IDEA | `collect` to ground the idea | `think` on the note | stop.

Do not treat ideas as evidence until ANALYZE grades sources.
