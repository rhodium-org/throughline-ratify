# Contributing to throughline-ratify

Thanks for your interest. `throughline-ratify` is the htop-style terminal cockpit
(`tl-ratify`) for working through the [throughline][tl] items that await **human
ratification** — one at a time, most-actionable first.

Contributions are welcome, including the kind that isn't code: using the cockpit on
a real requirements graph and reporting where it fought you is a genuine
contribution.

## Set up your environment

```bash
git clone https://github.com/rhodium-org/throughline-ratify.git
cd throughline-ratify
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
```

That pulls [throughline-compose][tlc] and [throughline][tl] along too. Python 3.11
or later.

### If you're also working on throughline or throughline-compose

This repo sits on top of both, which makes it the most exposed of the three: the
cockpit you run can be your working tree while the validator behind it is a
published release, and **every version string will still agree**. A cockpit
reporting `38/38 ratified` while the gate reports an error is exactly what that
looks like, and it is indistinguishable from a real defect until you check which
build you're running.

Check all three out side by side and chain them in a **single** command, so the
resolver never reaches the package index:

```bash
pip install -e ../throughline -e ../throughline-compose -e '.[dev]'
```

Then verify rather than assume — every path must be your checkout, not
`site-packages`:

```bash
python -c "import throughline as a, throughline_compose as b, throughline_ratify as c; \
[print(m.__file__) for m in (a, b, c)]"
```

## Run the tests

```bash
python -m pytest
```

## Run the requirements gate

This repository manages its own requirements with the tool it serves — they live in
[`idd/`](idd). The gate rejects an ungrounded or otherwise invalid graph:

```bash
tl-compose -C idd check --strict
```

**Use `tl-compose`, not bare `tl`.** This graph adopts throughline's own as a pinned
source, so a requirement here can point at the upstream clause it tracks
(`satisfies: tl:SR-0157`) and have that reference resolved rather than merely
asserted. Bare `tl` fails the moment it meets a namespace-qualified reference it
cannot resolve.

Both the tests and the gate run in CI on every pull request.

## Making changes

This project follows **Intent-Driven Development** — the discipline the tool exists
to serve, applied to itself:

1. **Ground the change before you build it.** Find the `idd/` item that justifies
   the work. If none exists, author it first (`tl new SR --ground <PARENT_UID>`) as
   a `draft` — throughline's version of a red test: specified and justified, not yet
   built.
2. **Build it**, then move the item forward (`tl status <UID> implemented`).
3. **Cite the UID in your commit message.** Every commit here names the item it
   supports.
4. **Keep the gate green.**

If you are an AI agent rather than a person, run `tl context` in `idd/` first — it
prints the brief generated from this project's live configuration — and read
[`AGENTS.md`](AGENTS.md). Two rules are absolute: propose, never ratify, and never
invent a `--by` name. A fabricated ratifier is a false accountability record, which
is the one thing this tool exists to prevent.

## Sign your commits (DCO)

Every commit offered to this project carries a [Developer Certificate of
Origin](https://developercertificate.org) sign-off — the lightweight alternative to
a CLA. By signing off you assert you have the right to submit the work under the
project's licence. It's one flag:

```bash
git commit -s -m "Your message (SR-0034)"
```

Forgot it? Recover with `git commit --amend -s` for the last commit, or
`git rebase --signoff <base>` for a branch, then force-push. Note that GitHub's
web editor does not add the trailer, so an edit made in the browser will need
amending locally.

## Where to start

- Issues labelled `good first issue` or `help wanted`.
- Running `tl-ratify` against a real graph and reporting friction. A clear "the
  model fought me here" write-up is worth as much as a patch.
- [`README.md`](README.md) covers what the cockpit does; [`AGENTS.md`](AGENTS.md)
  covers the discipline and how the three packages fit together.

## Licensing of contributions

throughline-ratify is released under the **Apache License 2.0**
([`LICENSE`](LICENSE)). By submitting a contribution you agree it is licensed under
those same terms, per section 5 of the licence, unless you arrange otherwise with
the maintainers. Please keep the SPDX header
(`# SPDX-License-Identifier: Apache-2.0`) on new source files.

Everyone participating is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

[tl]: https://github.com/rhodium-org/throughline
[tlc]: https://github.com/rhodium-org/throughline-compose
