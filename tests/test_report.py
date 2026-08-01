# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""The sitting's written account (UR-0005, SR-0021).

Two layers are covered: the report renderer on its own, and the recording sites
in the TUI driven against a real fixture graph — so a passing test proves the log
reflects decisions that were actually persisted, not merely that the renderer can
format a hand-built log.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from throughline_ratify import cli, core, report


# --------------------------------------------------------------------------- #
# The renderer
# --------------------------------------------------------------------------- #

def _log() -> report.DecisionLog:
    log = report.DecisionLog("Ada Lovelace")
    log.ratified("FR-0001", "Guided setup wizard")
    log.reratified("FR-0007", "Overshot requirement",
                   ["implemented", "suspect", "ratified", "implemented"])
    log.rejected("FR-0002", "Rate-limit login", "superseded by FR-0001",
                 ["FR-0003", "FR-0004"])
    log.link_removed("FR-0001", "Guided setup wizard", "relates", "FR-0002")
    return log


def _rendered(log: report.DecisionLog, *, composed: bool = False) -> str:
    return report.render(
        log, project_name="Ratifier Fixture", composed=composed,
        when=datetime(2026, 7, 31, 7, 30, 0, tzinfo=timezone.utc),
    )


def test_header_names_project_scope_ratifier_and_end_time():
    out = _rendered(_log())
    assert "Project  : Ratifier Fixture" in out
    assert "Scope    : local graph" in out
    assert "Ratifier : Ada Lovelace" in out
    assert "2026-07-31 07:30:00" in out


def test_header_distinguishes_a_composed_scope():
    assert "Scope    : composed union" in _rendered(_log(), composed=True)


def test_entries_appear_in_the_order_taken():
    out = _rendered(_log())
    assert out.index("1. ratified") < out.index("2. re-ratified") < out.index("3. rejected")


def test_every_entry_names_the_item_and_its_title():
    out = _rendered(_log())
    for uid, title in [("FR-0001", "Guided setup wizard"),
                       ("FR-0007", "Overshot requirement"),
                       ("FR-0002", "Rate-limit login")]:
        assert uid in out and title in out


def test_reratification_names_the_route_walked():
    # The assistant moved the item through intermediate statuses on the ratifier's
    # behalf; the account must say so rather than silently claim a plain sign-off.
    out = _rendered(_log())
    assert "route walked: implemented -> suspect -> ratified -> implemented" in out


def test_rejection_names_the_reason_and_the_cascade():
    out = _rendered(_log())
    assert "reason: superseded by FR-0001" in out
    assert "dependents made suspect: FR-0003, FR-0004" in out


def test_rejection_without_a_reason_says_so_rather_than_printing_nothing():
    log = report.DecisionLog("Ada")
    log.rejected("FR-0002", "Rate-limit login", "", [])
    assert "reason: (none given)" in _rendered(log)


def test_link_removal_distinguishes_a_grounding_link():
    log = report.DecisionLog("Ada")
    log.link_removed("FR-0002", "Rate-limit login", "mitigates", "RISK-0001",
                     grounding=True)
    assert "removed grounding link: mitigates -> RISK-0001" in _rendered(log)


def test_tally_counts_each_kind_and_omits_kinds_that_did_not_occur():
    out = _rendered(_log())
    tally = next(ln for ln in out.splitlines() if ln.startswith("Tally:"))
    assert "1 ratified" in tally and "1 re-ratified" in tally
    assert "1 rejected" in tally and "1 link removed" in tally

    only_ratified = report.DecisionLog("Ada")
    only_ratified.ratified("FR-0001", "Guided setup wizard")
    assert _rendered(only_ratified).count("rejected") == 0


def test_report_ends_with_a_commit_ready_trailer_of_decided_uids():
    out = _rendered(_log())
    last = out.rstrip().splitlines()[-1]
    # FR-0001 was touched twice (ratified, then a link removed) but is cited once,
    # in the order first decided — this line is pasted straight into the commit.
    assert last == "Items: FR-0001, FR-0007, FR-0002"


def test_long_titles_wrap_rather_than_running_off_the_line():
    log = report.DecisionLog("Ada")
    log.ratified("FR-0001", "A " + "very " * 40 + "long title")
    assert all(len(ln) <= 80 for ln in _rendered(log).splitlines())


# --------------------------------------------------------------------------- #
# Emission
# --------------------------------------------------------------------------- #

def test_emit_to_stdout_writes_the_report(capsys):
    report.emit(_log(), report.STDOUT, project_name="Fixture", composed=False)
    assert "tl-ratify session summary" in capsys.readouterr().out


def test_emit_to_a_path_writes_the_file(tmp_path):
    dest = tmp_path / "nested" / "summary.txt"
    written = report.emit(_log(), str(dest), project_name="Fixture", composed=False)
    assert written == dest and dest.exists()
    assert "Items: FR-0001, FR-0007, FR-0002" in dest.read_text(encoding="utf-8")


def test_a_sitting_with_no_decisions_produces_no_report(tmp_path, capsys):
    # Browsing must not leave a misleading empty artefact behind.
    dest = tmp_path / "summary.txt"
    empty = report.DecisionLog("Ada")
    assert report.emit(empty, str(dest), project_name="Fixture", composed=False) is None
    assert not dest.exists()
    report.emit(empty, report.STDOUT, project_name="Fixture", composed=False)
    assert capsys.readouterr().out == ""


def test_no_summary_asked_for_writes_nothing(tmp_path):
    dest = tmp_path / "summary.txt"
    assert report.emit(_log(), None, project_name="Fixture", composed=False) is None
    assert not dest.exists()


def test_report_is_ascii_so_it_survives_any_locale_on_the_way_to_a_commit():
    _rendered(_log()).encode("ascii")  # raises if the renderer smuggles in unicode


# --------------------------------------------------------------------------- #
# The CLI contract
# --------------------------------------------------------------------------- #

def test_summary_is_a_usage_error_alongside_list(demo_project, capsys):
    rc = cli.main(["-C", str(demo_project), "--list", "--summary"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--summary cannot be used with --list" in err


def test_summary_with_a_path_is_also_refused_alongside_list(demo_project, tmp_path, capsys):
    dest = tmp_path / "summary.txt"
    rc = cli.main(["-C", str(demo_project), "--list", "--summary", str(dest)])
    assert rc == 2
    assert not dest.exists()  # failed fast, before anything was created


def test_summary_defaults_to_stdout_when_no_path_is_given():
    args = cli.build_parser().parse_args(["--summary"])
    assert args.summary == report.STDOUT


def test_summary_takes_an_optional_path():
    args = cli.build_parser().parse_args(["--summary", "out.txt"])
    assert args.summary == "out.txt"


def test_summary_is_off_unless_asked_for():
    assert cli.build_parser().parse_args([]).summary is None


def test_summary_does_not_swallow_the_next_option():
    args = cli.build_parser().parse_args(["--summary", "--by", "ada"])
    assert args.summary == report.STDOUT and args.by == "ada"


# --------------------------------------------------------------------------- #
# The recording sites, driven against a real graph
# --------------------------------------------------------------------------- #

@pytest.fixture
def app(demo_project, monkeypatch):
    """A cockpit wired to a decision log, with the curses prompts stubbed out.
    Every action below really mutates the fixture graph on disk."""
    from throughline_ratify import tui

    monkeypatch.setattr(tui.App, "_confirm", lambda self, msg, detail=None: True)
    monkeypatch.setattr(tui.App, "_prompt",
                        lambda self, msg, initial="": "superseded by FR-0001")
    session = core.open_session(demo_project)
    log = report.DecisionLog("Ada Lovelace")
    return tui.App(None, session, "Ada Lovelace", log), log


def _select(app_obj, uid: str) -> None:
    app_obj.show_all = True
    app_obj.refresh_queue()
    app_obj.sel = next(i for i, r in enumerate(app_obj.rows) if r.uid == uid)


def test_ratifying_records_the_decision_and_the_graph_agrees(app, demo_project):
    app_obj, log = app
    _select(app_obj, "FR-0001")
    app_obj.do_ratify()

    assert [(d.kind, d.uid, d.title) for d in log.decisions] == [
        (report.RATIFIED, "FR-0001", "Guided setup wizard")
    ]
    # the account describes what actually happened — the item really was signed off
    reloaded = core.open_session(demo_project).project.get("FR-0001")
    assert reloaded.attrs.get("ratified_by") == "Ada Lovelace"


def test_reratifying_records_the_route_core_actually_walked(app):
    app_obj, log = app
    _select(app_obj, "FR-0007")  # overshot to 'implemented', never signed off
    app_obj.do_ratify()          # falls through to the re-ratify route

    assert len(log) == 1
    d = log.decisions[0]
    assert d.kind == report.RERATIFIED and d.uid == "FR-0007"
    assert d.route and d.route[0] == d.route[-1] == "implemented"
    assert "ratified" in d.route


def test_rejecting_records_the_reason_and_the_dependents_made_suspect(app):
    """The account names the items the rejection really made suspect — and only those.

    FR-0001 is reachable from INT-0001 and so appears in throughline's impact set, but
    it sits at 'proposed', which the fixture's [transitions] give no route to suspect;
    the cascade therefore leaves it alone. Recording it regardless would put an item in
    the session summary, and into the commit pasted from it, as collateral of a
    rejection that never touched it (SR-0025)."""
    app_obj, log = app
    _select(app_obj, "INT-0001")  # FR-0001/2/4/5/6/7 derive from it
    app_obj.do_reject()

    d = log.decisions[0]
    assert d.kind == report.REJECTED and d.uid == "INT-0001"
    assert d.reason == "superseded by FR-0001"
    assert d.suspected, "a rejection with real dependents should record them"
    assert "FR-0001" not in d.suspected

    # every UID recorded is suspect on disk, and nothing suspect on disk is missing
    session = core.open_session(app_obj.session.root)
    suspect = session.suspect_status
    assert {i.uid for i in session.project.items() if i.status == suspect} == set(d.suspected)


def test_removing_a_link_records_it_as_a_link_removal(app):
    app_obj, log = app
    _select(app_obj, "FR-0002")
    app_obj.focus = "detail"
    app_obj.link_sel = 1  # the informational 'relates' link
    app_obj.do_remove_link()

    d = log.decisions[0]
    assert d.kind == report.LINK_REMOVED and d.uid == "FR-0002"
    assert d.link_type == "relates" and d.link_ref == "FR-0001"
    assert d.grounding is False


def test_a_refused_action_records_nothing(app):
    app_obj, log = app
    _select(app_obj, "FR-0004")  # flagged ambiguous — cannot be ratified
    app_obj.do_ratify()
    assert len(log) == 0, "an action that did not happen must not appear in the account"


def test_the_cockpit_runs_unchanged_without_a_log(demo_project, monkeypatch):
    # --summary is opt-in; every recording site must be inert when it is off.
    from throughline_ratify import tui

    monkeypatch.setattr(tui.App, "_confirm", lambda self, msg, detail=None: True)
    session = core.open_session(demo_project)
    app_obj = tui.App(None, session, "Ada Lovelace")
    _select(app_obj, "FR-0001")
    app_obj.do_ratify()
    assert core.open_session(demo_project).project.get("FR-0001").attrs["ratified_by"]


def test_a_re_signature_is_not_reported_as_a_missing_one(app):
    """SR-0030: FR-0010 was ratified by alice and rewritten since. The account has to
    distinguish that from FR-0007's case — "re-ratified" is the record of a sign-off
    that never happened, and reporting this as that would say nobody had accepted an
    item somebody had."""
    app_obj, log = app
    _select(app_obj, "FR-0010")
    app_obj.do_ratify()

    d = log.decisions[0]
    assert d.kind == report.RESIGNED and d.uid == "FR-0010"
    assert d.superseded == "alice"
    assert d.route == ()          # signed where it stood; nothing was walked


def test_a_re_signature_that_had_to_travel_records_the_route(app):
    app_obj, log = app
    _select(app_obj, "FR-0011")   # stale *and* advanced past ratified
    app_obj.do_ratify()

    d = log.decisions[0]
    assert d.kind == report.RESIGNED
    assert d.route == ("implemented", "suspect", "ratified", "implemented")


def test_the_report_says_whose_signature_was_replaced():
    log = report.DecisionLog("Ada Lovelace")
    log.resigned("FR-0010", "Rewritten since it was signed", "alice",
                 ["implemented", "suspect", "ratified", "implemented"])
    out = _rendered(log)
    assert "1. re-signed    FR-0010" in out
    assert "content changed since alice ratified it" in out
    assert "route walked: implemented -> suspect -> ratified -> implemented" in out
    assert "Tally: 1 re-signed" in out
