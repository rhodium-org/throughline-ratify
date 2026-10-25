# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""UR-0019 — sign in the role the graph declares, and see who has signed before me.

throughline 4.0.0 holds an item's ratification record as a list of signatures and
lets a graph declare roles and what each kind of item requires (throughline
SR-0254 to SR-0264). The cockpit draws what the Tool decides: the `awaiting`
concern, where an item stands against its requirement, every signature it carries,
and the role this sitting signs in. Nothing here is decided a second time (SR-0058).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from throughline_ratify import cli, core, tui

ROLES = ('\n[ratify.roles]\nsenior = ["github:ada"]\njunior = ["github:bob"]\n')
TWO = "\n[ratify.requires.requirement]\nsignatures = 2\n"


@pytest.fixture(autouse=True)
def _no_curses(monkeypatch):
    monkeypatch.setattr(tui, "_attr", lambda name, bold=False: 0)


def _declare(root: Path, config: str) -> None:
    cfg = root / "throughline.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + config, encoding="utf-8")


def _rows(session) -> dict[str, core.QueueItem]:
    return {r.uid: r for r in core.build_queue(session, show_all=True)}


def _pane(session, item: core.QueueItem, role: str | None = None) -> list[str]:
    app = tui.App(None, session, "Ada Lovelace", None, ratifier_id="github:ada", role=role)
    return [text for text, _attr in app._detail_lines(item, 80)]


# ----------------------------------------------------------- the awaiting concern

def test_the_awaiting_concern_is_drawn_with_an_icon_of_its_own():
    """A concern the Tool adds is caught at import, not drawn as a blank (SR-0058)."""
    assert "awaiting" in core.CONCERN_ICONS
    assert core.CONCERN_ICONS["awaiting"] not in {
        v for k, v in core.CONCERN_ICONS.items() if k != "awaiting"}


def test_an_item_short_of_its_requirement_is_awaiting_and_says_where_it_stands(demo_project):
    _declare(demo_project, ROLES + TWO)
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", "Ada Lovelace", by_id="github:ada", role="senior")
    row = _rows(core.open_session(demo_project))["FR-0001"]
    assert row.concern == "awaiting" and row.status == "proposed"
    assert row.signatures == ("Ada Lovelace (github:ada, as senior)",)
    assert "signed by Ada Lovelace (github:ada, as senior)" in row.standing
    assert "1 more signature" in row.standing
    assert row.ratifiable_now


def test_the_pane_shows_the_standing_the_signers_and_the_key_to_add_a_signature(demo_project):
    _declare(demo_project, ROLES + TWO)
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", "Ada Lovelace", by_id="github:ada", role="senior")
    session = core.open_session(demo_project)
    lines = _pane(session, _rows(session)["FR-0001"], role="junior")
    joined = "\n".join(lines)
    assert "still requires 1 more signature" in joined
    assert "press r to add your signature as Ada Lovelace <github:ada> as junior" in joined
    assert "signed by: Ada Lovelace (github:ada, as senior)" in joined


def test_the_second_signature_settles_the_item_and_both_signers_are_shown(demo_project):
    _declare(demo_project, ROLES + TWO)
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", "Ada Lovelace", by_id="github:ada", role="senior")
    core.ratify_item(session, "FR-0001", "Bob", by_id="github:bob", role="junior")
    row = _rows(core.open_session(demo_project))["FR-0001"]
    assert row.concern == "ratified" and row.status == "ratified"
    assert row.signatures == ("Ada Lovelace (github:ada, as senior)", "Bob (github:bob, as junior)")
    assert row.ratified_by == "Ada Lovelace and Bob"
    assert "signed by: Ada Lovelace (github:ada, as senior); Bob (github:bob, as junior)" \
        in "\n".join(_pane(core.open_session(demo_project), row))


def test_a_graph_without_roles_draws_as_before(demo_project):
    session = core.open_session(demo_project)
    core.ratify_item(session, "FR-0001", "Ada Lovelace")
    row = _rows(core.open_session(demo_project))["FR-0001"]
    assert row.concern == "ratified" and row.signatures == ("Ada Lovelace",)
    assert row.standing == "signed by Ada Lovelace"
    assert not any("still requires" in ln for ln in _pane(session, row))


# ------------------------------------------------------------ the role of a sitting

def test_the_signature_names_the_role_it_is_given_in(demo_project):
    session = core.open_session(demo_project)
    app = tui.App(None, session, "Ada Lovelace", None, ratifier_id="github:ada", role="senior")
    assert app._signature() == "Ada Lovelace <github:ada> as senior"
    assert tui.App(None, session, "Ada Lovelace", None)._signature() == "Ada Lovelace"


def test_ratifying_from_the_cockpit_passes_the_role_to_the_tool(demo_project, monkeypatch):
    _declare(demo_project, ROLES)
    session = core.open_session(demo_project)
    seen = {}

    def _ratify(sess, uid, by, by_id=None, role=None):
        seen.update(uid=uid, by=by, by_id=by_id, role=role)
    monkeypatch.setattr(core, "ratify_item", _ratify)
    app = tui.App(None, session, "Ada Lovelace", None, ratifier_id="github:ada", role="senior")
    monkeypatch.setattr(app, "_confirm", lambda q: True)
    monkeypatch.setattr(app, "_moved_under_us", lambda what: False)
    app.rows = core.build_queue(session)
    app.sel = [r.uid for r in app.rows].index("FR-0001")
    app.do_ratify()
    assert seen == {"uid": "FR-0001", "by": "Ada Lovelace", "by_id": "github:ada",
                    "role": "senior"}


def _tty(monkeypatch):
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(tui, "run", lambda *a, **k: True)


def test_a_graph_that_declares_roles_is_refused_without_one(demo_project, monkeypatch, capsys):
    _declare(demo_project, ROLES)
    _tty(monkeypatch)
    assert cli.main(["-C", str(demo_project), "--by", "Ada", "--by-id", "github:ada"]) == 2
    err = capsys.readouterr().err
    assert "declares roles (senior, junior)" in err and "--as <role>" in err
    assert cli.main(["-C", str(demo_project), "--by", "Ada", "--by-id", "github:ada",
                     "--as", "boss"]) == 2
    assert "not a role this graph declares" in capsys.readouterr().err


def test_a_graph_without_roles_refuses_a_role(demo_project, monkeypatch, capsys):
    _tty(monkeypatch)
    assert cli.main(["-C", str(demo_project), "--by", "Ada", "--as", "senior"]) == 2
    assert "declares no roles" in capsys.readouterr().err


def test_the_identifier_is_offered_from_the_signing_email_and_refused_where_none(
        demo_project, monkeypatch, capsys):
    _declare(demo_project, ROLES)
    _tty(monkeypatch)
    handed = {}
    monkeypatch.setattr(tui, "run", lambda session, ratifier, log, ratifier_id=None,
                        role=None: handed.update(ratifier_id=ratifier_id, role=role) or True)
    monkeypatch.setattr(core, "default_identifier", lambda root: "email:ada@example.com")
    assert cli.main(["-C", str(demo_project), "--by", "Ada", "--as", "senior"]) == 0
    assert handed == {"ratifier_id": "email:ada@example.com", "role": "senior"}
    monkeypatch.setattr(core, "default_identifier", lambda root: None)
    assert cli.main(["-C", str(demo_project), "--by", "Ada", "--as", "senior"]) == 2
    assert "--by-id" in capsys.readouterr().err


def test_the_role_reaches_the_cockpit_opened_from_a_list(multi_project, monkeypatch):
    _tty(monkeypatch)
    handed = {}
    monkeypatch.setattr(tui, "work_through",
                        lambda candidates, open_graph, ratifier_id=None, search=None,
                        role=None: handed.update(role=role))
    assert cli.main(["-C", str(multi_project), "--by", "Ada", "--as", "senior"]) == 0
    assert handed == {"role": "senior"}
