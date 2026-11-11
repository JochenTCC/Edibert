"""Tariff overview model (Editor P4b): selection kept by row key, and which action fits the selection."""

import json
from datetime import date

import pytest

from edibert.editor.catalog import read_catalog
from edibert.editor.overview import (
    COMPARE_LIMIT,
    Action,
    Origin,
    OverviewFilter,
    build_rows,
    copies,
    filter_rows,
    merge_selection,
    prune_selection,
    refusal,
    rows_of,
    selected_positions,
    selection_stamp,
)
from edibert.tariff import IMPORT, parse_tariff

TODAY = date(2026, 11, 11)


def entry(tariff_id: str, label: str, **extra) -> dict:
    """A placeholder tariff (no real supplier data)."""
    return {"id": tariff_id, "label": label, "type": "fixed_cent", "land": "AT", "supplier_id": f"s_{tariff_id}",
            "fix_cent_kwh": 20.0, "vat_percent": 20, **extra}  # fmt: skip


@pytest.fixture
def rows(tmp_path):
    path = tmp_path / "tariffs.json"
    catalog = [entry(f"at_{name}", name.title()) for name in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta")]
    path.write_text(json.dumps({"tariff_format": 1, "import_tariffs": catalog}), encoding="utf-8")
    user = {"tariff_format": 1, "import_tariffs": [entry("user_own", "Own", supplier_id="user_me"),
                                                   entry("user_two", "Two", supplier_id="user_me")]}  # fmt: skip
    return build_rows(IMPORT, user, read_catalog(path, TODAY))


def pick(rows, *labels):
    return [row for row in rows if row.tariff.label in labels]


def keys(rows, *labels):
    return {row.key for row in pick(rows, *labels)}


def test_the_stamp_changes_with_the_shown_rows_only(rows):
    assert selection_stamp(rows) == selection_stamp(list(rows))
    assert selection_stamp(rows) != selection_stamp(rows[1:])
    assert selection_stamp(rows) != selection_stamp(list(reversed(rows)))


def test_selection_survives_a_filter_change_by_key(rows):
    selected = merge_selection(set(), rows, [2, 3])  # Alpha, Beta
    assert selected == {"catalog:at_alpha", "catalog:at_beta"}
    shown = filter_rows(rows, OverviewFilter(text="beta"))
    assert selected_positions(shown, selected) == [0]
    after = merge_selection(selected, shown, [])  # the user unselects Beta; the hidden Alpha stays
    assert after == {"catalog:at_alpha"}
    assert selected_positions(rows, after) == [2]


def test_a_position_outside_the_shown_rows_fails_loud(rows):
    with pytest.raises(ValueError, match="not among"):
        merge_selection(set(), rows[:2], [2])


def test_prune_drops_rows_that_are_gone(rows):
    assert prune_selection({"own:user_own", "own:user_deleted"}, rows) == {"own:user_own"}
    assert [row.key for row in rows_of(rows, {"catalog:at_beta", "own:user_two"})] == ["own:user_two", "catalog:at_beta"]


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ((), {"open": "open_one_own", "copy": "copy_not_own", "delete": "delete_own_only"}),
        (("Own",), {"open": None, "copy": "copy_not_own", "delete": None}),
        (("Own", "Two"), {"open": "open_one_own", "copy": "copy_not_own", "delete": None}),
        (("Alpha",), {"open": "open_one_own", "copy": None, "delete": "delete_own_only"}),
        (("Alpha", "Beta"), {"open": "open_one_own", "copy": None, "delete": "delete_own_only"}),
        (("Own", "Alpha"), {"open": "open_one_own", "copy": "copy_not_own", "delete": "delete_own_only"}),
    ],
)
def test_which_action_fits_the_selection(rows, labels, expected):
    chosen = pick(rows, *labels)
    assert {str(action): refusal(action, chosen) for action in Action} == expected


def test_compare_is_no_action_and_takes_at_most_five():
    assert COMPARE_LIMIT == 5
    assert "compare" not in {str(action) for action in Action}  # shown with the selection, no button


def test_copies_get_ids_unique_among_own_tariffs_and_each_other(rows):
    chosen = pick(rows, "Alpha", "Beta")
    made = copies(chosen, {"user_at_alpha"}, "(copy)", lambda row: None)
    assert [(raw["id"], raw["label"]) for raw in made] == [("user_at_alpha_2", "Alpha (copy)"), ("user_at_beta", "Beta (copy)")]
    for raw in made:
        parse_tariff(raw, IMPORT)  # each copy is a valid own tariff
    twice = copies(pick(rows, "Alpha") * 2, set(), "(copy)", lambda row: None)
    assert [raw["id"] for raw in twice] == ["user_at_alpha", "user_at_alpha_2"]
    with pytest.raises(ValueError, match="copy_not_own"):
        copies(pick(rows, "Own"), set(), "(copy)", lambda row: None)


def test_a_copy_carries_the_database_reference_it_is_given(rows):
    ref = {"id": "AT/import/at_alpha", "version": "a" * 64}
    (made,) = copies(pick(rows, "Alpha"), set(), "(copy)", lambda row: ref if row.origin == Origin.CATALOG else None)
    assert made["db_ref"] == ref
