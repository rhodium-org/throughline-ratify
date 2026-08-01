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
tl-ratify --summary          # on exit, print an account of everything you decided
tl-ratify --summary out.txt  # …or write it to a file
```

### Leaving with a record of what you decided

A sitting scatters its evidence one field at a time across dozens of item files,
so answering *"what did I just accept, and why did that one get rejected?"* means
reading a diff. `--summary` keeps a running account instead and renders it once
the full-screen view has closed — so it can be redirected, pasted into the commit
that carries the decisions, or sent to someone who was not there:

```text
tl-ratify session summary
=========================

Project  : throughline-ratify
Scope    : local graph
Ratifier : Ada Lovelace
Ended    : 2026-07-31 07:12:44 BST

Decisions taken (3), in the order taken:

  1. ratified     SR-0021
     A session summary of every decision taken

  2. re-ratified  SR-0009
     Ground each item over the composed union
     route walked: implemented -> suspect -> ratified -> implemented

  3. rejected     SR-0018
     Colour the queue by grounding depth
     reason: superseded by the concern ranking
     dependents made suspect: SR-0019, SR-0020

Tally: 1 ratified, 1 re-ratified, 1 rejected

Items: SR-0021, SR-0009, SR-0018
```

The last line is a commit trailer, so the sitting turns straight into the commit
that records it. Where the assistant moved an item through intermediate statuses
on your behalf, the entry names the route it walked; where a rejection cascaded
suspicion, it names the dependents. A sitting in which you decided nothing writes
nothing — browsing never leaves an empty artefact behind. The report only ever
names the ratifier the sitting already recorded, and it *describes*: the items
themselves remain the only source of truth.

### Keys

| Key | Action |
| --- | --- |
| `j` / `↓`, `k` / `↑` | move |
| `g` / `G`, PgUp / PgDn | jump / page |
| `r` / `Enter` | ratify the selected item (with confirm); on a stale one, accept the wording that has changed since it was signed; on an item that overshot ratification, record the missed sign-off. Where the item's status cannot reach ratified directly, a route the project's transitions permit carries it there and back |
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
| ↺ | stale | signed off, but the wording has changed since — the signature no longer covers it |
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
tl-compose -C idd check --strict   # this repo is itself throughline-managed
```

This project practises what it automates: its own requirements live in
[`idd/`](https://github.com/rhodium-org/throughline-ratify/tree/main/idd) as a throughline graph, and CI gates every change on
`tl-compose check --strict`.

The gate is the composition-aware one because this graph adopts throughline's own
graph as a pinned source. A requirement here that tracks an upstream clause points
straight at it — `satisfies: tl:SR-0157` — so the citation is resolved
against a pinned edition of throughline's requirements rather than restated in a
rationale field that nothing validates.

## Licence

Created by Dr Henry J Grech-Cini ([ORCID 0009-0007-1565-7530](https://orcid.org/0009-0007-1565-7530)).
Copyright © 2026 Henry J Grech-Cini. Released under the Apache License 2.0 — see
[LICENSE](https://github.com/rhodium-org/throughline-ratify/blob/main/LICENSE) and [NOTICE](https://github.com/rhodium-org/throughline-ratify/blob/main/NOTICE).
