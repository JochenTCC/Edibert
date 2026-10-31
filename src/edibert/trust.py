"""Check state and trust level of a tariff-database version (backlog ``0.1.d``, contract v2).

The database keeps per version a check state (``check_state``) and the use status ``reliable``; the trust level
shown to the user is derived from both here and never stored. A checked or supplier-released version whose check
is older than the check interval plus a grace period is shown as "check overdue".
"""

from __future__ import annotations

from datetime import date, timedelta

UNCHECKED = "unchecked"
CHECKED = "checked"
RELEASED_BY_SUPPLIER = "released_by_supplier"
REJECTED = "rejected"
CHECK_STATES = (UNCHECKED, CHECKED, RELEASED_BY_SUPPLIER, REJECTED)
CATALOG_CHECK_STATES = (CHECKED, RELEASED_BY_SUPPLIER)  # the only states a signed catalog package carries

# Trust levels, strongest first (contract v2, "Model").
TRUST_RELEASED = "released_by_supplier"
TRUST_CHECKED = "checked"
TRUST_RELIABLE = "reliable"
TRUST_UNCHECKED = "unchecked"
TRUST_LEVELS = (TRUST_RELEASED, TRUST_CHECKED, TRUST_RELIABLE, TRUST_UNCHECKED)

CHECK_INTERVAL = timedelta(days=91)  # target: a check per quarter
OVERDUE_GRACE = timedelta(days=30)


def trust_level(check_state: str | None, reliable: bool) -> str:
    """Released by supplier > checked > reliable > unchecked. ``None`` (state not known) counts as unchecked;
    a ``rejected`` version is never more than reliable."""
    if check_state == RELEASED_BY_SUPPLIER:
        return TRUST_RELEASED
    if check_state == CHECKED:
        return TRUST_CHECKED
    return TRUST_RELIABLE if reliable else TRUST_UNCHECKED


def check_overdue(check_state: str | None, checked_at: date | None, today: date, *, grid_fee: bool = False) -> bool:
    """True when a checked or supplier-released version needs a new check.

    Overdue after the check interval plus 30 days; a grid fee also once 1 January has passed and the check date
    is from an earlier year (grid fees change at the turn of the year). Other states are never overdue.
    """
    if check_state not in CATALOG_CHECK_STATES or checked_at is None:
        return False
    if today - checked_at > CHECK_INTERVAL + OVERDUE_GRACE:
        return True
    return grid_fee and checked_at.year < today.year
