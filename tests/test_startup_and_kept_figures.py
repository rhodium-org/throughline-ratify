# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0094 and SR-0095 — starting over a large tree.

Over 430 graphs the search showed nothing for seven seconds, and every figure
was read again, 89 seconds of it, each time the list was shown. The search now
says how far it has got, and a figure is read again only when its graph's own
files have moved.
"""
from __future__ import annotations

import io
import json
import time

import pytest

from conftest import _named_project
from test_back_to_the_list import Screen, no_curses  # noqa: F401 - fixture
from throughline_ratify import cli, core, tui


@pytest.fixture
def reads(monkeypatch):
    """The graphs read in full, by directory name, as they are read."""
    opened = []
    opening = core._open

    def _counting(root, *a, **k):
        opened.append(root.name)
        return opening(root, *a, **k)

    monkeypatch.setattr(core, "_open", _counting)
    return opened


# --------------------------------------------------------------------------- #
# SR-0094 — the search says how far it has got
# --------------------------------------------------------------------------- #

def test_the_search_reports_its_path_and_counts(multi_project):
    heard = []
    found = core.discover_projects(multi_project, on_search=lambda *a: heard.append(a))
    assert {base for base, _, _ in heard} == {multi_project}
    directories = [d for _, d, _ in heard]
    assert directories == sorted(directories) and directories[-1] > 1
    assert heard[-1][2] <= len(found)


def test_the_counts_run_on_across_several_paths(multi_project, tmp_path):
    other = tmp_path / "other"
    _named_project(other / "idd", "Other Graph")
    heard = []
    core.discover_projects(multi_project, other, on_search=lambda *a: heard.append(a))
    first = [h for h in heard if h[0] == multi_project]
    second = [h for h in heard if h[0] == other]
    assert second[0][1] > first[-1][1], "directories carry on from the first path"
    assert second[0][2] >= 2, "the first path's graphs are counted in"


def test_the_line_names_the_path_and_counts_and_is_cleared():
    stream = io.StringIO()
    line = cli._SearchLine(stream)
    somewhere = core.Path("/somewhere")
    line.update(somewhere, 12, 3)
    line.clear()
    written = stream.getvalue()
    assert f"searching {somewhere}" in written and "12 directories, 3 graphs found" in written
    assert written.endswith("\r\x1b[K")


def test_the_line_moves_at_least_once_a_second_while_nothing_reports():
    stream = io.StringIO()
    line = cli._SearchLine(stream)
    somewhere = core.Path("/somewhere")
    line.update(somewhere, 1, 0)
    time.sleep(1.1)
    line.clear()
    assert stream.getvalue().count(f"searching {somewhere}") >= 3


def test_a_terminal_sees_the_search_and_the_line_is_gone_before_the_list(
        multi_project, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True, raising=False)
    at_list = []
    monkeypatch.setattr(tui, "work_through",
                        lambda *a, **k: at_list.append(capsys.readouterr().err))
    assert cli.main(["-C", str(multi_project), "--by", "Ada"]) == 0
    assert "searching" in at_list[0] and at_list[0].endswith("\r\x1b[K")


def test_list_shows_no_search_line(multi_project, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True, raising=False)
    assert cli.main(["-C", str(multi_project), "--list"]) == 2
    assert "searching" not in capsys.readouterr().err


def test_no_terminal_on_standard_error_shows_no_search_line(multi_project, monkeypatch,
                                                            capsys):
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(tui, "work_through", lambda *a, **k: None)
    assert cli.main(["-C", str(multi_project), "--by", "Ada"]) == 0
    assert "searching" not in capsys.readouterr().err


def test_naming_a_graph_directly_shows_nothing(demo_project, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(tui, "run", lambda *a, **k: True)
    assert cli.main(["-C", str(demo_project), "--by", "Ada"]) == 0
    assert capsys.readouterr().err == ""


# --------------------------------------------------------------------------- #
# SR-0095 — figures kept, and read again only when their files move
# --------------------------------------------------------------------------- #

def test_a_second_run_reads_no_graph(multi_project, reads):
    found = core.discover_projects(multi_project)
    first = core.describe_candidates(found, kept=core.Assessments())
    assert sorted(reads) == ["alpha", "beta"]
    reads.clear()
    again = core.describe_candidates(found, kept=core.Assessments())
    assert reads == []
    assert [(c.ratified, c.gradable) for c in again] == \
        [(c.ratified, c.gradable) for c in first]


def test_a_graph_whose_files_moved_is_read_again(multi_project, reads):
    found = core.discover_projects(multi_project)
    core.describe_candidates(found, kept=core.Assessments())
    reads.clear()
    item = next((multi_project / "beta").rglob("FR-0001.yml"))
    item.write_text(item.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    core.describe_candidates(found, kept=core.Assessments())
    assert reads == ["beta"]


def test_progress_counts_only_the_graphs_read(multi_project):
    found = core.discover_projects(multi_project)
    core.describe_candidates(found[:1], kept=core.Assessments())
    heard = []
    core.describe_candidates(found, on_progress=lambda *a: heard.append(a[:2]),
                             kept=core.Assessments())
    assert heard == [(0, 1)]


def test_another_version_reads_every_graph(multi_project, reads, monkeypatch):
    found = core.discover_projects(multi_project)
    core.describe_candidates(found, kept=core.Assessments())
    reads.clear()
    monkeypatch.setattr(core, "_reader", lambda: "9.9.9/9.9.9")
    core.describe_candidates(found, kept=core.Assessments())
    assert sorted(reads) == ["alpha", "beta"]


def test_without_reuse_every_graph_is_read_and_kept(multi_project, reads):
    found = core.discover_projects(multi_project)
    core.describe_candidates(found, kept=core.Assessments())
    reads.clear()
    core.describe_candidates(found, kept=core.Assessments(), reuse=False)
    assert sorted(reads) == ["alpha", "beta"]


def test_an_unreadable_graph_is_kept_with_its_reason(multi_project, reads):
    (multi_project / "beta" / "requirements" / "FR-0001.yml").write_text(
        "uid: [unclosed\n", encoding="utf-8")
    found = core.discover_projects(multi_project)
    core.describe_candidates(found, kept=core.Assessments())
    reads.clear()
    again = core.describe_candidates(found, kept=core.Assessments())
    assert reads == []
    assert again[1].error and again[0].error is None


def test_a_corrupt_file_keeps_nothing_and_is_replaced(multi_project, reads):
    path = core.assessments_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    core.describe_candidates(core.discover_projects(multi_project), kept=core.Assessments())
    assert sorted(reads) == ["alpha", "beta"]
    assert set(json.loads(path.read_text(encoding="utf-8"))["graphs"]) == {
        str(multi_project / "alpha"), str(multi_project / "beta")}


def test_a_file_that_cannot_be_written_leaves_the_figures_shown(multi_project,
                                                                monkeypatch):
    def _refuse(*a):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(core.os, "replace", _refuse)
    described = core.describe_candidates(core.discover_projects(multi_project),
                                         kept=core.Assessments())
    assert all(c.gradable is not None for c in described)


def test_the_file_sits_beside_the_favourites_and_nothing_enters_a_project(multi_project):
    before = sorted(multi_project.rglob("*"))
    core.describe_candidates(core.discover_projects(multi_project), kept=core.Assessments())
    assert core.assessments_path().parent == core.favourites_path().parent
    assert core.assessments_path().exists()
    assert sorted(multi_project.rglob("*")) == before


def test_the_list_shown_again_reads_no_unchanged_graph(multi_project, reads, no_curses):
    chooser = tui.ProjectChooser(core.discover_projects(multi_project))
    chooser.ask(Screen([ord("q")]))
    reads.clear()
    chooser.ask(Screen([ord("q")]))
    assert reads == []


def test_r_reads_every_graph_afresh(multi_project, reads, no_curses):
    chooser = tui.ProjectChooser(core.discover_projects(multi_project))
    chooser.ask(Screen([ord("q")]))
    reads.clear()
    chooser.ask(Screen([ord("R"), ord("q")]))
    assert sorted(reads) == ["alpha", "beta"]
