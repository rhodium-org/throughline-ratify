# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""SR-0072 — the graph names the tests that check each requirement, and the suite
fails when a named test is missing.

A list of test names kept by hand goes stale the first time a test is renamed,
so the suite reads the list and compares it with itself. The comparison is three
plain functions over plain data, tested here against lists that are wrong in
each way, and then run once over this repository's own graph and suite.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
GRAPH = REPO / "idd"

# Test functions that check no requirement of this project. These cover an
# upstream clause, throughline SR-0172, that this graph does not restate.
NO_REQUIREMENT_HERE = {
    "tests/test_ratify_in_place.py::test_default_still_needs_the_round_trip",
    "tests/test_ratify_in_place.py::test_in_place_makes_an_overshot_item_directly_ratifiable",
    "tests/test_ratify_in_place.py::test_in_place_sign_off_leaves_the_status_where_it_was",
    "tests/test_ratify_in_place.py::test_in_place_sign_off_settles_the_item",
    "tests/test_ratify_in_place.py::test_in_place_does_not_read_the_ratified_status_as_a_signature",
    "tests/test_ratify_in_place.py::test_in_place_leaves_the_ungrounded_and_ambiguous_gates_alone",
}

DEAD = {"rejected", "deleted"}


def suite_functions(tests_dir: Path) -> set[str]:
    """Every test function in the suite, as ``tests/<file>::<function>``."""
    found = set()
    for path in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found |= {f"tests/{path.name}::{node.name}" for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name.startswith("test")}
    return found


def graph_items(graph: Path) -> dict[str, dict]:
    """Every item in the graph's own registers, by UID."""
    items = {}
    for path in graph.glob("*/*.yml"):
        if path.name.startswith("."):
            continue
        item = yaml.safe_load(path.read_text(encoding="utf-8"))
        items[item["uid"]] = item
    return items


def named(item: dict) -> list[str]:
    return (item.get("attrs", {}).get("checks") or "").split()


def names_that_do_not_exist(items: dict, functions: set[str]) -> list[str]:
    return sorted(f"{uid} names {name}, which is not a test in the suite"
                  for uid, item in items.items() if item["type"] == "test"
                  for name in named(item) if name not in functions)


def items_that_verify_nothing_live(items: dict) -> list[str]:
    problems = []
    for uid, item in items.items():
        if item["type"] != "test" or item["status"] in DEAD:
            continue
        targets = [ln["target"] for ln in item.get("links", []) if ln["type"] == "verifies"]
        live = [t for t in targets if t in items and items[t]["status"] not in DEAD]
        if not live:
            problems.append(f"{uid} verifies no live requirement")
        if not named(item):
            problems.append(f"{uid} names no test")
    return sorted(problems)


def functions_no_item_names(items: dict, functions: set[str], exempt: set[str]) -> list[str]:
    claimed = {name for item in items.values() if item["type"] == "test"
               and item["status"] not in DEAD for name in named(item)}
    return sorted(f"{name} is named by no test item" for name in functions - claimed - exempt)


# --------------------------------------------------------------------------- #
# The comparison, against lists that are wrong in each way
# --------------------------------------------------------------------------- #

def _graph(**over):
    items = {
        "SR-0001": {"uid": "SR-0001", "type": "system_requirement", "status": "ratified"},
        "TEST-0001": {"uid": "TEST-0001", "type": "test", "status": "ratified",
                      "links": [{"target": "SR-0001", "type": "verifies"}],
                      "attrs": {"checks": "tests/test_a.py::test_one\ntests/test_a.py::test_two"}},
    }
    for uid, change in over.items():
        items[uid.replace("_", "-")] = {**items.get(uid.replace("_", "-"), {}), **change}
    return items


FUNCTIONS = {"tests/test_a.py::test_one", "tests/test_a.py::test_two"}


def test_a_graph_that_agrees_with_its_suite_has_nothing_to_report():
    items = _graph()
    assert names_that_do_not_exist(items, FUNCTIONS) == []
    assert items_that_verify_nothing_live(items) == []
    assert functions_no_item_names(items, FUNCTIONS, set()) == []


def test_a_renamed_test_is_reported_against_the_item_that_names_it():
    renamed = {"tests/test_a.py::test_one", "tests/test_a.py::test_second"}
    assert names_that_do_not_exist(_graph(), renamed) == [
        "TEST-0001 names tests/test_a.py::test_two, which is not a test in the suite"]


def test_a_new_test_that_no_item_names_is_reported():
    more = FUNCTIONS | {"tests/test_b.py::test_new"}
    assert functions_no_item_names(_graph(), more, set()) == [
        "tests/test_b.py::test_new is named by no test item"]


def test_a_test_listed_as_checking_no_requirement_here_is_not_reported():
    more = FUNCTIONS | {"tests/test_b.py::test_upstream"}
    assert functions_no_item_names(_graph(), more, {"tests/test_b.py::test_upstream"}) == []


def test_an_item_whose_requirement_was_rejected_is_reported():
    items = _graph(SR_0001={"status": "rejected"})
    assert items_that_verify_nothing_live(items) == ["TEST-0001 verifies no live requirement"]


def test_an_item_whose_requirement_is_not_in_the_graph_is_reported():
    items = _graph(TEST_0001={"links": [{"target": "SR-0999", "type": "verifies"}]})
    assert items_that_verify_nothing_live(items) == ["TEST-0001 verifies no live requirement"]


def test_an_item_that_names_no_test_is_reported():
    items = _graph(TEST_0001={"attrs": {}})
    assert items_that_verify_nothing_live(items) == ["TEST-0001 names no test"]


def test_a_dead_item_claims_nothing_and_is_asked_nothing():
    items = _graph(TEST_0001={"status": "rejected"})
    assert items_that_verify_nothing_live(items) == []
    assert len(functions_no_item_names(items, FUNCTIONS, set())) == 2


# --------------------------------------------------------------------------- #
# This repository's own graph and suite
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def own():
    if not (GRAPH / "tests").is_dir():
        # The published sdist ships the suite and not the graph (SR-0040), so
        # there is nothing to compare the suite with when it runs from there.
        pytest.skip("this copy of the suite was shipped without the graph")
    return graph_items(GRAPH), suite_functions(REPO / "tests")


def test_every_test_the_graph_names_exists(own):
    items, functions = own
    assert names_that_do_not_exist(items, functions) == []


def test_every_test_item_verifies_a_live_requirement_and_names_a_test(own):
    items, _ = own
    assert items_that_verify_nothing_live(items) == []


def test_every_test_in_the_suite_is_named_by_an_item(own):
    items, functions = own
    assert functions_no_item_names(items, functions, NO_REQUIREMENT_HERE) == []


def test_the_tests_listed_as_checking_no_requirement_here_all_exist(own):
    _, functions = own
    assert NO_REQUIREMENT_HERE <= functions
