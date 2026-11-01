# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0089 — f marks a graph as a favourite, kept in the reviewer's own file.

The file is the reviewer's, under their state directory, and nothing about
favourites is written into a project. conftest gives every test a state
directory of its own, so none of this touches the real one.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from test_back_to_the_list import Screen, no_curses  # noqa: F401 - fixture
from throughline_ratify import core, tui


def _pick(multi_project, keys, **kwargs):
    screen = Screen(keys)
    chosen = tui._Picker(screen, core.discover_projects(multi_project), **kwargs).choose()
    return screen, chosen


def _row(screen: Screen, name: str) -> str:
    return next(row for row in screen.rows.values() if name in row)


def test_the_file_is_under_the_reviewers_state_directory(_own_state_directory):
    assert core.favourites_path() == _own_state_directory / "tl-ratify" / "favourites"


@pytest.mark.skipif(os.name == "nt", reason="the XDG convention is not Windows'")
def test_a_relative_state_directory_is_ignored(monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "relative/state")
    assert core.favourites_path() == Path.home() / ".local" / "state" / "tl-ratify" / "favourites"


@pytest.mark.skipif(os.name == "nt", reason="the XDG convention is not Windows'")
def test_an_unset_state_directory_falls_back_to_the_home_one(monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME")
    assert core.favourites_path() == Path.home() / ".local" / "state" / "tl-ratify" / "favourites"


def test_f_stars_the_row_and_the_file_names_the_graph(multi_project, no_curses):
    screen, _ = _pick(multi_project, [ord("j"), ord("f"), ord("q")])
    assert "★ Beta Graph" in _row(screen, "Beta Graph")
    assert "★" not in _row(screen, "Alpha Graph")
    assert core.favourites_path().read_text(encoding="utf-8") == \
        f"{multi_project / 'beta'}\n"
    assert "beta is now a favourite" in screen.painted()


def test_f_again_unmarks_it(multi_project, no_curses):
    screen, _ = _pick(multi_project, [ord("f"), ord("f"), ord("q")])
    assert "★" not in _row(screen, "Alpha Graph")
    assert core.favourites_path().read_text(encoding="utf-8") == ""


def test_marks_are_kept_between_runs(multi_project, no_curses):
    _pick(multi_project, [ord("j"), ord("f"), ord("q")])
    screen, _ = _pick(multi_project, [ord("q")])
    assert "★ Beta Graph" in _row(screen, "Beta Graph")


def test_an_absent_file_is_no_favourites():
    favourites = core.Favourites()
    favourites.load()
    assert favourites.roots == set()


def test_a_mark_another_sitting_made_meanwhile_survives(multi_project):
    mine = core.Favourites()
    mine.load()
    elsewhere = core.Favourites()
    elsewhere.toggle(multi_project / "beta")
    mine.toggle(multi_project / "alpha")
    lines = core.favourites_path().read_text(encoding="utf-8").splitlines()
    assert lines == [str(multi_project / "beta"), str(multi_project / "alpha")]


def test_a_favourite_not_found_is_kept_and_not_shown(multi_project, no_curses, tmp_path):
    elsewhere = tmp_path / "elsewhere" / "idd"
    path = core.favourites_path()
    path.parent.mkdir(parents=True)
    path.write_text(f"{elsewhere}\n", encoding="utf-8")
    screen, _ = _pick(multi_project, [ord("f"), ord("q")])
    assert "elsewhere" not in screen.painted()
    assert path.read_text(encoding="utf-8").splitlines() == [
        str(elsewhere), str(multi_project / "alpha")]


def test_the_file_is_replaced_whole(multi_project):
    core.Favourites().toggle(multi_project / "alpha")
    assert sorted(p.name for p in core.favourites_path().parent.iterdir()) == ["favourites"]


def test_nothing_is_written_into_a_project(multi_project, no_curses):
    before = sorted(p for p in multi_project.rglob("*"))
    _pick(multi_project, [ord("f"), ord("j"), ord("f"), ord("q")])
    assert sorted(p for p in multi_project.rglob("*")) == before


def test_a_file_that_cannot_be_written_leaves_the_mark_and_says_so(multi_project,
                                                                   no_curses, monkeypatch):
    def _refuse(*a):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(core.os, "replace", _refuse)
    screen, chosen = _pick(multi_project, [ord("f"), ord("\n")])
    assert "could not save favourites" in screen.painted()
    assert "★" not in _row(screen, "Alpha Graph")
    assert chosen.name == "Alpha Graph", "the list stays usable"


def test_a_file_that_cannot_be_read_says_so_and_the_list_stays_usable(multi_project,
                                                                      no_curses):
    # A directory where the file should be cannot be read as one.
    core.favourites_path().mkdir(parents=True)
    screen, _ = _pick(multi_project, [ord("q")])
    assert "could not read favourites" in screen.painted()
    _, chosen = _pick(multi_project, [ord("j"), ord("\n")])
    assert chosen.name == "Beta Graph"


def test_f_on_an_empty_list_does_nothing(multi_project, no_curses):
    screen = Screen([ord("f"), ord("q")])
    assert tui._Picker(screen, []).choose() is None
    assert not core.favourites_path().exists()
