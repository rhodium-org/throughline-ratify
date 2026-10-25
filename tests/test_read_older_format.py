# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0081: a graph at an older on-disk format opens read-only and is never written."""
from __future__ import annotations

from pathlib import Path

import pytest

from throughline_ratify import core


def _files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def format3_project(demo_project: Path) -> Path:
    config = demo_project / "throughline.toml"
    config.write_text(config.read_text(encoding="utf-8").replace("format_version = 4", "format_version = 3"), encoding="utf-8")
    return demo_project


def test_an_older_graph_is_still_refused_without_read_only(format3_project):
    with pytest.raises(core.RatifierError, match="tl migrate"):
        core.open_session(format3_project)


def test_an_older_graph_opens_read_only_with_read_older_and_lists_its_items(format3_project):
    session = core.open_session(format3_project, read_older=True)
    assert session.read_only and session.older_format == 3
    queue = core.build_queue(session, show_all=True)
    assert {"FR-0001", "FR-0002", "INT-0001"} <= {q.uid for q in queue}


@pytest.mark.parametrize("write", [
    lambda s: core.ratify_item(s, "FR-0001", by="tester"),
    lambda s: core.reratify_item(s, "FR-0007", by="tester"),
    lambda s: core.reject_item(s, "FR-0002", reason="not needed"),
    lambda s: core.remove_link(s, "FR-0001", 0),
], ids=["ratify", "reratify", "reject", "remove-link"])
def test_every_write_to_an_older_graph_is_refused_and_names_migrate(format3_project, write):
    before = _files(format3_project)
    session = core.open_session(format3_project, read_older=True)
    with pytest.raises(core.ReadOnlySessionError, match="format version 3.*tl migrate"):
        write(session)
    assert _files(format3_project) == before


def test_a_current_graph_opened_with_read_older_is_written_as_always(demo_project):
    session = core.open_session(demo_project, read_older=True)
    assert not session.read_only and session.older_format is None
    core.ratify_item(session, "FR-0001", by="tester")
    assert core.open_session(demo_project).project.get("FR-0001").status == "ratified"


def test_reading_again_keeps_the_session_read_only(format3_project):
    session = core.reopen(core.open_session(format3_project, read_older=True))
    assert session.read_only and session.older_format == 3
    with pytest.raises(core.ReadOnlySessionError):
        core.ratify_item(session, "FR-0001", by="tester")
