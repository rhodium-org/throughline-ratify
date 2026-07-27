# throughline-ratify

A full-screen, **htop-style** terminal cockpit for working through the
[throughline](https://github.com/rhodium-org/throughline) requirement items that
await human ratification — one item at a time, with colour and glyphs carrying the
semantic weight so your eye lands on the actionable rows first.

It is **compose-aware**: on a
[`tl-compose`](https://github.com/rhodium-org/throughline-compose) project it grounds
each item over the *composed union*, so an item whose grounding chain reaches a root
only through a borrowed source counts as grounded — never orphaned. Writes only ever
land on your own consumer registers; a composed source stays read-only.

```
 throughline-ratify │ my-service                               composed │ 2 source(s)
 queue: ● 3 proposed  ◉ 2 ready  ○ 0 blocked  ⚠ 1 ungrounded  ⚑ 0 ambiguous   (6 shown)
 ▸ ● SR-0007  Rate-limit the login endpoint    │ ● SR-0007  system_requirement
   ◉ SR-0008  Store audit events append-only   │   status: proposed
   ⚠ SR-0011  Redact PII from logs             │
                                               │   ✓ ready to ratify (proposed → ratified)
                                               │   grounded: ✓   ambiguous: no
                                               │   links
                                               │     derives_from → asvs:V7.1.1  "..."
 j/k:move  r/↵:ratify  x:reject  a:all  /:filter  R:reload  ?:help  q:quit
```

## Install

```bash
pipx install throughline-ratify
```

This pulls in `throughline-compose` (and, transitively, the `throughline` core), so
the `tl` and `tl-compose` CLIs come along too.

## Use

From anywhere inside a throughline project (it walks up to find `throughline.toml`):

```bash
tl-ratify                    # open the cockpit
tl-ratify -C path/to/project # point at a specific project
tl-ratify --by alice         # record a specific ratifier on sign-off
tl-ratify --list             # print the worklist (no TUI) — good for CI/pipelines
tl-ratify --list --all       # widen: also show ratified and dead (rejected/tombstoned) items
```

### Keys

| Key | Action |
| --- | --- |
| `j` / `↓`, `k` / `↑` | move |
| `g` / `G`, PgUp / PgDn | jump / page |
| `r` / `Enter` | ratify the selected item (with confirm); on an item that overshot ratification, record the missed sign-off via a route the project's transitions permit |
| `x` | reject (invalidate) the selected item, cascading suspect to dependents |
| `a` | toggle the wide view — also show already-ratified and dead (rejected/tombstoned) items |
| `/` | filter by uid or title |
| `R` | reload the graph from disk |
| `?` | help |
| `q` | quit |

### Concerns

Every row is classified by the one thing you most need to know about it:

| Glyph | Concern | Meaning |
| --- | --- | --- |
| ● | proposed | AI-proposed, awaiting a human's accountability |
| ◉ | ready | already approved, one move from ratified |
| ○ | blocked | pending, but not directly ratifiable from its status |
| ⚠ | ungrounded | reaches no root — link it upward before sign-off |
| ⚑ | ambiguous | flagged ambiguous — clarify it first |
| ✓ | ratified | already signed off — shown only in the wide view (`a`) |
| ✗ | rejected | invalidated, kept for the record — shown only in the wide view (`a`) |
| ☠ | deleted | tombstoned, kept for history — shown only in the wide view (`a`) |

## How it works

`tl-ratify` is a thin, safe view over throughline's own Python API:

- **What needs ratifying** — every local item whose status is not the project's
  `ratified` role and is not a dead status. Ranking, colour and icon come from the
  concern each item earns.
- **Ratifying** mirrors `tl-compose ratify`: it runs throughline's grounding gate
  over the composed union (refusing ambiguous or ungrounded items), sets the
  `ratified`-role status through the config-driven `set_status` choke point, records
  who signed off, and writes the item back to its own register.
- **Rejecting** calls throughline's `invalidate`, moving the item to the
  `invalidated` role and cascading `suspect` to its trusting dependents.

No status names are hardcoded: the project's `[status.roles]` and `[transitions]`
govern every move.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
tl -C idd check --strict   # this repo is itself throughline-managed
```

This project practises what it automates: its own requirements live in
[`idd/`](https://github.com/rhodium-org/throughline-ratify/tree/main/idd) as a throughline graph, and CI gates every change on
`tl check --strict`.

## Licence

Copyright © 2026 Time Back Solutions Limited (Company No. 12938914), authored by
Henry J Grech-Cini ([ORCID 0009-0007-1565-7530](https://orcid.org/0009-0007-1565-7530)). Released under the Apache License 2.0 — see
[LICENSE](https://github.com/rhodium-org/throughline-ratify/blob/main/LICENSE) and [NOTICE](https://github.com/rhodium-org/throughline-ratify/blob/main/NOTICE).
