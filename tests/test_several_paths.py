# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0088 — -C given more than once offers the graphs beneath every path together.

Each path is resolved as SR-0045 resolves one, so a path behaves inside a list
exactly as it behaves alone; what changes is that the graphs they reach are
asked about in one list, labelled from the directory the paths share.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import _named_project
from test_back_to_the_list import Screen, no_curses  # noqa: F401 - fixture
from throughline_ratify import cli, core, tui


def _label(posix: str) -> str:
    """A label as this platform writes it: labels use its own separator."""
    return str(Path(posix))


@pytest.fixture
def two_trees(tmp_path: Path) -> tuple[Path, Path]:
    """Two sibling repositories, each keeping its graph in idd/ — the shape where
    labelling by the path beneath each tree would show `idd` twice."""
    apps = tmp_path / "apps"
    standards = tmp_path / "standards"
    _named_project(apps / "idd", "Apps Graph")
    _named_project(standards / "idd", "Standards Graph")
    return apps, standards


def test_the_graphs_beneath_every_path_are_offered_together(two_trees):
    apps, standards = two_trees
    with pytest.raises(core.AmbiguousProjectError) as exc:
        core.resolve_root(apps, standards)
    assert [c.name for c in exc.value.candidates] == ["Apps Graph", "Standards Graph"]
    assert exc.value.several


def test_each_graph_is_labelled_from_the_directory_the_paths_share(two_trees):
    apps, standards = two_trees
    with pytest.raises(core.AmbiguousProjectError) as exc:
        core.resolve_root(apps, standards)
    assert [c.rel for c in exc.value.candidates] == [_label("apps/idd"), _label("standards/idd")]
    assert exc.value.base == apps.parent


def test_a_graph_two_paths_reach_is_offered_once(multi_project):
    with pytest.raises(core.AmbiguousProjectError) as exc:
        core.resolve_root(multi_project, multi_project / "alpha", multi_project)
    assert [c.name for c in exc.value.candidates] == ["Alpha Graph", "Beta Graph"]


def test_exactly_one_graph_between_the_paths_is_opened(multi_project):
    alpha = multi_project / "alpha"
    assert core.resolve_root(alpha, alpha / "requirements") == alpha


def test_a_path_that_is_a_graph_contributes_itself_alone(multi_project, two_trees):
    """SR-0045 for each path: naming a graph settles that path, and nothing
    beneath it is searched."""
    apps, _ = two_trees
    nested = multi_project / "alpha" / "vendored"
    _named_project(nested, "Vendored Graph")
    with pytest.raises(core.AmbiguousProjectError) as exc:
        core.resolve_root(multi_project / "alpha", apps)
    assert [c.name for c in exc.value.candidates] == ["Alpha Graph", "Apps Graph"]


def test_a_path_with_nothing_beneath_still_walks_upward(multi_project, two_trees):
    apps, _ = two_trees
    with pytest.raises(core.AmbiguousProjectError) as exc:
        core.resolve_root(multi_project / "alpha" / "requirements", apps)
    assert [c.name for c in exc.value.candidates] == ["Alpha Graph", "Apps Graph"]


def test_a_path_that_reaches_no_graph_is_refused_by_name(two_trees, tmp_path):
    apps, _ = two_trees
    empty = tmp_path / "nothing-here"
    empty.mkdir()
    with pytest.raises(core.RatifierError) as exc:
        core.resolve_root(apps, empty)
    assert str(empty) in str(exc.value)
    assert not isinstance(exc.value, core.AmbiguousProjectError)


def test_the_cli_refuses_a_path_that_reaches_nothing(two_trees, tmp_path, capsys):
    apps, _ = two_trees
    empty = tmp_path / "nothing-here"
    empty.mkdir()
    assert cli.main(["-C", str(apps), "-C", str(empty), "--list"]) == 2
    err = capsys.readouterr().err
    assert str(empty) in err and "Traceback" not in err


def test_list_over_several_paths_refuses_with_commands_that_work(two_trees, capsys):
    """A label is relative to the shared directory, not to where the command
    runs, so the command printed names each graph in full."""
    apps, standards = two_trees
    rc = cli.main(["-C", str(apps), "-C", str(standards), "--list"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "beneath the paths given" in err
    assert f"tl-ratify -C {apps / 'idd'}" in err
    assert f"tl-ratify -C {standards / 'idd'}" in err


def test_the_cli_opens_the_graph_picked_from_several_paths(two_trees, monkeypatch):
    apps, standards = two_trees
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    handed = {}

    def _work_through(candidates, open_graph, search=None, several=False, **k):
        handed.update(names=[c.name for c in candidates], several=several,
                      again=[c.rel for c in search()])

    monkeypatch.setattr(tui, "work_through", _work_through)
    assert cli.main(["-C", str(apps), "-C", str(standards), "--by", "Ada"]) == 0
    assert handed == {"names": ["Apps Graph", "Standards Graph"], "several": True,
                      "again": [_label("apps/idd"), _label("standards/idd")]}


def test_a_reload_searches_beneath_every_path(two_trees):
    apps, standards = two_trees
    _named_project(standards / "extra", "Extra Graph")
    found = cli._search_beneath(apps, standards)
    assert [c.rel for c in found] == [_label("apps/idd"), _label("standards/extra"), _label("standards/idd")]


def test_a_reload_after_one_path_has_gone_keeps_the_others_labels(two_trees):
    apps, standards = two_trees
    shutil.rmtree(standards)
    found = cli._search_beneath(apps, standards)
    assert [c.rel for c in found] == [_label("apps/idd")]


def test_the_screen_says_the_graphs_lie_beneath_the_paths_given(two_trees, no_curses):
    apps, standards = two_trees
    screen = Screen([ord("q")])
    tui._Picker(screen, core.discover_projects(apps, standards), several=True).choose()
    assert "lie beneath the paths you gave" in screen.painted()


def test_one_path_reads_as_it_always_did(multi_project, no_curses):
    screen = Screen([ord("q")])
    tui._Picker(screen, core.discover_projects(multi_project)).choose()
    assert "lie beneath the path you gave" in screen.painted()
    assert cli.build_parser().parse_args([]).path is None
