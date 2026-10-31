"""Trust level and "check overdue" of tariff-database versions (0.1.d, contract v2)."""

from datetime import date

import pytest

from edibert import api


@pytest.mark.parametrize(
    ("state", "reliable", "level"),
    [
        ("released_by_supplier", False, "released_by_supplier"),
        ("checked", True, "checked"),
        ("unchecked", True, "reliable"),
        ("rejected", True, "reliable"),
        ("unchecked", False, "unchecked"),
        (None, False, "unchecked"),
    ],
)
def test_trust_level_order(state, reliable, level):
    assert api.trust_level(state, reliable) == level
    assert level in api.TRUST_LEVELS


def test_check_overdue_after_interval_plus_30_days():
    checked = date(2026, 1, 10)
    assert not api.check_overdue("checked", checked, date(2026, 5, 11))  # 121 days
    assert api.check_overdue("checked", checked, date(2026, 5, 12))
    assert api.check_overdue("released_by_supplier", checked, date(2026, 6, 1))
    assert not api.check_overdue("unchecked", checked, date(2027, 6, 1))
    assert not api.check_overdue("checked", None, date(2027, 6, 1))


def test_grid_fees_are_overdue_once_the_year_turned():
    assert not api.check_overdue("checked", date(2026, 12, 20), date(2027, 1, 5))
    assert api.check_overdue("checked", date(2026, 12, 20), date(2027, 1, 5), grid_fee=True)
    assert not api.check_overdue("checked", date(2027, 1, 2), date(2027, 1, 5), grid_fee=True)
