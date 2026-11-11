"""Tariff overview (Editor P4a): one read-only table per direction with filters and a gross/net switch.

The rows, columns, filters and the price basis come from :mod:`edibert.editor.overview`; this module only
translates and draws them. Selection and actions follow in P4b.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import streamlit as st

from edibert.editor.catalog import read_catalog
from edibert.editor.overview import (
    DIRECTIONS,
    Basis,
    Column,
    Origin,
    OverviewFilter,
    OverviewRow,
    Unit,
    build_rows,
    columns,
    counts,
    filter_rows,
    kinds_of,
    lands_of,
    row_values,
)
from edibert.editor.userstore import read_document
from edibert.i18n import Translator
from edibert.ui import state
from edibert.ui.config import UiConfig
from edibert.ui.number_columns import localized_number_column

ALL = ""  # the "all" option of a filter
PRICE_COLUMNS = {"base_price", "remuneration"}  # hold this month's rate for monthly tables


def kind_label(t: Translator, key: str) -> str:
    """``fixed`` / ``spot:15min`` / ... in the UI language."""
    kind, _, mtu = key.partition(":")
    return f"{t.t(f'ui.kind.{kind}')} · {t.t(f'ui.mtu_short.{mtu}')}" if mtu else t.t(f"ui.kind.{kind}")


def _all_or(t: Translator, value: str, label) -> str:
    return t.t("ui.filter_all") if value == ALL else label(value)


def _index(options: Sequence[str], value: str | None) -> int:
    return list(options).index(value) if value in options else 0


def _filters(t: Translator, direction: str, rows: list[OverviewRow], house_land: str | None, house_region: str | None) -> OverviewFilter:
    """The filter row of one tab; every key is per direction, so each table keeps its own filters."""
    land_col, kind_col, origin_col, text_col, region_col = st.columns([2, 3, 2, 3, 2])
    lands = [ALL, *lands_of(rows)]
    land = land_col.selectbox(
        t.t("ui.filter_land"), lands, index=_index(lands, house_land), format_func=lambda c: _all_or(t, c, str),
        key=state.k(f"ov.{direction}.land.{house_land}"),
    )  # fmt: skip
    kinds = [ALL, *kinds_of(rows)]
    kind = kind_col.selectbox(
        t.t("ui.ov.filter_kind"), kinds, format_func=lambda k: _all_or(t, k, lambda v: kind_label(t, v)),
        key=state.k(f"ov.{direction}.kind"),
    )  # fmt: skip
    origins = [ALL, *(str(origin) for origin in (Origin.OWN, Origin.CATALOG))]
    origin = origin_col.selectbox(
        t.t("ui.ov.filter_origin"), origins, format_func=lambda o: _all_or(t, o, lambda v: t.t(f"ui.ov.origin.{v}")),
        key=state.k(f"ov.{direction}.origin"),
    )  # fmt: skip
    text = text_col.text_input(t.t("ui.ov.filter_text"), key=state.k(f"ov.{direction}.text"))
    region_only = region_col.checkbox(
        t.t("ui.ov.filter_region"), value=True, help=t.t("ui.ov.filter_region_help"), key=state.k(f"ov.{direction}.region")
    )
    return OverviewFilter(
        land=land or None, kind=kind or None, origin=Origin(origin) if origin else None, text=text,
        region_only=region_only, house_land=house_land, house_region=house_region,
    )  # fmt: skip


def _header(t: Translator, column: Column, month: str | None) -> str:
    label = t.t(f"ui.ov.col.{column.id}")
    return t.t("ui.ov.col_month", label=label, month=month) if month and column.id in PRICE_COLUMNS else label


def _column_config(t: Translator, column: Column, month: str | None):
    label = _header(t, column, month)
    if column.unit in (Unit.CENT, Unit.EUR_MONTH, Unit.PERCENT):
        return localized_number_column(label)
    if column.unit == Unit.COUNT:
        return st.column_config.NumberColumn(label, format="%d")
    if column.unit == Unit.DATE:
        return st.column_config.DateColumn(label, format="localized")
    return st.column_config.TextColumn(label)


def _cell(t: Translator, column: Column, value):
    """Codes become text in the UI language; everything else stays as the model returns it."""
    if column.unit != Unit.CODE or value is None:
        return value
    if column.id == "origin":
        return t.t(f"ui.ov.origin.{value}")
    if column.id == "kind":
        return kind_label(t, value)
    if column.id == "requires":
        return ", ".join(t.t(f"requirement.{item}") for item in value) or None
    if column.id == "check":
        return t.t(f"trust.{value}")
    raise ValueError(f"No translation for code column '{column.id}'.")


def _table(t: Translator, direction: str, shown: list[OverviewRow], basis: Basis, today: date, all_columns: bool) -> None:
    cols = columns(direction)
    values = [row_values(row, basis, today) for row in shown]
    month = today.strftime("%Y-%m") if any(row.tariff.type == "monthly_table" for row in shown) else None
    frame = pd.DataFrame(
        [{column.id: _cell(t, column, item.values[column.id]) for column in cols} for item in values],
        index=[row.key for row in shown],
        columns=[column.id for column in cols],
    )
    st.dataframe(
        frame,
        hide_index=True,
        column_order=[column.id for column in cols if all_columns or column.default],
        column_config={column.id: _column_config(t, column, month) for column in cols},
        placeholder="",
        key=state.k(f"ov.{direction}.table"),
    )
    missing = [row.tariff.label for row, item in zip(shown, values, strict=True) if item.month_missing]
    if missing:
        st.caption(t.t("ui.ov.month_missing", month=today.strftime("%Y-%m"), labels=", ".join(missing)))


def _tab(t: Translator, direction: str, rows: list[OverviewRow], basis: Basis, today: date,
         house_land: str | None, house_region: str | None) -> None:  # fmt: skip
    chosen = _filters(t, direction, rows, house_land, house_region)
    if chosen.region_only and not house_region:
        st.caption(t.t("ui.copy_no_region"))
    shown = filter_rows(rows, chosen)
    all_columns = st.toggle(t.t("ui.ov.all_columns"), key=state.k(f"ov.{direction}.all_columns"))
    if not shown:
        st.caption(t.t("ui.ov.none"))
        return
    _table(t, direction, shown, basis, today, all_columns)


def _tab_title(t: Translator, direction: str, rows: list[OverviewRow]) -> str:
    per_origin = counts(rows)
    return t.t("ui.ov.tab", direction=t.t(f"ui.direction.{direction}"), own=per_origin[Origin.OWN], catalog=per_origin[Origin.CATALOG])


def render(t: Translator, config: UiConfig, house_land: str | None, house_region: str | None, today: date | None = None) -> None:
    """Both tables (import, export) in tabs, with the gross/net switch above them."""
    day = today or date.today()
    document = read_document(config.user_file)
    catalog = read_catalog(config.catalog, day) if config.catalog is not None else []
    rows = {direction: build_rows(direction, document, catalog) for direction in DIRECTIONS}
    head, switch = st.columns([3, 2])
    head.subheader(t.t("ui.ov.title"))
    chosen = switch.segmented_control(
        t.t("ui.ov.basis"), [str(Basis.GROSS), str(Basis.NET)], default=str(Basis.GROSS), required=True,
        format_func=lambda b: t.t(f"ui.ov.basis.{b}"), key=state.k("ov.basis"),
    )  # fmt: skip
    basis = Basis(chosen)
    if config.catalog is None:
        st.caption(t.t("ui.no_catalog"))
    tabs = st.tabs([_tab_title(t, direction, rows[direction]) for direction in DIRECTIONS])
    for tab, direction in zip(tabs, DIRECTIONS, strict=True):
        with tab:
            _tab(t, direction, rows[direction], basis, day, house_land, house_region)

