# RECONCILE Mode

Update research state when new evidence contradicts existing artifacts, or when the user requests archive/rollback.

## Trigger

```
reconcile
reconcile --archive
reconcile --rollback <snapshot>
reconcile --list
reconcile --review
```

Also: after collect when contradictions vs judgment/decision/synth are detected.

## Reconcile flow

1. Diff new materials / claims against judgment, decision (if any), and published synth.
2. Compute blast radius (which artifacts need revision).
3. Propose options: update judgment → re-synth; archive old versions; narrow scope.
4. On approve: archive superseded files under `docs/archive/{timestamp}/`, update plans/synth, refresh indexes/traceability.
5. Update tree-state; may re-lock synth until Gate A re-passes.

## Archive / rollback

- `--archive` — snapshot current plans + synth + `deliverables/` (+ `deliverables/wiki/` optional)
- `--list` — list snapshots
- `--rollback` — restore snapshot (confirm first)
- `--review` — show drift summary without writing

## No evaluation re-runs

Do not invoke coding/evaluation paths. Re-analyze and re-synth only.
