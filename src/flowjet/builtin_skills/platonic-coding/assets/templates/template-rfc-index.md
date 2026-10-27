# {{PROJECT_NAME}} RFC Index

Master rollup index of all RFC specifications. For projects with namespaces
declared in `.platonic.yml`, this file stays **small**: one summary section
per namespace plus the root-level RFC table. Detailed per-RFC tables live in
each namespace's local `rfc-index.md`.

---

## Namespaces

| Namespace | Prefix | Description | RFCs | Last Updated | Local Index |
|-----------|---------|-------------|------|--------------|-------------|
| _None declared_ | | | | | |

> When namespaces are declared, each row links to `<namespace>/rfc-index.md`
> and the skill regenerates those local indexes automatically
> (`specs-generate-index`). Projects without namespaces have a single flat
> table below.

---

## Root-Level RFCs (Cross-Cutting)

RFCs that span services or define system-wide concepts. Format: `RFC-NNN`
(global sequence).

| RFC | Title | Kind | Status | Created | Last Updated |
|-----|-------|------|--------|---------|--------------|
| _None yet_ | | | | | |

> In single-namespace mode (no `namespaces:` in `.platonic.yml`), this table
> lists ALL RFCs and mirrors the pre-3.0 behavior.

---

## Supporting Documents

| Document | Purpose |
|----------|---------|
| [rfc-namings.md](rfc-namings.md) | Terminology reference (global) |
| [rfc-history.md](rfc-history.md) | Change history (global timeline) |
| [rfc-index.md](rfc-index.md) | This document |

---

## Status Legend

| Status | Meaning |
|--------|---------|
| **Draft** | Work in progress, subject to change |
| **Review** | Complete, ready for review |
| **Frozen** | Immutable production reference |
| **Deprecated** | No longer active |

---

## Quick Links

### By Kind (root-level RFCs)

- **Conceptual Design**: _None yet_
- **Architecture Design**: _None yet_
- **Implementation Interface Design**: _None yet_

### By Status (root-level RFCs)

- **Draft**: _None yet_
- **Review**: _None yet_
- **Frozen**: _None yet_

---

## Related Documents

- [rfc-history.md](rfc-history.md) - Change history
- [rfc-namings.md](rfc-namings.md) - Terminology
