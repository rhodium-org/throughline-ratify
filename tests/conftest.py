# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""A hermetic throughline fixture graph, written fresh into a tmp dir per test so
ratify/reject writes never touch a committed file."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

_CONFIG = textwrap.dedent(
    """
    [project]
    name = "Ratifier Fixture"
    format_version = 3

    [grounding]
    root_types = ["intent", "risk"]
    delivery_roots = ["intent", "risk"]
    ground_link_types = ["derives_from", "mitigates"]
    ai_origins = ["ai", "hybrid"]

    [types.requirement]
    attrs.origin = { type = "enum", values = ["human", "ai", "hybrid"] }

    [links]
    types = ["derives_from", "mitigates", "assumes", "relates"]

    [link_rules]
    derives_from = { from = ["requirement"], to = ["intent"] }
    mitigates    = { from = ["requirement"], to = ["risk"] }

    [status]
    values = ["proposed", "draft", "approved", "ratified", "implemented",
              "verified", "suspect", "rejected", "deleted"]

    [transitions]
    proposed    = ["draft", "approved", "ratified", "rejected", "deleted"]
    draft       = ["approved", "rejected", "deleted"]
    approved    = ["ratified", "implemented", "suspect", "rejected", "deleted"]
    ratified    = ["implemented", "suspect", "rejected", "deleted"]
    implemented = ["verified", "suspect", "rejected", "deleted"]
    suspect     = ["approved", "ratified", "rejected", "deleted"]
    rejected    = ["draft", "deleted"]

    [status.roles]
    initial = "draft"
    proposed = "proposed"
    ratified = "ratified"
    invalidated = "rejected"
    suspect = "suspect"
    tombstone = "deleted"
    """
).lstrip()


def _reg(prefix: str, title: str) -> str:
    return f"prefix: {prefix}\ndigits: 4\ntitle: {title}\n"


# uid, dir, prefix, type, status, title, extra-yaml-body
_ITEMS = [
    ("INT-0001", "intents", "INT", "Intents", "intent", "ratified",
     "Frictionless onboarding", "attrs:\n  source_ref: ASVS-V1.2.3\n"),
    ("RISK-0001", "risks", "RISK", "Risks", "risk", "ratified",
     "Account takeover", ""),
    # grounded + proposed -> ratifiable, concern "proposed"
    ("FR-0001", "requirements", "FR", "Requirements", "requirement", "proposed",
     "Guided setup wizard",
     "links:\n- target: INT-0001\n  type: derives_from\n"),
    # grounded + approved -> ratifiable, concern "ready"; carries a second,
    # informational (non-grounding) link so link removal can be exercised.
    ("FR-0002", "requirements", "FR", "Requirements", "requirement", "approved",
     "Rate-limit login",
     "links:\n- target: RISK-0001\n  type: mitigates\n"
     "- target: FR-0001\n  type: relates\n"),
    # no links -> ungrounded, concern "ungrounded", not ratifiable
    ("FR-0003", "requirements", "FR", "Requirements", "requirement", "proposed",
     "Orphan requirement", ""),
    # grounded but ambiguous -> concern "ambiguous", not ratifiable
    ("FR-0004", "requirements", "FR", "Requirements", "requirement", "proposed",
     "Ambiguous requirement",
     "attrs:\n  ambiguous: true\nlinks:\n- target: INT-0001\n  type: derives_from\n"),
    # already ratified -> excluded unless show_all
    ("FR-0005", "requirements", "FR", "Requirements", "requirement", "ratified",
     "Done requirement",
     "links:\n- target: INT-0001\n  type: derives_from\n"),
    # ratified (carries the stamp) THEN advanced to 'implemented' — must still count
    # as signed off, not reappear as pending just because status left 'ratified'.
    ("FR-0006", "requirements", "FR", "Requirements", "requirement", "implemented",
     "Shipped requirement",
     "attrs:\n  ratified_by: alice\nlinks:\n- target: INT-0001\n  type: derives_from\n"),
    # OVERSHOT: advanced to 'implemented' but NEVER ratified (no stamp). Grounded and
    # unambiguous, so it is 'blocked' — pending but not directly ratifiable — and must
    # carry a config-computed re-ratify route (implemented -> suspect -> ratified ->
    # implemented under the fixture's transitions).
    ("FR-0007", "requirements", "FR", "Requirements", "requirement", "implemented",
     "Overshot requirement",
     "links:\n- target: INT-0001\n  type: derives_from\n"),
    # REJECTED (invalidated) with a recorded reason -> dead: hidden by default,
    # visible under show_all as concern "rejected", never actionable.
    ("FR-0008", "requirements", "FR", "Requirements", "requirement", "rejected",
     "Abandoned requirement",
     "attrs:\n  invalidated_reason: superseded by FR-0002\n"
     "links:\n- target: INT-0001\n  type: derives_from\n"),
    # DELETED (tombstoned) -> dead: hidden by default, visible under show_all as
    # concern "deleted".
    ("FR-0009", "requirements", "FR", "Requirements", "requirement", "deleted",
     "Tombstoned requirement",
     "links:\n- target: INT-0001\n  type: derives_from\n"),
    # STALE: ratified, and stamped with a fingerprint that does not match the content
    # below it — the state throughline's check reports as ratified-stale. It sits at
    # 'ratified', which may always move to itself, so it is directly ratifiable again.
    ("FR-0010", "requirements", "FR", "Requirements", "requirement", "ratified",
     "Rewritten since it was signed",
     f"attrs:\n  ratified_by: alice\n  ratified_fingerprint: sha256:{'0' * 64}\n"
     "links:\n- target: INT-0001\n  type: derives_from\n"),
    # STALE *and* overshot: signed off, rewritten since, and advanced to 'implemented'
    # — so the re-signature has to travel the same round trip FR-0007's missed one does.
    ("FR-0011", "requirements", "FR", "Requirements", "requirement", "implemented",
     "Rewritten since it was signed, and shipped",
     f"attrs:\n  ratified_by: alice\n  ratified_fingerprint: sha256:{'0' * 64}\n"
     "links:\n- target: INT-0001\n  type: derives_from\n"),
]


def _write_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "throughline.toml").write_text(_CONFIG, encoding="utf-8")
    seen_dirs: dict[str, tuple[str, str]] = {}
    for uid, folder, prefix, reg_title, _t, _s, _title, _body in _ITEMS:
        seen_dirs[folder] = (prefix, reg_title)
    for folder, (prefix, reg_title) in seen_dirs.items():
        d = root / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / ".register.yml").write_text(_reg(prefix, reg_title), encoding="utf-8")
    for uid, folder, _prefix, _rt, itype, status, title, body in _ITEMS:
        doc = (
            f"uid: {uid}\n"
            f"type: {itype}\n"
            f"status: {status}\n"
            f"title: {title}\n"
            f"text: Body of {uid}.\n"
            f"normative: true\n"
            f"{body}"
        )
        (root / folder / f"{uid}.yml").write_text(doc, encoding="utf-8")
    return root


@pytest.fixture
def demo_project(tmp_path: Path) -> Path:
    return _write_project(tmp_path / "project")


@pytest.fixture
def in_place_project(tmp_path: Path) -> Path:
    """The same graph in a project that has declared ratification does not move an
    item (throughline SR-0172) — the shape a delivery graph has, where status tracks
    progress and a sign-off is orthogonal to it."""
    root = _write_project(tmp_path / "in-place")
    cfg = root / "throughline.toml"
    cfg.write_text(
        cfg.read_text() + "\n[ratify]\nmoves_status = false\n", encoding="utf-8"
    )
    return root
