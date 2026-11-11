"""Tariff overview (Editor P4, concept "tariff overview" 2026-11-11): rows, columns, filters and price basis (no UI).

One table per direction lists every tariff at hand: the own tariffs of ``user_tariffs.json``, the catalog
(only the version valid today, as ``read_catalog`` picks it) and, later, loaded templates. Values come from
the parsed :class:`~edibert.tariff.Tariff`, so a tariff the engine rejects is rejected here as well.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from edibert.editor.catalog import CatalogEntry, applies_to_region, type_key
from edibert.editor.userstore import SECTIONS, copy_as_template
from edibert.exchange import Template
from edibert.tariff import EXPORT, IMPORT, DbRef, Tariff, parse_tariff
from edibert.trust import trust_level


class Origin(StrEnum):
    """Where a row comes from. ``TEMPLATE`` rows (templates loaded from the tariff database) follow in P4c."""

    OWN = "own"
    CATALOG = "catalog"
    TEMPLATE = "template"


class Basis(StrEnum):
    """The one basis all price columns of a table are shown on."""

    GROSS = "gross"
    NET = "net"


class Unit(StrEnum):
    """What a column holds; the UI picks the column type and number format from it."""

    TEXT = "text"  # plain text (label, supplier, land, regions)
    CODE = "code"  # a code the UI translates (origin, price kind, requirements, check state)
    CENT = "cent"  # cent/kWh on the chosen basis
    EUR_MONTH = "eur_month"  # EUR per month on the chosen basis
    PERCENT = "percent"
    COUNT = "count"
    DATE = "date"


@dataclass(frozen=True)
class Column:
    id: str
    unit: Unit
    default: bool  # shown in the default view; the others on request


_HEAD = (
    Column("label", Unit.TEXT, True),
    Column("supplier", Unit.TEXT, True),
    Column("origin", Unit.CODE, True),
    Column("kind", Unit.CODE, True),
)
_DIRECTION_COLUMNS = {
    IMPORT: (
        Column("base_price", Unit.CENT, True),  # fixed price or this month's rate; empty for market prices
        Column("markup_percent", Unit.PERCENT, True),  # market prices only
        Column("markup_cent", Unit.CENT, True),  # market prices only (``settlement_fee_cent_kwh``)
    ),
    EXPORT: (
        Column("remuneration", Unit.CENT, True),  # fixed price or this month's rate; empty for market prices
        Column("market_factor", Unit.PERCENT, True),  # ``feed_in_fee_factor`` in percent of |market price|
        Column("fixed_deduction", Unit.CENT, True),  # ``settlement_fee_cent_kwh``, subtracted
        Column("fixed_addition", Unit.CENT, False),  # ``feed_in_fix_cent``, added
    ),
}
_TAIL = (
    Column("monthly_fee", Unit.EUR_MONTH, True),
    Column("land", Unit.TEXT, False),
    Column("regions", Unit.TEXT, False),
    Column("time_rules", Unit.COUNT, False),
    Column("price_floor", Unit.CENT, False),
    Column("price_cap", Unit.CENT, False),
    Column("requires", Unit.CODE, False),
    Column("valid_from", Unit.DATE, False),
    Column("valid_to", Unit.DATE, False),
    Column("last_verified", Unit.DATE, False),
    Column("check", Unit.CODE, True),  # check state of a catalog entry, trust level of a template
)


def columns(direction: str) -> tuple[Column, ...]:
    """The columns of the ``direction`` table, in display order."""
    if direction not in _DIRECTION_COLUMNS:
        raise ValueError(f"direction must be '{IMPORT}' or '{EXPORT}', got '{direction}'.")
    return (*_HEAD, *_DIRECTION_COLUMNS[direction], *_TAIL)


@dataclass(frozen=True)
class OverviewRow:
    """One tariff in the table: where it comes from, the stored entry and the parsed tariff.

    Template rows also carry their database reference (the copy keeps it), their trust level and whether the
    database knows a checked version of the same tariff.
    """

    origin: Origin
    raw: Mapping[str, Any]
    tariff: Tariff
    db_ref: DbRef | None = None
    trust: str | None = None
    checked_version_exists: bool = False

    @property
    def key(self) -> str:
        """Stable row ID (``origin:id``): the same ID can exist as own tariff, catalog entry and template."""
        return f"{self.origin}:{self.tariff.id}"

    @property
    def kind(self) -> str:
        """Price kind in the editor's wording (``fixed``, ``spot:15min``, ``spot:60min``, ``monthly``)."""
        return type_key(self.raw, self.tariff.direction)


def _row(origin: Origin, raw: Mapping[str, Any], direction: str) -> OverviewRow:
    return OverviewRow(origin, raw, parse_tariff(raw, direction))


def template_row(template: Template) -> OverviewRow:
    """A loaded template as a row: the payload tariff under the local part of its database ID (as the copy names
    it), parsed strictly; an invalid template raises."""
    parts = template.db_id.split("/", 2)
    if len(parts) != 3 or not parts[2]:
        raise ValueError(f"Template database ID '{template.db_id}' is not '<land>/<direction>/<id>'.")
    raw = {**template.tariff, "id": parts[2]}
    return OverviewRow(
        Origin.TEMPLATE, raw, parse_tariff(raw, template.direction), db_ref=template.db_ref,
        trust=trust_level(template.check_state, template.reliable),
        checked_version_exists=template.latest_checked_version is not None,
    )  # fmt: skip


def build_rows(
    direction: str,
    user_document: Mapping[str, Any],
    catalog: Iterable[CatalogEntry] = (),
    templates: Iterable[OverviewRow] = (),
) -> list[OverviewRow]:
    """Own tariffs (file order), the catalog entries of ``direction`` (as ``read_catalog`` returns them), then the
    template rows of ``direction`` (see :func:`template_row`).

    Every entry is parsed; an invalid or unsupported one raises (no row is dropped silently).
    """
    columns(direction)  # checks the direction
    rows = [_row(Origin.OWN, raw, direction) for raw in user_document.get(SECTIONS[direction], [])]
    rows.extend(_row(Origin.CATALOG, entry.raw, direction) for entry in catalog if entry.direction == direction)
    for row in templates:
        if row.origin != Origin.TEMPLATE:
            raise ValueError(f"Row '{row.key}' passed as template.")
        if row.tariff.direction == direction:
            rows.append(row)
    return rows


@dataclass(frozen=True)
class OverviewFilter:
    """The filters above one table; ``None`` / empty = any.

    ``land``: tariffs of that land; a tariff without a land states no restriction and is kept.
    ``region_only``: drop tariffs whose ``regions`` exclude the house region (needs ``house_land``/``house_region``).
    """

    land: str | None = None
    kind: str | None = None
    origin: Origin | None = None
    text: str = ""
    region_only: bool = True
    house_land: str | None = None
    house_region: str | None = None


def _matches(row: OverviewRow, chosen: OverviewFilter) -> bool:
    tariff = row.tariff
    needle = chosen.text.strip().casefold()
    return (
        (chosen.land is None or tariff.land in (None, chosen.land))
        and (chosen.kind is None or row.kind == chosen.kind)
        and (chosen.origin is None or row.origin == chosen.origin)
        and (not needle or needle in tariff.label.casefold() or needle in tariff.supplier_id.casefold())
        and (not chosen.region_only or applies_to_region(tariff.regions, tariff.land, chosen.house_land, chosen.house_region))
    )


def filter_rows(rows: Iterable[OverviewRow], chosen: OverviewFilter) -> list[OverviewRow]:
    """The rows that pass every filter, in their order."""
    return [row for row in rows if _matches(row, chosen)]


def lands_of(rows: Iterable[OverviewRow]) -> list[str]:
    return sorted({row.tariff.land for row in rows if row.tariff.land})


def kinds_of(rows: Iterable[OverviewRow]) -> list[str]:
    """Price kinds present, in the order of the editor's price kinds."""
    present = {row.kind for row in rows}
    return [key for key in ("fixed", "spot:15min", "spot:60min", "monthly") if key in present]


def on_basis(value: float | None, tariff: Tariff, basis: Basis) -> float | None:
    """A price of ``tariff`` (stored gross or net, ``prices_include_vat``) on ``basis``, with its ``vat_percent``."""
    if value is None:
        return None
    if basis not in (Basis.GROSS, Basis.NET):
        raise ValueError(f"Unknown price basis '{basis}'.")
    factor = 1.0 + tariff.vat_percent / 100.0
    if tariff.prices_include_vat == (basis == Basis.GROSS):
        return value
    return value * factor if basis == Basis.GROSS else value / factor


def month_value(tariff: Tariff, today: date) -> float | None:
    """Rate of a monthly table for the month of ``today``, as stored; ``None`` if that month is missing.

    Exactly this month: the table shows no other month's rate in its place (the engine's fallback with a
    warning belongs to pricing, not to a parameter column).
    """
    if tariff.type != "monthly_table":
        raise ValueError(f"Tariff '{tariff.id}' is no monthly table.")
    return tariff.monthly_rates.get((today.year, today.month))


@dataclass(frozen=True)
class RowValues:
    """Cell values of one row by column ID; ``month_missing`` is set when a monthly table lacks this month."""

    values: dict[str, Any]
    month_missing: bool = False


def _price(row: OverviewRow, today: date) -> tuple[float | None, bool]:
    """Base price (import) or remuneration (export) as stored, and whether this month's rate is missing."""
    tariff = row.tariff
    if tariff.is_spot:
        return None, False
    if tariff.type == "monthly_table":
        value = month_value(tariff, today)
        return value, value is None
    fixed = tariff.fix_cent_kwh if tariff.direction == IMPORT else tariff.k_push_cent
    if fixed is None:  # parse_tariff requires it; reaching this means the model changed
        raise ValueError(f"Tariff '{tariff.id}' has no fixed price.")
    return fixed, False


def row_values(row: OverviewRow, basis: Basis, today: date) -> RowValues:
    """All cells of ``row`` with prices and fees on ``basis``; market-price parameters only for market tariffs."""
    tariff = row.tariff
    spot = tariff.is_spot
    price, month_missing = _price(row, today)
    values: dict[str, Any] = {
        "label": tariff.label,
        "supplier": tariff.supplier_id,
        "origin": str(row.origin),
        "kind": row.kind,
        "monthly_fee": on_basis(sum(tariff.fees.values()), tariff, basis) if tariff.fees else None,
        "land": tariff.land,
        "regions": ", ".join(tariff.regions) or None,
        "time_rules": len(tariff.rules),
        "price_floor": on_basis(tariff.price_floor_cent_kwh, tariff, basis),
        "price_cap": on_basis(tariff.price_cap_cent_kwh, tariff, basis),
        "requires": list(tariff.requires),
        "valid_from": tariff.valid_from,
        "valid_to": tariff.valid_to,
        "last_verified": tariff.last_verified,
        "check": row.trust if row.trust is not None else (tariff.check.state if tariff.check is not None else None),
    }
    if tariff.direction == IMPORT:
        values["base_price"] = on_basis(price, tariff, basis)
        values["markup_percent"] = tariff.markup_percent if spot else None
        values["markup_cent"] = on_basis(tariff.settlement_fee_cent_kwh, tariff, basis) if spot else None
    else:
        values["remuneration"] = on_basis(price, tariff, basis)
        values["market_factor"] = tariff.feed_in_fee_factor * 100.0 if spot else None
        values["fixed_deduction"] = on_basis(tariff.settlement_fee_cent_kwh, tariff, basis) if spot else None
        values["fixed_addition"] = on_basis(tariff.feed_in_fix_cent, tariff, basis) if spot else None
    expected = {column.id for column in columns(tariff.direction)}
    if set(values) != expected:  # a column without a value (or the other way round) is a programming error
        raise ValueError(f"Overview columns and values differ: {sorted(set(values) ^ expected)}.")
    return RowValues(values, month_missing)


def counts(rows: Iterable[OverviewRow]) -> dict[Origin, int]:
    """Rows per origin (for the tab titles)."""
    result = dict.fromkeys(Origin, 0)
    for row in rows:
        result[row.origin] += 1
    return result


DIRECTIONS = (IMPORT, EXPORT)
COMPARE_LIMIT = 5  # at most this many tariffs in the comparison; more is refused, never cut silently


# --- Selection (kept by row key, not by table position: a filter changes the positions) ---


def selection_stamp(shown: Sequence[OverviewRow]) -> str:
    """Short hash of the shown row keys in order: part of the table's widget key, so every other set of
    rows (filter, new or deleted tariff) starts a fresh table widget instead of reusing old positions."""
    return hashlib.sha1("|".join(row.key for row in shown).encode("utf-8")).hexdigest()[:10]


def selected_positions(shown: Sequence[OverviewRow], selected: Iterable[str]) -> list[int]:
    """Positions of the selected keys among the shown rows (the table's default selection)."""
    keys = set(selected)
    return [index for index, row in enumerate(shown) if row.key in keys]


def merge_selection(selected: Iterable[str], shown: Sequence[OverviewRow], picked: Iterable[int]) -> set[str]:
    """The selection after a run: the shown rows count as the table says, selected rows the filters hide stay.

    A position outside ``shown`` is an error: it would select a row the user never saw.
    """
    visible = {row.key for row in shown}
    chosen: set[str] = set()
    for index in picked:
        if not 0 <= index < len(shown):
            raise ValueError(f"Selected row {index} is not among the {len(shown)} shown rows.")
        chosen.add(shown[index].key)
    return {key for key in selected if key not in visible} | chosen


def prune_selection(selected: Iterable[str], rows: Iterable[OverviewRow]) -> set[str]:
    """Drop keys of rows that no longer exist (a deleted tariff, a catalog entry gone after a package import)."""
    existing = {row.key for row in rows}
    return {key for key in selected if key in existing}


def rows_of(rows: Iterable[OverviewRow], selected: Iterable[str]) -> list[OverviewRow]:
    """The selected rows in table order."""
    keys = set(selected)
    return [row for row in rows if row.key in keys]


# --- Actions on the selection ---


class Action(StrEnum):
    OPEN = "open"
    COPY = "copy"
    DELETE = "delete"
    COMPARE = "compare"


def refusal(action: Action, chosen: Sequence[OverviewRow]) -> str | None:
    """Why ``action`` does not fit the selection (a code the UI translates), or ``None`` when it does.

    open: exactly one own tariff. copy: one or more tariffs that are not own (catalog, template).
    delete: one or more own tariffs. compare: one to ``COMPARE_LIMIT`` tariffs of any origin.
    """
    own = [row for row in chosen if row.origin == Origin.OWN]
    if action == Action.OPEN:
        return None if len(chosen) == 1 and len(own) == 1 else "open_one_own"
    if action == Action.COPY:
        return None if chosen and not own else "copy_not_own"
    if action == Action.DELETE:
        return None if chosen and len(own) == len(chosen) else "delete_own_only"
    if action == Action.COMPARE:
        if not chosen:
            return "compare_none"
        return None if len(chosen) <= COMPARE_LIMIT else "compare_limit"
    raise ValueError(f"Unknown overview action '{action}'.")


def require(action: Action, chosen: Sequence[OverviewRow]) -> None:
    """Fail loud when an action is run on a selection it does not fit (the UI disables it first)."""
    reason = refusal(action, chosen)
    if reason is not None:
        raise ValueError(f"Action '{action}' does not fit the selection ({reason}).")


def copies(
    chosen: Sequence[OverviewRow],
    taken: Iterable[str],
    label_suffix: str,
    db_ref: Callable[[OverviewRow], Mapping[str, str] | None],
) -> list[dict[str, Any]]:
    """Own copies of the selected catalog tariffs (or templates), with IDs unique among ``taken`` and each other.

    ``db_ref(row)``: the database reference the copy carries (``None`` for a catalog that is no package).
    """
    require(Action.COPY, chosen)
    used = set(taken)
    result = []
    for row in chosen:
        copy = copy_as_template(row.raw, used, label_suffix, db_ref(row))
        used.add(copy["id"])
        result.append(copy)
    return result
