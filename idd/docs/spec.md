# throughline-ratify — specification

<!-- Generated from this repository's own requirements graph. Do not edit the
     blocks between `tl:item` markers by hand — run `tl-compose -C idd docs` and
     they are rewritten from the graph. The headings and the prose between blocks
     are hand-owned and are left alone.

     `tl-compose -C idd docs --check` fails if any block here has fallen behind the
     graph, and `tl-compose -C idd check --strict` fails if a live normative item is
     missing from this document altogether (SR-0042). -->

This document is the whole of what throughline-ratify is built to, rendered from
the items under [`idd/`](..). Requirements borrowed from throughline's own graph
are not reproduced here — they belong to that graph and are read there; what
follows is this project's own.


## Intent

Why throughline-ratify exists. Everything below grounds upward into one of these.

<!-- tl:item INT-0001 -->
**INT-0001 — Clear a backlog of un-ratified items quickly and safely from the terminal** — `intent`, status `ratified`

> A reviewer facing many AI-proposed or approved items can work through them item-by-item in one full-screen tool, ratifying or rejecting each with the same grounding guarantees the throughline CLI enforces.

**origin**: human
<!-- tl:end -->

<!-- tl:item INT-0002 -->
**INT-0002 — The assistant is distributed as an installable package, obtainable without cloning the source** — `intent`, status `ratified`

> A user should be able to install the assistant from a package index and run it, without cloning the repository or building from source. This makes the tool something people adopt rather than a script they copy, and it means the project owns a release pipeline as a first-class, maintained concern.

**origin**: hybrid · **ratified_by**: henry · **ratified_fingerprint**: sha256:18c78ba67d83f2ae2a62ee86443ced918663cff2b04e6f242041ab46782bd46d · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item INT-0003 -->
**INT-0003 — Contributable** — `intent`, status `ratified`

> As an open-source project, throughline-ratify should let an outside contributor understand how to contribute, how to report a vulnerability privately, and what conduct is expected, and should have each contribution arrive carrying an explicit, recorded grant of the rights under which it is offered — so that a contribution can be accepted without a later, unanswerable question about the terms on which it was given.

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:4ce2342bba7ed42e119c796848396cebe236f4ae51ebe1ffd62722c7c4a5f45a
<!-- tl:end -->


## Non-goals

Recorded negative space. Nothing derives from a non-goal; it is here so a
later reader can tell a deliberate omission from an oversight.

<!-- tl:item NG-0001 -->
**NG-0001 — No path to a ratification decision that does not pass through a person** — `non_goal`, status `ratified`

> tl-ratify shall offer no way for a script, a pipeline or an AI agent to reach a ratification decision — to ratify an item, to reject one, or to bring either outcome about — without a person reading the item and choosing it. It shall not be developed in that direction, and no argument from convenience, batch size or automation reaches past this. The boundary is the decision, not the terminal. An affordance that only reports — that prints what is queued, describes how the tool works, or accounts for what a person already decided — takes no decision and does not fall here; that it can be redirected, scripted or read by a machine does not put it on the wrong side of this line, and such an affordance is judged on its own merit like any other.

*Rationale:* Ratification is the one act in this toolchain that must not be reachable without a human. Everything else throughline does can be automated safely, because everything else is a claim that can be checked — grounding, transitions, document rendering, the whole validator. A ratification cannot be checked; it is a person saying they have read this and will answer for it. Reached any other way it is not a weaker record, it is a false one, and a false accountability record is the single failure the whole toolchain exists to prevent. So the risk is not that automating it would be wrong in some particular case; it is that the record stops meaning anything at all, everywhere, retrospectively. The boundary needs recording because the mistake is easy and has now been made three times in one sitting — twice proposed here and withdrawn, once raised as a question. Every time it was argued from the family resemblance to throughline and throughline-compose, which are genuinely agent-driven and genuinely need agent-facing surfaces. That resemblance is the obvious thing about these three tools; that this one turns on an act a machine must not perform is not. Written down as negative space — nothing derives from it and nothing is checked against it — it saves the next reader from re-deriving the argument, or making it a fourth time. A broader version of this boundary was drafted and rejected, and the reason is worth keeping. It said tl-ratify was not to be used at the terminal the way a command tool is. That indicted --list (SR-0008) and --summary (SR-0021), which are ratified, useful, and take no decision, and it would have ruled out future read-only affordances for a reason that does not survive scrutiny. The line that holds is around the decision.

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:4199a7ed7aacbd6d126d9d6cae97c5e74319533d8e263024251c514319d3e5c3
<!-- tl:end -->

<!-- tl:item NG-0002 -->
**NG-0002 — No contribution barrier a willing contributor cannot clear from where they are** — `non_goal`, status `ratified`

> This project shall not adopt a contribution gate that a person of good will cannot satisfy from the interface they are contributing from. A per-commit ceremony a browser cannot produce — a trailer, a signature, a form — turns away the drive-by correction the project most wants and stops nobody it should, because anyone acting in bad faith can perform the ceremony perfectly. This is recorded negative space and not a rule about any one mechanism. Measure a proposed gate against what it costs the contribution it will refuse, not only against what it is meant to prevent, and say in the item who bears that cost.

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:3d7292b81fb2779af351b1c33d07ac2a4db7124c1a1a819f13615188c1da7355
<!-- tl:end -->


## User requirements

What a person working with the tool must be able to do.

<!-- tl:item UR-0001 -->
**UR-0001 — See every item awaiting my ratification, most-actionable first** — `user_requirement`, status `ratified`

> As a reviewer I want the items that still need a human decision surfaced and ranked so I act on the ready ones before the blocked ones.

*Derives from:* INT-0001

**origin**: human
<!-- tl:end -->

<!-- tl:item UR-0002 -->
**UR-0002 — Ratify or reject an item without leaving the full-screen view** — `user_requirement`, status `ratified`

> As a reviewer I want to sign off or reject the selected item in place, with a confirmation, so review is a continuous flow.

*Derives from:* INT-0001

**origin**: human
<!-- tl:end -->

<!-- tl:item UR-0003 -->
**UR-0003 — On a composed project, items grounded through a source are ratifiable** — `user_requirement`, status `ratified`

> As a reviewer of a tl-compose project I want an item whose grounding chain reaches a root only through a borrowed source treated as grounded, not orphaned.

*Derives from:* INT-0001

**origin**: human
<!-- tl:end -->

<!-- tl:item UR-0004 -->
**UR-0004 — Read the interface like htop, not a scrolling log** — `user_requirement`, status `ratified`

> As a reviewer I want a full-screen, colour-and-glyph interface using the whole terminal, with keyboard navigation, so semantic concerns are seen at a glance.

*Derives from:* INT-0001

**origin**: human
<!-- tl:end -->

<!-- tl:item UR-0005 -->
**UR-0005 — Leave a ratification session with a written record of what I decided** — `user_requirement`, status `ratified`

> On request, the assistant shall give the ratifier a written account of what they decided in the sitting — which items they accepted, which they rejected and why, and anything the assistant changed on their behalf to carry those decisions out. The account shall be produced without the ratifier having to keep their own notes as they work, and shall be usable outside the terminal, so it can go into the commit that carries the decisions or to someone who was not present.

*Rationale:* Ratification is the accountability act this whole toolchain exists to protect, yet a sitting currently leaves no account of itself. The evidence it produces is scattered one field at a time across dozens of item files, so the only way to answer "what did I accept just now, and why did that one get rejected" is to read a diff. That matters most at exactly the moment the record is needed — writing the commit. The estate convention is that a commit cites the items it supports, and after a sitting that cleared 25 items the ratifier is asked to reconstruct that list by hand from the working tree. A ratifier who cannot easily say what they took responsibility for is a weaker accountability record than one who can.

*Derives from:* INT-0001

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:6dfc1642045c6cd9acb6dac8624810063a238285ab04a12363fd385d3c735ea5 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item UR-0006 -->
**UR-0006 — A contribution states the terms under which it is offered** — `user_requirement`, status `ratified`

> A contribution arrives under terms the project can point to. CONTRIBUTING.md shall record that submitting a contribution licenses it under the project's own Apache-2.0 terms, per section 5 of that licence, so the project never holds work whose licensing it cannot evidence. Nothing further shall be required of the contributor per commit.

*Rationale:* The first form of this required a Developer Certificate of Origin sign-off on every commit, enforced in CI. Withdrawn because of what it cost the contributions this project most wants. GitHub composes a web-UI commit — an edit in the browser, an accepted review suggestion, a revert — with no Signed-off-by trailer at all, and no check can add one, so the drive-by documentation fix was the exact contribution the gate turned away. Section 5 of the licence already achieves inbound equals outbound without asking the contributor for anything, and a term nobody has to remember is worth more here than evidence nobody was going to audit.

*Derives from:* INT-0003

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:b12e1ee38c313cd5582868b2b1dc165a77474e8f86b0b7db72035a85d9e9e06f
<!-- tl:end -->

<!-- tl:item UR-0007 -->
**UR-0007 — Know that a reload is running, not that the tool has hung** — `user_requirement`, status `ratified`

> Reloading the graph from disk (R) can take long enough that the cockpit looks frozen. While a reload is running the cockpit shall show the reviewer that it is working, so they wait for it rather than assume the tool has stopped responding.

*Derives from:* INT-0001
*Relates:* UR-0004

**origin**: human · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:cfe3180061b7227b1456158b92f5fc28b3922756f89a555f0f3163b2c65603d6
<!-- tl:end -->

<!-- tl:item UR-0008 -->
**UR-0008 — A newcomer can set up, check and offer a change without asking** — `user_requirement`, status `ratified`

> A person who has never worked on this repository shall find, in the repository itself, what they need to get a working development environment, run the tests and the requirements gate, and understand the discipline a change here is held to — including the sign-off UR-0006 requires. None of it shall depend on asking a maintainer or reading the source to infer it.

*Derives from:* INT-0003

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:952712695c9bd539ab5fa960ba6c59a84381929a46d814bd18c79534285ca0bd
<!-- tl:end -->

<!-- tl:item UR-0009 -->
**UR-0009 — A vulnerability can be reported without first disclosing it** — `user_requirement`, status `ratified`

> A person who believes they have found a security defect shall find a stated private route for reporting it, and shall know what response to expect. The public issue tracker shall not be the only channel, so reporting a defect responsibly never requires publishing it first.

*Derives from:* INT-0003

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:648612688a877e52b142373515e50342d1befdbbbfab52951f70455f43e6a3f2
<!-- tl:end -->

<!-- tl:item UR-0010 -->
**UR-0010 — What is expected of participants, and where a breach is taken** — `user_requirement`, status `ratified`

> The behaviour expected of everyone taking part shall be stated in the repository, with a private route for reporting a breach and a named person answerable for acting on one. An expectation nobody has written down cannot be relied on by the person it exists to protect.

*Derives from:* INT-0003

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:77ba804bb1844422af0ac514a80d1d1ec711562b0575db11a8c39510355ccd83
<!-- tl:end -->

<!-- tl:item UR-0011 -->
**UR-0011 — The published distribution passes the suite it ships** — `user_requirement`, status `ratified`

> A person who installs throughline-ratify from a package index shall be able to run the test suite that distribution ships and have it pass, so the package they are vetting visibly upholds the discipline this cockpit exists to enforce rather than presenting errors the moment it is examined. The published artifact shall not ship a test suite it cannot itself run green.

*Derives from:* INT-0002

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:f3b938bcf8b8cd4dae3b8e1d1b97014a5a3304f0a4efdabdb2fb8d3e093a2c67
<!-- tl:end -->

<!-- tl:item UR-0012 -->
**UR-0012 — The requirements this tool is built to can be read, and read whole** — `user_requirement`, status `ratified`

> A person who wants to know what throughline-ratify is required to do shall find those requirements rendered as a document in the repository, generated from the graph rather than written beside it. The document shall be provably current — no item shall be able to change without the document being out of date — and provably whole: a live normative requirement absent from it shall be a defect the repository's own gate reports, not something a reader can only discover by reading the register files.

*Rationale:* This repository is self-hosting: it is a tool for working a requirements graph, and it keeps its own under `idd/`. A reader who wants to know what it is required to do has, today, only the register files — a directory of YAML, one item per file, with the traceability between them readable only by walking links by hand. The graph is authored; it is not published. Generated, not written beside. A hand-written specification is a second copy of the requirements that drifts from the first, and the drift is silent because nothing compares them. Rendering from the graph makes the document a view, and `docs --check` makes staleness a build failure rather than something a reader discovers by disbelieving it. Whole, not merely fresh. Freshness alone is satisfied by a document that publishes nothing: it is never stale, because there is nothing in it to go stale. That is the weaker half, and on its own it is a gate that cannot fail. The obligation that gives the document its value is coverage — every live normative item must reach the reader — which is what makes adding an item without publishing it an error someone is told about.

*Derives from:* INT-0003

**priority**: should · **verification**: demonstration · **origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:bc07cec67d2f4cf88b6bcb97ad355eb32d42ccaa1c9d8f70d0573f9039118872
<!-- tl:end -->


## System requirements

What the software must do to meet them.

<!-- tl:item SR-0001 -->
**SR-0001 — Queue lists local items that are neither ratified nor in a dead status** — `system_requirement`, status `implemented`

> The default worklist build_queue yields every consumer item whose status is neither the ratified role nor a dead status. Already-ratified items appear only under show_all; dead (tombstoned/rejected) items appear only under show_all too, as refined by SR-0020.

*Derives from:* UR-0001

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:5a55e491069cc53f9b7b7663c994aa8d824f943f3131d3fd3210fda80e575c3e · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0002 -->
**SR-0002 — Each queued item carries a semantic concern driving colour and sort order** — `system_requirement`, status `implemented`

> Every row is classified proposed / ready / blocked / ungrounded / ambiguous; the concern selects its colour and icon and ranks it so the most actionable rows sort to the top.

*Derives from:* UR-0001

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:7e349382581350a63f4e10e62d0ac25f776ac6b883473def7ae8070141c37b67 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0003 -->
**SR-0003 — Ratify runs throughline's grounding gate then writes only the consumer register** — `system_requirement`, status `implemented`

> Ratification refuses ambiguous or ungrounded items, sets the ratified-role status via set_status, records ratified_by, and persists with write_item to the item's own register.

*Derives from:* UR-0002

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:655ef5e23922f6239f216bccc35e664cb42190f4214170212cb9b3018eb86b62 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0004 -->
**SR-0004 — Reject invalidates via throughline and cascades suspect to dependents** — `system_requirement`, status `implemented`

> Rejection calls grounding.invalidate, moving the item to the invalidated role and every trusting dependent to suspect, then persists each touched local item.

*Derives from:* UR-0002

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:dfe7ab5ce4c8f3ef1c7b8cb369790e13550b2f0db350d902962a4d09d922f465 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0005 -->
**SR-0005 — Status changes are config-driven; no status literal is hardcoded** — `system_requirement`, status `implemented`

> All transitions route through set_status / schema.status_role and schema.allows_transition, so the project's [status.roles] and [transitions] govern every move.

*Derives from:* UR-0002

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:d6f2f1f67db5263ac45f5f3eb933cf82c1cde9e8a633550f75a4b045502913f3 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0006 -->
**SR-0006 — Grounding is evaluated over the composed union when sources are declared** — `system_requirement`, status `implemented`

> When the consumer declares [[sources]], the session composes them with build_union and grounds items over that union, so a chain reaching a root through a source counts; writes still land only on the consumer.

*Derives from:* UR-0003

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:483280f53bf4a105160d6f3a4285820e0f60aa27045f5f3f83e8eef87d0dc658 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0007 -->
**SR-0007 — A full-screen curses cockpit with header, summary, list, detail and footer** — `system_requirement`, status `implemented`

> The TUI uses the whole terminal: a project header, a colour-coded concern summary, a scrollable worklist, a detail pane with grounding and links, and a keybinding footer, navigable by keyboard.

*Derives from:* UR-0004

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:373175cdb959fa3cd1afe50de08da7ee3d5dc89d7ddf64de06e926549ebf2d27 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0008 -->
**SR-0008 — A non-interactive --list mode prints the same worklist** — `system_requirement`, status `implemented`

> tl-ratify --list prints the ranked worklist to stdout without curses for pipelines, CI logs and quick glances, refusing the TUI when stdout is not a terminal.

*Derives from:* UR-0001

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:72132337fa182e2e603b0aee4e061e0a6a74afb7b090bddf8c4d986af0b02292 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0009 -->
**SR-0009 — Opening a project that cannot be ratified against fails with clear guidance, not a traceback** — `system_requirement`, status `implemented`

> When a project is missing the configuration tl-ratify needs to run its accountability gate (for example no status is bound to the 'ratified' or 'proposed' role under [status.roles]), open_session raises a user-facing RatifierError naming the offending file and how to fix it, and the CLI prints a single-line message and exits non-zero rather than dumping a Python traceback.

*Derives from:* UR-0001

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:cb07d06f3c7dd52ae8556f252402e3278ed61231b2fb86e72f1ffee7660ec5f2 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0010 -->
**SR-0010 — The summary shows ratification progress and marks ratified items distinctly from ready ones** — `system_requirement`, status `implemented`

> The header summary carries a project-wide progress figure (items ratified out of total gradable items) that climbs as the human signs off, and already-ratified items render under their own 'ratified' concern and glyph rather than sharing the 'ready' state used for approved-but-unratified items, so the number a human watches actually reflects work done.

*Derives from:* UR-0004

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:a4a156f6e8bea2a69d70ddd329b02c04794720c8d68587a71781f3a6549b791c · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0011 -->
**SR-0011 — The worklist can be ordered by grounding depth, roots-first or leaves-first** — `system_requirement`, status `implemented`

> In addition to the default most-actionable-first ordering, the operator can re-sort the queue by each item's grounding depth — either roots-first (shallowest, closest to intent, at the top) or leaves-first (deepest first) — so a large graph can be worked top-down or bottom-up. Ungrounded items sort last in either direction.

*Derives from:* UR-0001

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:f97504b7548f639670e5eb9f2ec2b13e93a418860a38a7c41fb230a1914426b3 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0012 -->
**SR-0012 — The detail pane resolves each link to its referenced title and content, including items from composed sources** — `system_requirement`, status `implemented`

> For the selected item, every link shows the referenced item's title, and — for references borrowed from a composed source — its body content, resolved over the composed union. The reference is displayed as authored (namespace-qualified for source items) while its meaning is looked up through the union, so a reviewer can see what an external clause such as asvs SR-0195 actually says without leaving the cockpit. A reference that resolves to nothing is marked unresolved.

*Derives from:* UR-0002
*Refines:* SR-0007

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:f7729abad855a22ecb783bab1dac98a2f684a9038879411255c33cd0e25e5e08 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0013 -->
**SR-0013 — The detail pane is focusable and its links can be navigated and expanded to read referenced content** — `system_requirement`, status `implemented`

> Pressing Tab moves focus between the worklist and the detail pane. With the detail pane focused, the up and down keys move a cursor over the selected item's links, and expanding a link reveals the referenced item's full content — its type, status and body — resolved over the composed union, so a borrowed source clause can be read in place. Tab or Escape returns focus to the worklist.

*Derives from:* UR-0002
*Refines:* SR-0007

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:a926915a3f9b2a713b1497ba09fcc2e61e9efc8cb08159ca2ae16a97ba46bf59 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0014 -->
**SR-0014 — A link can be removed from a local item in the cockpit, refused when removal would leave the item ungrounded** — `system_requirement`, status `implemented`

> With a link selected in the detail pane, the reviewer can remove it after confirmation. Removal is refused when it would leave the item reaching no root, so the graph cannot be silently orphaned, and the edit is written only to the consumer's own register so a composed source stays read-only. Removing an informational link that is not the item's only path to a root is allowed.

*Derives from:* UR-0002
*Relates:* SR-0006

**origin**: ai · **ratified_by**: henry · **ratified_fingerprint**: sha256:58884eafe09fb87c5f9158a2eadc43f79a808a9036db723832bacec4d41a916a · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0015 -->
**SR-0015 — A composed link shows the target's authoritative source reference, not just its namespace** — `system_requirement`, status `implemented`

> When a link targets an item borrowed from a composed source, the detail pane labels it with the target's attrs.source_ref — the authoritative clause reference such as an ASVS clause id — rather than repeating the source namespace, which the reference prefix already carries. It falls back to the namespace only when the target declares no source_ref.

*Derives from:* INT-0001
*Refines:* SR-0012

**origin**: hybrid · **ratified_by**: henry · **ratified_fingerprint**: sha256:a40ea3bd679d432624fb37050f855d8a443e533e16ea8b19364c6a80550a8d9a · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0016 -->
**SR-0016 — Interrupting the cockpit with Ctrl-C exits cleanly, without a traceback** — `system_requirement`, status `implemented`

> A KeyboardInterrupt raised by Ctrl-C while the full-screen view is waiting for input is treated like the quit key — the terminal is restored and the program exits with no Python traceback. The interrupt is absorbed both in the main input loop and at the curses.wrapper boundary, so an interrupt fired during a help screen or confirmation prompt is handled the same way.

*Derives from:* INT-0001
*Refines:* SR-0007

**origin**: hybrid · **ratified_by**: henry · **ratified_fingerprint**: sha256:9fd825f642f3a0f52a4f43071d94174760d7cb367525ee90ab3273e76a0801ed · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0017 -->
**SR-0017 — The release workflow publishes to PyPI on a GitHub Release using supported, non-deprecated action runtimes** — `system_requirement`, status `implemented`

> On a published GitHub Release the workflow builds an sdist and wheel, checks their metadata, and publishes to PyPI via Trusted Publishing (OIDC), with no stored API token. The reusable actions it depends on are pinned to versions whose runtime is still supported by GitHub — actions running on a deprecated Node runtime are bumped to a current major so the pipeline does not rely on the runner's temporary forward-compatibility shim.

*Derives from:* INT-0002

**origin**: hybrid · **ratified_by**: henry · **ratified_fingerprint**: sha256:9464c727e5877f7dd3cb36c28cbb2ba250a1fe34e028b5ab243fc7c3c875f847 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0018 -->
**SR-0018 — An item ratified then advanced beyond the ratified status is still treated as signed off** — `system_requirement`, status `implemented`

> Ratification is recorded by a stamp the ratify action writes (the ratified_by attribute), which persists after the item moves on to implemented or verified. An item carrying that stamp counts as signed off even when its current status is no longer the ratified one — it is excluded from the pending queue, shown as ratified under show-all, and counted in ratification progress. This stops a since-advanced item being re-offered for a ratification its status can no longer accept, which would otherwise surface only as a dead-end "cannot move to ratified" message.

*Derives from:* INT-0001
*Refines:* SR-0001

**origin**: hybrid · **ratified_by**: henry · **ratified_fingerprint**: sha256:aa5f4231140b4a24db22fa7c817fdfc1357ec4d40fbea6100e52927e4b74a514 · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0019 -->
**SR-0019 — Overshot items can be retrospectively ratified via a config-computed route** — `system_requirement`, status `implemented`

> An item that was advanced past the ratified status without ever being signed off (it carries no ratification stamp) is grounded and unambiguous yet cannot move straight to ratified. The assistant offers to record the missed sign-off by walking a status itinerary — from the current status, through ratified, and back to the current status — computed solely from the project's own [transitions] table, never from any hardcoded status name. If the configuration affords no such round-trip the affordance does not appear. Walking the route applies the ratification stamp as it passes through the ratified status and persists only the end state, which equals the item's original status, so the item ends exactly where it was but now proven ratified.

*Derives from:* INT-0001
*Refines:* SR-0018

**origin**: hybrid · **ratified_by**: henry · **ratified_fingerprint**: sha256:eddb618ae9c6aeb27239b1f1a1af4329704660855ff5b67357a1d2cd444266df · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0020 -->
**SR-0020 — Dead items stay visible under the wide (show-all) view** — `system_requirement`, status `implemented`

> Rejecting or otherwise invalidating an item must not make it silently disappear. The default worklist stays the actionable backlog and hides settled outcomes, but the wide view (show_all, the assistant's 'a' toggle and the CLI's --all) reveals the whole local graph — already-ratified items and dead items alike, where dead means any status playing the invalidated or tombstone role. A dead item is rendered with its own concern (rejected or deleted, decided from the project's [status.roles], not a hardcoded status name), is never offered as actionable, and carries its recorded invalidation reason so a reviewer can see what was thrown away and why.

*Derives from:* INT-0001
*Refines:* SR-0001

**origin**: hybrid · **ratified_by**: henry · **ratified_fingerprint**: sha256:8851181d0ee5410d14350f84c3a946ff75bb08de89cf4a41b983c899b45657bd · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0021 -->
**SR-0021 — A session summary of every decision taken, ready to paste into a commit** — `system_requirement`, status `implemented`

> The assistant shall accept a `--summary` option taking an optional file path. When it is given, the assistant shall record every decision the ratifier takes during the sitting and, on exit, render them as a plain-text report — to the named file if a path was supplied, otherwise to stdout after the full-screen view has closed. The report shall carry a header naming the project, whether the scope was the local graph or a composed union, the ratifier recorded on sign-off, and when the sitting ended; then one entry per decision in the order taken, each naming the item, its title, and what was decided — ratified, re-ratified, rejected with the reason given, or a grounding link removed. Where the assistant moved an item through intermediate statuses to carry a decision out, the entry shall name the route it walked; where a rejection cascaded suspicion to dependents, the entry shall name them. The report shall end with a tally and a single line listing the decided item UIDs, formatted as the trailer the estate's commit convention expects, so it can be pasted into the commit that carries the work. A sitting in which no decision was taken shall produce no report and shall not create the file. The option shall be rejected as a usage error alongside `--list`, which takes no decisions. The report shall name only the ratifier the sitting already recorded, never a value the assistant chose, and shall describe what happened rather than govern anything — the items themselves remain the only source of truth.

*Rationale:* The name is `--summary` rather than `--with-summary` because the flag names the artefact it produces, matching `--list`, and because the argument is the report's destination — `--with-summary` reads as a modifier and leaves nowhere natural to put the path. Note the full-screen view already draws a pane it calls the summary, showing ratification progress; this is a different thing, and the distinction is worth holding — one is the state of the backlog, the other is the account of a sitting. Rendering after curses has closed is what makes the output redirectable and pasteable, which is the whole point of UR-0005; a report drawn inside the full-screen view could be read but not used. Producing nothing when nothing was decided keeps a browsing session from leaving a misleading empty artefact behind, and refusing the flag alongside `--list` fails fast rather than silently handing back an empty report the user would reasonably read as "I changed nothing". The trailer line is the detail that earns the feature — it turns the sitting directly into the commit that records it, which is the moment the ratifier actually needs this.

*Derives from:* UR-0005

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:6fa63c16153286d0a3c48d9b2735d03c5fe6dead30b45aa8a8d604ede4c91bba · **ratified_backfilled**: True
<!-- tl:end -->

<!-- tl:item SR-0022 -->
**SR-0022 — Ratification is recorded through throughline's own ratify, never a copy of it** — `system_requirement`, status `implemented`

> The assistant shall record a ratification by calling throughline's own ratify operation, rather than by setting the ratified status and stamping the ratifier itself, so every part of the record throughline writes is written here too and stays written as throughline evolves. Where the assistant must reach the ratified status by a route — an item that overshot ratification without ever being signed off — it shall walk the intervening hops and hand the final move to that operation, so the sign-off itself is always throughline's. It shall pass its composed-union grounding view into the call, so an item that reaches a root only through a borrowed clause is still accepted, and writes shall continue to land only on the consumer's own registers. A refusal throughline raises — an ambiguous item, an ungrounded one, or one already ratified whose content has not changed since — shall be surfaced to the reviewer as it stands, never worked around.

*Rationale:* The cockpit forked ratification for a sound reason — it grounds over the composed union while writing only to the consumer's register, which throughline's own ratify could not do — but a fork of an accountability record drifts, and this one did. When throughline began binding a signature to the content it signed (throughline SR-0148), the cockpit went on writing the ratifier's name alone, so every item ratified through this tool carries a signature that proves who accepted it but not what they accepted. That is precisely the failure the stamp exists to prevent, and nothing in the cockpit could show a reviewer it was happening. The durable fix is one implementation rather than two — throughline accepts a prebuilt grounding index (throughline SR-0151) so the union view can be handed in, and the cockpit calls the real operation. The next field throughline adds to the record then appears here for free, and a view over a tool can no longer fall silently behind it.

*Derives from:* UR-0002

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:7073408dd41cf47585a36f2fcbc72579b8c4d2d1a5115e353a6aff725190c750
<!-- tl:end -->

<!-- tl:item SR-0023 -->
**SR-0023 — Text being typed at the prompt stays visible as it grows** — `system_requirement`, status `implemented`

> Wherever the cockpit takes typed input from a human at the foot of the screen — a rejection reason, a filter, or any prompt added later — the whole of what has been entered shall remain visible while it is being entered. When the text no longer fits the terminal's width it shall wrap, and the prompt area shall grow upward from the bottom one line at a time to hold it, giving back the space when the text shrinks or the prompt closes. The cursor shall stay at the insertion point. No entered character shall ever be hidden or silently discarded because the terminal is narrow.

*Rationale:* The prompt currently truncates the label and the buffer to the terminal's width and keeps the front of that string, so the moment a reason runs past one line the display stops moving and the person is typing blind at a cursor pinned to the right-hand edge. A rejection reason is the worst place in this tool for that to happen. It is the only free-text account of why an item was refused, it is written once and read later by someone who was not there, and it is exactly the field a person is most likely to write a full sentence into. Someone who cannot see what they have typed cannot check it, so they either write less than the record deserves or leave a mistake standing in it — and a truncated or careless reason weakens the audit trail the cockpit exists to produce. Growing the prompt upward rather than opening a separate editor keeps the item and its context on screen while the reason is written, which is the htop-like reading UR-0004 asks for; the space is borrowed only while it is needed.

*Derives from:* UR-0002
*Relates:* UR-0004

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:6dea89d3100c002acbbda2cea1088247c55f89f5ffd73aec5b6f9290866ff2e2
<!-- tl:end -->

<!-- tl:item SR-0024 -->
**SR-0024 — An item made suspect returns to the worklist** — `system_requirement`, status `implemented`

> An item that has been made suspect shall appear in the default worklist, subject only to the filter in force, whether or not it was ratified before. A past ratification shall be treated as settled only while the item's status still stands on it; once the item is suspect that sign-off no longer holds, and the item is awaiting a human again. The cascade a rejection causes shall therefore be visible in the queue the reviewer is already working through, without their having to widen the view.

*Rationale:* Rejecting an item reports that its dependents are now suspect, and then hides the ones that matter most. The worklist skips any item that either holds the ratified status or merely carries a ratification stamp; the stamp test exists so an item that was ratified and has since moved on to implemented is not offered for a ratification its status can no longer accept. A suspect item still carries that old stamp, so it is filtered out — which means the previously-ratified dependents, the only ones whose sign-off was ever real, are exactly the ones that vanish, while dependents that were never ratified stay visible. Verified against the fixture graph — rejecting a root cascaded suspicion to eight items and the one carrying a stamp was absent from the default queue and present only under the wide view. Suspicion that cannot be seen where the work is done is not much better than no suspicion at all — the reviewer is told a number and then has to go looking for what it referred to, which is the scrolling-log reading this cockpit exists to replace.

*Derives from:* UR-0001
*Relates:* UR-0002

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:817ae860b39a82ddb1bdc3ddbbc306b667c4bc7ec2ec1abfac07a980dc3e8592
<!-- tl:end -->

<!-- tl:item SR-0025 -->
**SR-0025 — A confirmation states the consequence it has actually computed** — `system_requirement`, status `implemented`

> Before a human confirms an action that may change items other than the one they selected, the cockpit shall determine what those items are and say so — how many there are, and which — and shall say plainly when there are none. A confirmation shall not assert a consequence the cockpit has not established, and shall describe what the action will do rather than what an action of that kind can do in general.

*Rationale:* The reject confirmation asks whether to reject the item "and mark dependents suspect" whatever the circumstances, having computed nothing; the affected set is only worked out afterwards, when the rejection has already been written. A human who answers that prompt twice comes away certain that items were made suspect, and may be entirely wrong — that is exactly what happened, and it sent someone looking for a cascade that had never occurred. A confirmation exists so a person can decide with their eyes open, so a prompt that overstates what will happen is worse than none — it spends the reader's trust on a claim the tool has not checked, and once they learn the wording is boilerplate they stop reading the prompts that do matter. The numbers are already in hand a moment later, so this asks for a reordering rather than new machinery. Saying so when nothing else is affected is as much of the requirement as naming the items when something is, because "no dependents affected" is the answer that most changes how freely a person can act.

*Derives from:* UR-0002
*Relates:* SR-0024

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:e6eee3538ac8e579cb4a82d37ab2d69da92bd6bca840800d0088f9b5370fe8ea
<!-- tl:end -->

<!-- tl:item SR-0026 -->
**SR-0026 — The assistant holds no configuration of its own** — `system_requirement`, status `implemented`

> The assistant shall hold no configuration of its own — no settings file, no item vocabulary, no link types, no notion of which statuses exist or what they mean that it decides for itself. Everything governing what it shows and what it may do shall be read from the project's own throughline.toml through throughline's own loader, so the assistant and tl can never hold two different accounts of the same project. Where the assistant needs a fact about the project it shall obtain it by asking throughline, not by carrying an answer. A proposed behaviour that could only work if the assistant carried configuration of its own shall be treated as a design fault to be resolved rather than a setting to be added.

*Rationale:* The assistant is a view over a graph it does not own. Its whole safety argument is that it cannot show a person something the validator would disagree with, or offer a move the project does not permit, because it is reading the same file the validator reads. Give it configuration of its own and that argument collapses in the usual way — not loudly, but by drift, where the two accounts agree for months and then differ on the one project where it matters. SR-0005 already forbids hardcoded status literals; this states the general fact SR-0005 is a single instance of, so the next instance is caught by the rule rather than by someone remembering. This also settles a question that keeps returning, which is why there is no generated agent brief here. A generated brief earns its authority by being derived from live configuration that varies per project — throughline's brief is worth generating because a project's types, link rules and transitions are genuinely its own, and the brief and the validator read the same file so they cannot disagree. The assistant has no such configuration. Anything it generated would either restate what tl context already prints from the same throughline.toml, giving the project a second mouth and somewhere for the two to differ, or be a hand-written description of the assistant generated from nothing at all — a brief that rots, wearing the tone of one that cannot. The absence is a consequence of what this tool is, not a gap in it.

*Derives from:* UR-0002
*Relates:* SR-0005

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:c700159245c18dc743730ee79bc23df94be54e4e27116e1630029e43004cbeda
<!-- tl:end -->

<!-- tl:item SR-0027 -->
**SR-0027 — The ratifier the cockpit offers is throughline's, not a copy of it** — `system_requirement`, status `ratified`

> Where no ratifier is named on the command line, the identity the assistant offers shall be the one throughline itself offers, obtained by calling throughline rather than by deciding it here, so a person opening the cockpit is offered the same name the command line would offer them. The assistant shall keep its own choice of nothing about who is offered — not the source of the identity, not the fallback when none is configured — and where throughline offers none the assistant shall surface that as it stands rather than substituting a guess of its own. An explicitly supplied ratifier shall continue to override it outright. The documentation the assistant itself prints for that option shall describe the identity actually offered, and shall change with it in the same act, so the flag's own help cannot go on stating a default the assistant no longer has.

*Rationale:* The cockpit decides the default ratifier by reading the operating-system account name. throughline decided the same thing the same way until it stopped — it now offers the identity the repository already signs its commits with, because the account name is rarely how anyone identifies themselves and differs from the name their commits carry (throughline SR-0156). The two implementations have therefore already parted, and the same person on the same machine is now offered one name at the command line and a different one in the cockpit. This is a consistency defect and should be argued as one, not dressed up as an accountability breach. It is not one — the offered name is shown in the confirmation for every single sign-off, and the cockpit refuses to open at all without a terminal, so there is no route by which it is written unseen. What makes it worth fixing anyway is that the confirmation is confirm-or-cancel — a reviewer cannot correct the name in place, only quit and start again naming one — so whatever is offered is what almost everyone will actually sign under. An offer nobody can edit carries the weight of a decision. The cost of the fork is already measurable elsewhere in this estate, where the same two people appear under five spellings precisely because a default and a hand-typed name were never the same string; a second default that disagrees with the first can only add to that. The option's own help text is named here because it is the third place this one concept is written down, after the assistant's code and throughline's. A change that moved two of the three would leave the flag advertising a default it no longer has, which is how a fork of one idea becomes three descriptions that disagree. Deciding any of it here would also be the assistant holding a policy of its own about who may sign, which SR-0026 says is a design fault to resolve rather than a setting to keep.

*Derives from:* UR-0002
*Relates:* SR-0022, SR-0026

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:2be2483f881caab16ea0e45371beb1a225706ef53f3d424d6533fa264a2eaadb
<!-- tl:end -->

<!-- tl:item SR-0028 -->
**SR-0028 — The cockpit accepts --by-id, and records everything a CLI ratification would** — `system_requirement`, status `ratified`

> The assistant shall accept a stable identifier for the ratifying human under the option name throughline uses for it, --by-id, and shall pass it to throughline's own ratify to write, so a ratification taken here carries the same record as the same ratification taken at the command line. It shall never invent, derive or default one — an absent identifier stays absent — and it shall let throughline judge whether a supplied one is well formed, surfacing a refusal as it stands. The identity a sitting signs under, in every part, shall be settled before the full-screen view opens and shall be visible in the confirmation the reviewer answers, so no part of the record is written that the reviewer was not shown. The upstream clause this tracks, tl:SR-0157, shall be cited as a composed source rather than quoted, so the obligation is resolved against a pinned edition of throughline's own graph and cannot be restated here in words that drift from it. More generally, where throughline widens what an accountability record may carry, the assistant shall widen with it rather than wait for this requirement to name the new field.

*Rationale:* throughline records an optional scheme-qualified identifier beside the ratifier's name — in its own field, never conflated with the name — because a name is not stable, people are renamed, and two people share one (tl:SR-0157). The assistant has no way to supply one, so as things stand a ratification taken in this cockpit carries strictly less than the same ratification taken by typing the command. That is backwards. This tool exists because ratification is the one act in the whole toolchain a validator cannot check, and it is the tool built for the person performing it; the record it produces should be the most complete one available, not the least. The option is named here, in the title and in the text, on purpose. An earlier draft of this requirement deliberately avoided naming it, on the reasoning that a requirement naming one field must be rewritten each time the record grows. That reasoning was wrong in a way worth recording — the requirement was ratified while its text was empty, and because neither the title nor anything else named the capability, the obligation to support --by-id disappeared entirely and the graph still passed. A requirement should degrade to something rather than to nothing. The concrete capability is therefore stated first and the general obligation second, so the general clause extends the requirement without being the only thing holding it up. SR-0022 already settles that the record itself is written by throughline's ratify rather than a copy of it, and this extends the same answer — the assistant carries the identifier to that call and decides nothing about it. Requiring it to appear in the confirmation is what keeps the addition honest, since a part of the record shown to no one would be the first part a reviewer never actually saw. Citing tl:SR-0157 by composition rather than by quotation is the other half of that lesson. A rationale that merely names an upstream clause is prose no validator reads, so the clause could be withdrawn or rewritten upstream and nothing here would notice; composing throughline's own graph as a source turns the citation into a reference that must resolve against a pinned edition. Where a wording that this requirement leans on moves, the pin has to move, and moving the pin is a reviewable act rather than a silent one.

*Derives from:* UR-0002
*Relates:* SR-0022, SR-0027
*Satisfies:* tl:SR-0157

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:edacf0f595d22bde8572d7fbface706199f2b0dd2df8adbc205587af4da2ea54
<!-- tl:end -->

<!-- tl:item SR-0029 -->
**SR-0029 — This graph composes throughline's own, so a clause it depends on is a reference, not a quotation** — `system_requirement`, status `ratified`

> This project's requirements graph shall adopt throughline's own graph as a composed source, pinned to an edition, so that a requirement here which tracks an upstream clause may point at that clause and have the reference resolved by the validator. The gate this repository runs shall be the composition-aware one, since a bare check cannot resolve such a reference and would report it as a broken link. Where the schema of this graph is widened only to admit the source's vocabulary, that shall be marked as such, so a reader can tell this project's own model from what it accepts on the source's behalf. This project shall never write to the source, and shall never ratify a borrowed item.

*Rationale:* This cockpit does not define what a ratification record is; it writes one by calling throughline's own ratify (SR-0022). That dependency was real but lived only in prose — several requirements here cite an upstream clause in a rationale field, which no validator reads, so the clause could be reworded, narrowed or withdrawn upstream and nothing on this side would notice. SR-0028 is the case in point, and its own history is the argument. Its obligation was lost once already by a mechanical accident, and a citation that survives only as prose is the same failure with a slower fuse. Composing the source makes the citation a fact the validator holds, resolved against a pinned edition, so the wording under a citation moves only when the pin moves and moving the pin is a reviewable act. The pin is also the cost, and it is the right cost — this project now has to notice when throughline moves, which is precisely the thing it was previously able to ignore. Marking the schema lines that exist only for the source matters because the union is governed by this project's schema; without the marking, a reader would take throughline's business needs and non-functional requirements for part of this project's model, when nothing here is either.

*Derives from:* UR-0002
*Relates:* SR-0028, SR-0022

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:4ef12c8d5ce198023015bb79b6be16a8299e8a8122e7239c02b8da1d993bc760
<!-- tl:end -->

<!-- tl:item SR-0030 -->
**SR-0030 — A ratification the content has outgrown returns to the worklist as its own concern** — `system_requirement`, status `ratified`

> An item whose recorded ratification fingerprint no longer matches its content shall appear in the default worklist under a concern of its own, distinct both from an item nobody has signed off and from one whose signature still stands, presented as a signature that no longer covers the wording beneath it and naming the person who gave it. It shall not be counted as ratified where the assistant reports progress. The action offered shall be ratification through throughline's own ratify, by the route the project's transitions permit where the status cannot move straight there, and both the confirmation and the session summary shall say a signature was replaced rather than that a missed one was recorded. Whether an item is in this state shall be settled by asking throughline, never by computing a fingerprint here.

*Rationale:* throughline reports a stale ratification because the words a human accepted have since been rewritten, and only a person can clear it by accepting the new wording or reverting it (tl:SR-0148). That is a job exactly one kind of user can do, and this is the tool built for them — yet it was the one place the job was invisible. Before this requirement, `tl-compose check --strict` reported SR-0028 stale while `tl-ratify --list --all` showed it as `✓ ratified` and the progress figure read 37/37. A cockpit that reports full marks while the validator reports an error is worse than one that reports nothing, because the reviewer stops looking. It is deliberately not the case SR-0019 answers, where an item advanced past ratified without ever being signed off and the route through ratified records a sign-off that never happened; here the sign-off did happen and a second is being taken over changed wording. Saying 'never ratified' of an item somebody did ratify would be a false statement about the accountability record, and counting it as ratified in the progress figure would be the same falsehood in a number. Nor is it SR-0024, where a suspect item's sign-off has already stopped holding for a reason of its own. The comparison is delegated to throughline for the reason SR-0022 gives for ratification itself — a second implementation of what counts as a content change would drift from the validator's, and the cockpit would then disagree with `check` about which items need a human.

*Derives from:* UR-0001
*Relates:* SR-0019, SR-0022, SR-0024
*Satisfies:* tl:SR-0148

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:e6be3c41ea042eb68ba12c931a9c0749b27c6aa5cc3354d14ad16b2388dabc9f
<!-- tl:end -->

<!-- tl:item SR-0031 -->
**SR-0031 — The cockpit names the build it is, so a stale install cannot pass for the current one** — `system_requirement`, status `ratified`

> The full-screen view shall show the version of the assistant that is running, in the header, where it is visible without leaving the view or knowing to ask. It shall report the version of the package actually imported rather than a string held separately, so the two cannot disagree, and it shall not be suppressed when the header is short of room in preference to the project name — a header that has dropped the version is indistinguishable from one whose build never showed it. Where the imported package is a working tree rather than the release it derives from, the reported version shall say so, and the same shall hold for each package of the toolchain the cockpit reports alongside its own.

*Rationale:* Ratification is the one act in this toolchain a validator cannot check, so the question a reviewer must be able to settle from the screen is not only what an item says but whether the thing showing it is the thing they think it is. This requirement was written from a live failure of exactly that. A pipx-installed build several features behind was on PATH; the working tree carried a newly added concern; both reported the same version string, and nothing in the full-screen view distinguished them. The reviewer opened the cockpit, saw an item shown as settled that the strict check called stale, and reasonably concluded the new work was defective — when in fact the screen was rendered by a build that predated it. The cost fell on the person this tool exists to serve, and it fell at the moment they were exercising the very judgement the tool is for. A version in the header is a small thing that turns that whole class of confusion into a glance. It is deliberately taken from the imported package rather than restated, for the same reason SR-0029 prefers a resolved reference to a quoted one — a version written down in a second place is a claim nothing checks, and this requirement exists because an unchecked claim about a version had already cost a sitting once. Taking the value from the imported package turned out not to settle it. The failure recorded above was a pipx build and a working tree reporting the same string, and an editable install reports the release number honestly held in its own metadata — so both halves of that sitting were already showing the version of the package actually imported, and still could not be told apart. This tool is the most exposed of the three, because it sits on top of both others and shows a verdict rather than computing one; a cockpit reporting a clean count beside a validator reporting an error is indistinguishable from a real defect until someone thinks to ask which build each was. The marker turns that into a glance rather than an investigation, and it is worth stating for the packages beneath as well, since it is their disagreement that produces the symptom.

*Derives from:* UR-0004
*Relates:* SR-0007

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:d52cef544fad9eae8085672d2a3d93bb7769e21ba3b418c8e4c07f0fd3421eaa
<!-- tl:end -->

<!-- tl:item SR-0032 -->
**SR-0032 — An unsigned commit fails the build, and the failure carries its own remedy** — `system_requirement`, status `rejected`

> Every commit that lands on the default branch shall carry a Developer Certificate of Origin sign-off. A continuous-integration check shall inspect each commit in the change and fail when any of them carries no Signed-off-by trailer matching either its author or its committer. On a pull request the check shall be a required status check, so a non-conforming contribution cannot be merged; on a direct push it shall fail the build, which is the strongest gate that route allows. A failing check shall name each offending commit and print the command that remedies it.

*Rationale:* Two questions the first draft left open, decided here. Scope — gating pull requests alone left maintainer pushes straight to the default branch unsigned, which made UR-0006's claim untrue of most of this repository's own history; the obligation therefore follows the commit rather than the route it arrived by, at the strength each route permits. Whose sign-off counts — matching the trailer strictly against the commit author rejects cherry-picks, rebases and co-authored work, where the person offering the contribution is the committer; accepting either endpoint keeps the evidence intact and drops the false negatives. The remedy clause is load-bearing rather than courtesy. The measurable friction in a DCO gate is a contributor who forgot -s and must rewrite history to recover, and the check that rejects the work is the only place that fix is certain to be read.

*Derives from:* UR-0006

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:3d8ce8d2b62833fe7b8c598b2bee1ab3d218d368b266b49c5916635177f14d5d · **invalidated_reason**: Withdrawn, not superseded. The gate would have blocked every browser-based contribution — a web edit, an accepted review suggestion, a revert — because GitHub composes those commits with no Signed-off-by trailer and no check can supply one. UR-0006 now rests on section 5 of the licence, which needs nothing from the contributor per commit.
<!-- tl:end -->

<!-- tl:item SR-0033 -->
**SR-0033 — A reload shows itself before it blocks, not after it returns** — `system_requirement`, status `implemented`

> Before the cockpit begins reloading the graph from disk it shall paint a visible in-progress state and flush it to the terminal, then perform the read, then repaint the refreshed worklist. The indication is therefore on screen for the duration of the blocking read, rather than a flash message that can only appear once the read has already returned.

*Derives from:* UR-0007
*Relates:* SR-0007

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:33c8a44a21af3ba05af236f5018b98ce7a4765999fdb99e707fa9b6d28f5141e
<!-- tl:end -->

<!-- tl:item SR-0034 -->
**SR-0034 — CONTRIBUTING.md carries the whole path from clone to pull request** — `system_requirement`, status `implemented`

> A CONTRIBUTING.md at the repository root shall state how to install the package for development, how to run the tests, and how to run this repository's own requirements gate — naming tl-compose rather than bare tl, because the graph composes a source and bare tl cannot resolve it. It shall state that a change is grounded in an idd/ item before it is built and that the item's UID is cited in the commit, and shall record the terms a contribution is offered under. Where the contributor is also working on throughline or throughline-compose it shall point at the chained editable install, because a cockpit running against a published validator reports figures that disagree with the gate and is indistinguishable from a real defect.

*Derives from:* UR-0008

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:8a6897b4d5075eb8f726f205e95114ebf44dfb1aa02b423e192ca49c987648c0
<!-- tl:end -->

<!-- tl:item SR-0035 -->
**SR-0035 — SECURITY.md names a private reporting route and what it covers** — `system_requirement`, status `implemented`

> A SECURITY.md at the repository root shall direct a reporter to GitHub's private vulnerability reporting rather than a public issue, state which versions are supported, and set the expectation of acknowledgement, of a window to fix before disclosure, and of credit. It shall say what is worth reporting for a tool of this kind — including any route by which the cockpit records a ratification a person did not take, which is this project's own worst failure and not an obvious one from outside.

*Derives from:* UR-0009

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:258c73e1f136c4f1d896d74c8449bef65118cd47300d48aeb1beae62af3ff897
<!-- tl:end -->

<!-- tl:item SR-0036 -->
**SR-0036 — CODE_OF_CONDUCT.md is the Contributor Covenant with a real contact on it** — `system_requirement`, status `implemented`

> A CODE_OF_CONDUCT.md at the repository root shall adopt the Contributor Covenant version 2.1, attributed to its source, and shall name the person answerable for enforcement together with the private route by which a breach reaches them. A code of conduct whose enforcement section names nobody is decoration.

*Derives from:* UR-0010

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:59eb3133000e11ed9d49a10d9978e014c72e9bd13d15dc57402662055611dce4
<!-- tl:end -->

<!-- tl:item SR-0037 -->
**SR-0037 — A rejection reports the dependents it could not flag** — `system_requirement`, status `ratified`

> When a rejection cascades suspicion, the cockpit shall report not only the dependents it marked suspect but also those whose configured lifecycle offered no route to the suspect status, naming them and the move that was refused. A dependent that is already retired shall not be reported as refused, since nothing was withheld from an item that has already gone.

*Rationale:* An item whose footing has been withdrawn but which carries no flag is exactly the drift suspicion exists to surface, and it is the one outcome of a rejection the cockpit never mentioned. Until throughline SR-0173 it could not have — invalidate() returned its whole blast radius while having marked only part of it, so the only way to report what a rejection had done was to compare each dependent's status either side of the call. That comparison answers whether an item changed and cannot answer why it did not; a dependent whose lifecycle declares no route to suspect and one that was already retired look identical to it, so the reviewer was given a smaller number and no hint that anything had been refused. The reviewer is the right person to receive it. They are accountable for the rejection, they are the one who can correct a lifecycle that strands items short of suspicion or handle the stranded item by hand, and they are in front of the tool at the moment the refusal is discovered; deferring it to a later check would report the same fact to someone with less standing to act on it. Who pays — a rejection that refuses nothing reads exactly as it does today, and one that refuses something costs the reviewer a single further line.

*Derives from:* UR-0002
*Relates:* SR-0025
*Satisfies:* tl:SR-0173

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:021c50059c82151cac05f1ffb4d29b8085ee25f06600296f41c80bebf234438c
<!-- tl:end -->

<!-- tl:item SR-0038 -->
**SR-0038 — The declared dependency range is tested at both ends on a schedule** — `system_requirement`, status `ratified`

> The repository shall run its unit tests and its graph gate on a recurring schedule, independently of any commit, against two resolutions of its declared dependency range: the versions the package index currently publishes, and the exact declared minimums. The minimum versions installed shall be derived from the package metadata rather than restated in the workflow. The schedule shall place the run outside the maintainers' working hours.

*Rationale:* throughline and throughline-compose are declared as floors rather than locked, so continuous integration resolves whatever the index happens to publish and a green check is only true on the day it ran. This repository is the most exposed of the three because it sits on both: the cockpit is ours, but every judgement it reports comes from a validator we do not ship, so a release of either can turn this repository red without a commit here. Nothing observes that in between. The failure surfaces when a contributor next opens a pull request, who meets a break that has nothing to do with their change and must diagnose someone else's drift before their own work can be judged — which is precisely the barrier UR-0008 exists to remove, arriving from outside the repository rather than from a gap in its documentation. That is not hypothetical: on 2026-08-09 throughline 1.13 shipped a rule this graph did not satisfy. Testing the two ends catches opposite faults. The ceiling catches a dependency that has moved ahead of us. The floor catches a minimum declared but no longer actually supported — the fault that follows from pinning a version on the strength of 'it has the API we call' alone, which this repository has done. Deriving the minimums from the package metadata rather than restating them keeps the workflow from drifting away from the versions the package actually promises, which would leave a green floor job proving nothing. Who pays: maintainers, who receive failures no commit of theirs caused. That is the intent — the alternative is not the absence of the failure but its arrival in a newcomer's pull request, attributed to their change. The scheduled hour is offset from the top of the hour because scheduled jobs queue heavily there, and placed outside working hours so a red result waits rather than interrupts. Rejected: locking the dependencies, which trades this failure for a silent staleness nothing observes at all; and requiring branches to be up to date with the base before merging, which addresses a different drift and would not have caught the 2026-08-09 break.

*Derives from:* UR-0008

**priority**: should · **verification**: inspection · **origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:66a4d6b3c10b32ee66919aae140373a1850431b6ede31e712980a45d603d84aa
<!-- tl:end -->

<!-- tl:item SR-0039 -->
**SR-0039 — The decisions the cockpit offers are importable without a terminal** — `system_requirement`, status `ratified`

> The module in which the worklist is built and every decision is taken shall be importable and usable on its own, without importing curses and without running a subprocess. Everything the cockpit can decide shall be decidable through it: the ordered worklist and its counts, the concerns each item is in, ratification by a named person, the walk to ratification for an item that overshot it, the preview of what a refusal unsettles, the refusal itself, the removal of a link, and the record of the sitting. The full-screen view shall be one caller of that module rather than the place the decisions live. A test shall assert the import, so a terminal-only dependency reintroduced anywhere on that path is caught rather than discovered by whoever imported it.

*Derives from:* INT-0002

**priority**: should · **verification**: The decision module is imported in a process where curses is absent from sys.modules and importing it fails; the import succeeds and no subprocess is created. The test is part of the unit suite. · **origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:2933045aa6af9722e86c0466f0a089316a0e13175dabd2cd18a265b6618c92c0
<!-- tl:end -->

<!-- tl:item SR-0040 -->
**SR-0040 — Shipped test fixtures travel in the published sdist** — `system_requirement`, status `ratified`

> The published source distribution shall include every fixture the shipped test suite needs in order to run — in particular the shared conftest that defines the hermetic fixture graph the CLI and core tests are written against — so that running the shipped suite from the sdist passes rather than erroring at collection with a missing fixture. Because setuptools' default sdist file set ships modules matching test-star but not conftest, the project shall declare the inclusion explicitly through a MANIFEST directive rather than relying on that default.

*Rationale:* The published 0.4.0 sdist ships all seven test modules but not tests/conftest.py, so the shipped suite gives 47 passed and 103 errors — every one of them a fixture that conftest defines (demo_project and its siblings) not found at collection or setup. Confirmed identical against throughline 1.13.2 and 1.14.0, so this is a packaging defect of this repository's own rather than drift from a validator release. The conftest is self-contained — it writes its fixture graph into tmp_path per test, and needs no network and no committed data — so shipping that one file is the whole remedy. throughline-compose met the same defect in its published 0.3.0 and repaired it the same way, which is what identified it here.

*Derives from:* UR-0011
*Relates:* SR-0017
*Satisfies:* tl:SR-0135

**priority**: should · **verification**: test · **origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:28c82c45a02f574ebe957bb3992121263ecd1afe453dadde348ee70893f309ca
<!-- tl:end -->

<!-- tl:item SR-0041 -->
**SR-0041 — The gate that guards the published distribution runs against the artifact, before it ships** — `system_requirement`, status `ratified`

> Continuous integration shall run the shipped test suite once more from the built source distribution installed into a clean environment, so that what is verified is the artifact a user receives rather than the working tree it was built from. That run shall execute on every change and shall gate publication, so no release reaches the index carrying a suite it cannot pass. A fixture or helper the suite needs but the distribution omits shall therefore fail the build, not the reader who runs it.

*Rationale:* UR-0011 makes its claim about the distribution a user installs, and a checkout run cannot test it: tests/conftest.py reaches the sdist only because MANIFEST.in names it (SR-0040), and pytest run from the source tree passes whether or not that line survives. That is why the defect SR-0040 records reached the index rather than being caught — the unit job was green on every push throughout, on a suite whose shipped counterpart could not collect. Gating the release rather than observing after it follows the same reasoning: a check that runs after the upload names a defect the reader can no longer avoid. The scheduled run SR-0038 requires is not a substitute, because it resolves the declared dependency range against a checkout and would not have seen this. A test asserting that MANIFEST.in contains the conftest line was considered and rejected, because it pins the present remedy rather than the obligation and would pass while a newly added helper went unshipped.

*Derives from:* UR-0011
*Relates:* SR-0040, SR-0038

**priority**: should · **verification**: test · **origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:85f5b629a70fdf26973f1f1cadb4556a6b9ad26107f487f7539c0e57629d220a
<!-- tl:end -->

<!-- tl:item SR-0042 -->
**SR-0042 — The graph is published as a document, and CI gates it fresh and complete** — `system_requirement`, status `ratified`

> The repository shall configure the documents its requirements are published into, and shall carry a generated specification document rendering every live normative item in its own graph together with the traceability between them. Continuous integration shall run the freshness check on every change, so a document that no longer matches the graph fails the build; and because configuring published documents is what makes publication coverage judged at all, the existing strict graph check shall thereby report a live normative item that no document names.

*Rationale:* `tl-compose -C idd docs --check` has been the stated gate for this repository since its contributing guide was written, and it has always passed. It passed because there was nothing to check: no `[docs] paths` were configured and no document existed, so the command had no work to do and exited zero. A gate that cannot fail is worse than no gate, because the project believes it is covered — and this repository, of all of them, is the cockpit a human uses to take accountability for requirements. Two obligations, not one. Configuring the paths gives freshness. It also switches on core's publication-coverage rule, which is the half with teeth: adding an item and forgetting to publish it becomes a strict-check failure rather than a silent omission. The two are named together because either alone leaves a hole — an empty document is always fresh, and a complete document is worthless if it may be stale. Upstream first. That coverage rule was itself inert under `tl-compose check`, which never handed the published set to the validator, so configuring paths here would have bought freshness and nothing else. The fix belongs upstream and was made there (throughline-compose SR-0038), which is why this requirement can state coverage as a consequence of configuration rather than restate the rule. Freshness runs on every change rather than only at release, for the same reason the sdist suite does (SR-0041): a document that went stale is then found at the commit that staled it, by the person still holding the context to fix it.

*Derives from:* UR-0012
*Relates:* SR-0041, SR-0034

**priority**: should · **verification**: test · **origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:64738c2e1a103e9950a1e70d307eacb3b5272b5180d4a856c3d2298be4d54bec
<!-- tl:end -->

<!-- tl:item SR-0043 -->
**SR-0043 — The declared dependency range admits no combination that cannot run** — `system_requirement`, status `ratified`

> The floors this package declares shall admit no resolution of its dependencies that the cockpit cannot run. Where two declared dependencies are a paired edition — one of them requiring a floor of the other — raising either floor raises the other with it, so that every point the declared range permits is a toolchain that works together.

*Rationale:* Two floors declared independently describe a rectangle, and this repository assumed its corners were all valid. They are not. `throughline-compose>=0.13.0` and `throughline>=1.13.2` were each true of a working pair when written, and on 2026-08-16 throughline 2.0.0 removed `tl:sourced` from core so compose could register it instead — making compose 0.14.0 the first release that renders it and 2.0.0 the first core that permits registration. The declared range still admitted compose 0.13.0 alongside core 2.0.0, and pip installs that pair without complaint. Verified, not assumed: on that pair `tl-compose` does not start at all. Every invocation, `--version` included, dies importing a private name core no longer exports — `ImportError: cannot import name '_render_item' from 'throughline.inject'` — so the failure is a Python traceback naming an internal symbol rather than anything a user can act on. `tl-ratify --list` still runs, which is the sharp end of it: the package the person installed appears to work while the checker this repository tells them to drive the graph with is dead. SR-0038 does not catch this and was never going to. It resolves the range at its two ends, and both ends are sound — the floor pair works, the current pair works, and the broken region sits in the interior where nothing looks. A range is not proved by its extremes when its members are coupled. Who pays: consumers. `pipx install throughline-ratify` is how the estate hands someone the whole toolchain (INT-0002), and a resolver may choose any point the metadata permits. What it costs them is a toolchain that installs cleanly and is then half-dead, with an error that points at throughline's internals instead of at the install. Maintainers pay too, in a floor that must be raised on someone else's release rather than only on their own API needs — the cost of declaring an edition instead of a symbol list, and deliberate. Rejected: locking the versions, which SR-0038 already rejected for trading this failure for a staleness nothing observes. Rejected: an upper bound on the older dependency, which cannot be applied retrospectively to a release already on the index and so does not fix the case that prompted this.

*Derives from:* INT-0002
*Relates:* SR-0038

**origin**: ai · **ratified_by**: Henry Grech-Cini · **ratified_fingerprint**: sha256:24f0b78eccd3050208b2b04abcadc02e2dee233e2b0940f3ba42d84be0e52b69
<!-- tl:end -->


## Traceability

Every user requirement and the system requirements that derive from it. A row
with an empty right-hand column is a requirement nothing yet delivers.

<!-- tl:matrix incoming:derives_from type == 'user_requirement' -->
| UID | Title | Derives_from (incoming) |
|---|---|---|
| UR-0001 | See every item awaiting my ratification, most-actionable first | SR-0001, SR-0002, SR-0008, SR-0009, SR-0011, SR-0024, SR-0030 |
| UR-0002 | Ratify or reject an item without leaving the full-screen view | SR-0003, SR-0004, SR-0005, SR-0012, SR-0013, SR-0014, SR-0022, SR-0023, SR-0025, SR-0026, SR-0027, SR-0028, SR-0029, SR-0037 |
| UR-0003 | On a composed project, items grounded through a source are ratifiable | SR-0006 |
| UR-0004 | Read the interface like htop, not a scrolling log | SR-0007, SR-0010, SR-0031 |
| UR-0005 | Leave a ratification session with a written record of what I decided | SR-0021 |
| UR-0006 | A contribution states the terms under which it is offered | — |
| UR-0007 | Know that a reload is running, not that the tool has hung | SR-0033 |
| UR-0008 | A newcomer can set up, check and offer a change without asking | SR-0034, SR-0038 |
| UR-0009 | A vulnerability can be reported without first disclosing it | SR-0035 |
| UR-0010 | What is expected of participants, and where a breach is taken | SR-0036 |
| UR-0011 | The published distribution passes the suite it ships | SR-0040, SR-0041 |
| UR-0012 | The requirements this tool is built to can be read, and read whole | SR-0042 |
<!-- tl:end -->

