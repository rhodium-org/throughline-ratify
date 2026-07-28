<!--
  This is the CANONICAL agent-guidance document for throughline-ratify;
  CLAUDE.md, GEMINI.md, .github/copilot-instructions.md and .cursor/rules all
  point here so there is one source of truth, not N drifting copies.
-->

# Working with throughline-ratify (for AI agents)

This repository is **throughline-ratify**, an htop-style terminal cockpit (CLI
`tl-ratify`) for working through the
[throughline](https://github.com/rhodium-org/throughline) items that await
**human ratification** — one item at a time, most-actionable first. It is
compose-aware: on a
[`tl-compose`](https://github.com/rhodium-org/throughline-compose) project it
grounds each item over the composed union, and only ever writes to your own
consumer registers. It is also *self-hosting*: its own requirements live under
[`idd/`](idd). Read the hat that matches what you're doing:

- **Using tl-ratify inside a project?** → [Using tl-ratify](#using-tl-ratify-in-a-project).
- **Changing throughline-ratify itself?** → [Working on this repo](#working-on-this-repo-contributing).

---

## Using tl-ratify in a project

**Ratification is a deliberate human act.** `tl-ratify` exists so a *named person*
can review the requirements a machine (or teammate) proposed and take
accountability for each — recording who signed off. That accountability record is
the one thing the whole toolchain exists to protect.

### Where it fits

throughline / throughline-compose let an agent **propose** grounded requirements
(they enter `proposed`). `tl-ratify` is the human's tool for **accepting or
rejecting** them:

```bash
pipx install throughline-ratify   # pulls tl and tl-compose along too
tl-ratify                         # open the cockpit (walks up to find throughline.toml)
tl-ratify -C idd                  # point at a graph under idd/
tl-ratify --by alice              # record the ratifier on sign-off
tl-ratify --list                  # print the worklist, no TUI (good for CI/scripts)
tl-ratify --list --all            # also show ratified and dead items
```

In the cockpit: `r`/`Enter` ratify · `x` reject (cascades *suspect* to
dependents) · `/` filter · `a` wide view · `q` quit.

### If you are the AI agent, not the human

- **Do not ratify on a human's behalf.** Never run a ratify action, and never
  invent or reuse a `--by` name/email. A fabricated ratifier is a false
  accountability record — the one thing this tool exists to prevent.
- **Your job is to surface, then hand off.** After you propose items, you may run
  `tl-ratify --list` (read-only) to show the human what is queued, then **stop and
  ask them to ratify.** If you do not know who is ratifying, ask and use exactly
  what they give you.

### Best practice: keep the graph in `idd/`

Whichever throughline tool created the graph, the estate convention is to keep it
in a top-level `idd/` directory; `tl-ratify -C idd` then points straight at it.

## How to guide an agent to *use* the tool (the pattern)

Don't hand-write a brief that rots. In the *consuming* project add a short
`AGENTS.md` (the vendor-neutral standard) that points the agent at the generated
throughline brief and states the two invariants — *ground every item upward
before you build it*, and *only a named human ratifies machine-proposed items* —
then let each framework's own file (`CLAUDE.md`, `GEMINI.md`,
`.github/copilot-instructions.md`, `.cursor/rules/…`) be a **one-line pointer** to
that `AGENTS.md`, never a copy. This repo does exactly that.

---

## Working on this repo (contributing)

throughline-ratify is open source (Apache-2.0) and contributions are welcome. It
is a pure-Python curses app (`src/throughline_ratify`, CLI `tl-ratify`) that is a
thin, safe view over throughline's own Python API — it hardcodes **no** status
names; the project's `[status.roles]` and `[transitions]` govern every move.

```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"       # pulls throughline-compose (and throughline) along too
pytest -q
tl -C idd check --strict      # this repo's own requirements graph — keep it green
```

Changes here follow the same IDD discipline this tool serves: ground the change in
an `idd/` item (create + get it ratified if new — you can dogfood `tl-ratify`
itself), cite the UID in your commit, and keep `tl -C idd check --strict` green.
