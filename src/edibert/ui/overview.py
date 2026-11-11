"""Tariff overview (Editor P4a/P4b): one table per direction with filters, a gross/net switch, row selection and
the actions open, copy as template, delete and compare.

The rows, columns, filters, the selection rules and which action fits come from :mod:`edibert.editor.overview`;
this module translates and draws them. The selection is kept by row key (``origin:id``), never by table position.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date

import pandas as pd
import streamlit as st

from edibert.editor.catalog import catalog_package, read_catalog
from edibert.editor.overview import (
    DIRECTIONS,
    Action,
    Basis,
    Column,
    Origin,
    OverviewFilter,
    OverviewRow,
    Unit,
    build_rows,
    columns,
    copies,
    counts,
    filter_rows,
    kinds_of,
    lands_of,
    merge_selection,
    prune_selection,
    refusal,
    require,
    row_values,
    rows_of,
    selected_positions,
    selection_stamp,
)
from edibert.editor.userstore import (
    delete_user_tariff,
    read_document,
    save_user_tariff,
    user_tariff_ids,
)
from edibert.i18n import Translator
from edibert.identity import db_ref_for
from edibert.ui import state
from edibert.ui.config import UiConfig
from edibert.ui.number_columns import localized_number_column

ALL = ""  # the "all" option of a filter
PRICE_COLUMNS = {"base_price", "remuneration"}  # hold this month's rate for monthly tables
Leave = Callable[[tuple], None]


def kind_label(t: Translator, key: str) -> str:
    """``fixed`` / ``spot:15min`` / ... in the UI language."""
    kind, _, mtu = key.partition(":")
    return f"{t.t(f'ui.kind.{kind}')} · {t.t(f'ui.mtu_short.{mtu}')}" if mtu else t.t(f"ui.kind.{kind}")


def _all_or(t: Translator, value: str, label) -> str:
    return t.t("ui.filter_all") if value == ALL else label(value)


def _index(options: Sequence[str], value: str | None) -> int:
    return list(options).index(value) if value in options else 0


def _choice(column, label: str, options: list[str], name: str, preset: str | None, format_func) -> str:
    """A selectbox whose value outlives the edit view: it starts from the kept value (or ``preset``)."""
    value = column.selectbox(
        label, options, index=_index(options, state.kept(name, preset)), format_func=format_func, key=state.k(name)
    )
    state.keep(name, value)
    return value


def _filters(t: Translator, direction: str, rows: list[OverviewRow], house_land: str | None, house_region: str | None) -> OverviewFilter:
    """The filter row of one tab; every key is per direction, so each table keeps its own filters.

    The widgets are not drawn in the edit view, and Streamlit drops their state then; the values are kept in the
    editor state (``state.keep``) and come back as the widgets' start values.
    """
    land_col, kind_col, origin_col, text_col, region_col = st.columns([2, 3, 2, 3, 2])
    land = _choice(land_col, t.t("ui.filter_land"), [ALL, *lands_of(rows)], f"ov.{direction}.land.{house_land}", house_land,
                   lambda c: _all_or(t, c, str))  # fmt: skip
    kind = _choice(kind_col, t.t("ui.ov.filter_kind"), [ALL, *kinds_of(rows)], f"ov.{direction}.kind", ALL,
                   lambda k: _all_or(t, k, lambda v: kind_label(t, v)))  # fmt: skip
    origins = [ALL, *(str(origin) for origin in (Origin.OWN, Origin.CATALOG))]
    origin = _choice(origin_col, t.t("ui.ov.filter_origin"), origins, f"ov.{direction}.origin", ALL,
                     lambda o: _all_or(t, o, lambda v: t.t(f"ui.ov.origin.{v}")))  # fmt: skip
    name = f"ov.{direction}.text"
    text = text_col.text_input(t.t("ui.ov.filter_text"), value=state.kept(name, ""), key=state.k(name))
    state.keep(name, text)
    name = f"ov.{direction}.region"
    region_only = region_col.checkbox(
        t.t("ui.ov.filter_region"), value=state.kept(name, True), help=t.t("ui.ov.filter_region_help"), key=state.k(name)
    )
    state.keep(name, region_only)
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


def _table(t: Translator, direction: str, shown: list[OverviewRow], basis: Basis, today: date, all_columns: bool,
           selected: set[str]) -> list[int]:  # fmt: skip
    """Draw the table; returns the positions (among ``shown``) the user selected."""
    cols = columns(direction)
    values = [row_values(row, basis, today) for row in shown]
    month = today.strftime("%Y-%m") if any(row.tariff.type == "monthly_table" for row in shown) else None
    frame = pd.DataFrame(
        [{column.id: _cell(t, column, item.values[column.id]) for column in cols} for item in values],
        index=[row.key for row in shown],
        columns=[column.id for column in cols],
    )
    event = st.dataframe(
        frame,
        hide_index=True,
        column_order=[column.id for column in cols if all_columns or column.default],
        column_config={column.id: _column_config(t, column, month) for column in cols},
        placeholder="",
        on_select="rerun",
        selection_mode="multi-row",
        # a new key for every other set of rows: a fresh widget instead of positions that now mean other rows
        key=state.k(f"ov.{direction}.table.{selection_stamp(shown)}"),
        selection_default={"selection": {"rows": selected_positions(shown, selected), "columns": []}},
    )
    missing = [row.tariff.label for row, item in zip(shown, values, strict=True) if item.month_missing]
    if missing:
        st.caption(t.t("ui.ov.month_missing", month=today.strftime("%Y-%m"), labels=", ".join(missing)))
    return list(event.selection.rows)


def _db_ref(config: UiConfig, row: OverviewRow) -> Mapping[str, str] | None:
    """The database reference a copy carries: catalog entries of a package catalog only."""
    if row.origin != Origin.CATALOG:
        raise ValueError(f"Row '{row.key}' cannot be copied here (templates join the table in P4c).")
    if config.catalog is None:
        raise ValueError(f"Catalog row '{row.key}' without a catalog file.")
    return db_ref_for(row.raw, row.tariff.direction) if catalog_package(config.catalog) is not None else None


def _copy(t: Translator, config: UiConfig, direction: str, chosen: list[OverviewRow], leave: Leave) -> None:
    """One tariff: its unsaved copy opens in the form. Several: the copies are saved, none is opened."""
    taken = user_tariff_ids(config.user_file)[direction]
    made = copies(chosen, taken, t.t("ui.copy_suffix"), lambda row: _db_ref(config, row))
    if len(made) == 1:
        leave(("copy", made[0], direction))
        return
    for raw in made:
        save_user_tariff(config.user_file, raw, direction)
        if config.on_change is not None:
            config.on_change("save", direction, raw["id"])
    state.set_selection(direction, set())
    state.notify(t.t("ui.ov.copied", count=len(made)))


def _delete(t: Translator, config: UiConfig, direction: str, tariff_ids: tuple[str, ...]) -> None:
    for tariff_id in tariff_ids:
        delete_user_tariff(config.user_file, tariff_id, direction)
        if config.on_change is not None:
            config.on_change("delete", direction, tariff_id)
    draft = state.draft()
    if draft is not None and draft.direction == direction and draft.id in tariff_ids:
        state.adopt(None)  # the open tariff is gone
    state.set_pending_delete(None)
    state.set_selection(direction, set())
    state.notify(t.t("ui.ov.deleted", count=len(tariff_ids)))


def _ask_delete(t: Translator, config: UiConfig, direction: str, chosen: list[OverviewRow]) -> None:
    """Delete, or hold the delete for confirmation when the host's guard warns about any of the tariffs."""
    require(Action.DELETE, chosen)
    tariff_ids = tuple(row.tariff.id for row in chosen)
    guard = config.delete_guard
    answers = [guard(direction, tariff_id) for tariff_id in tariff_ids] if guard is not None else []
    warnings = tuple(answer for answer in answers if answer is not None)
    if warnings:
        state.set_pending_delete((direction, tariff_ids, warnings))
    else:
        _delete(t, config, direction, tariff_ids)


def _open(direction: str, chosen: list[OverviewRow], leave: Leave) -> None:
    require(Action.OPEN, chosen)
    leave(("open", dict(chosen[0].raw), direction))


def _compare(direction: str, chosen: list[OverviewRow]) -> None:
    require(Action.COMPARE, chosen)
    state.set_compared(direction, tuple(row.key for row in chosen))


def _delete_prompt(t: Translator, config: UiConfig, direction: str) -> None:
    pending = state.pending_delete()
    if pending is None or pending[0] != direction:
        return
    with st.container(border=True):
        for warning in pending[2]:
            st.warning(warning)
        confirm, cancel = st.columns(2)
        confirm.button(
            t.t("ui.delete_anyway"), key=state.k("delete.confirm"), type="primary", on_click=state.bound(_delete),
            args=(t, config, direction, pending[1]), width="stretch",
        )  # fmt: skip
        cancel.button(
            t.t("ui.delete_cancel"), key=state.k("delete.cancel"), on_click=state.bound(state.set_pending_delete),
            args=(None,), width="stretch",
        )  # fmt: skip


def _actions(t: Translator, config: UiConfig, direction: str, rows: list[OverviewRow], chosen: list[OverviewRow],
             hidden: int, leave: Leave) -> None:  # fmt: skip
    """What is selected, and the four actions; one that does not fit is disabled and its help says why."""
    if chosen:
        labels = ", ".join(row.tariff.label for row in chosen)
        note = f" {t.t('ui.ov.hidden', count=hidden)}" if hidden else ""
        st.caption(t.t("ui.ov.selected", count=len(chosen), labels=labels) + note)
    else:
        st.caption(t.t("ui.ov.select_hint"))
    handlers: dict[Action, tuple[Callable[..., None], tuple]] = {
        Action.OPEN: (_open, (direction, chosen, leave)),
        Action.COPY: (_copy, (t, config, direction, chosen, leave)),
        Action.DELETE: (_ask_delete, (t, config, direction, chosen)),
        Action.COMPARE: (_compare, (direction, chosen)),
    }
    for column, (action, (handler, args)) in zip(st.columns(len(handlers)), handlers.items(), strict=True):
        reason = refusal(action, chosen)
        column.button(
            t.t(f"ui.ov.action.{action}"), key=state.k(f"ov.{direction}.{action}"), disabled=reason is not None,
            help=t.t(f"ui.ov.why.{reason}") if reason else None, on_click=state.bound(handler), args=args, width="stretch",
        )  # fmt: skip
    _delete_prompt(t, config, direction)
    compared = rows_of(rows, state.compared(direction))
    if compared:
        st.caption(t.t("ui.ov.compare_pending", labels=", ".join(row.tariff.label for row in compared)))


def _tab(t: Translator, config: UiConfig, direction: str, rows: list[OverviewRow], basis: Basis, today: date,
         house_land: str | None, house_region: str | None, leave: Leave) -> None:  # fmt: skip
    chosen = _filters(t, direction, rows, house_land, house_region)
    if chosen.region_only and not house_region:
        st.caption(t.t("ui.copy_no_region"))
    shown = filter_rows(rows, chosen)
    name = f"ov.{direction}.all_columns"
    all_columns = st.toggle(t.t("ui.ov.all_columns"), value=state.kept(name, False), key=state.k(name))
    state.keep(name, all_columns)
    selected = prune_selection(state.selection(direction), rows)
    if shown:
        picked = _table(t, direction, shown, basis, today, all_columns, selected)
        selected = merge_selection(selected, shown, picked)
    else:
        st.caption(t.t("ui.ov.none"))
    state.set_selection(direction, selected)
    visible = {row.key for row in shown}
    _actions(t, config, direction, rows, rows_of(rows, selected), len(selected - visible), leave)


def _tab_title(t: Translator, direction: str, rows: list[OverviewRow]) -> str:
    per_origin = counts(rows)
    return t.t("ui.ov.tab", direction=t.t(f"ui.direction.{direction}"), own=per_origin[Origin.OWN], catalog=per_origin[Origin.CATALOG])


def render(t: Translator, config: UiConfig, house_land: str | None, house_region: str | None, leave: Leave,
           today: date | None = None) -> None:  # fmt: skip
    """Both tables (import, export) in tabs, with the gross/net switch above them. ``leave(action)`` opens a
    tariff or an unsaved copy in the edit view (the caller asks first when the open draft is not saved)."""
    day = today or date.today()
    document = read_document(config.user_file)
    catalog = read_catalog(config.catalog, day) if config.catalog is not None else []
    rows = {direction: build_rows(direction, document, catalog) for direction in DIRECTIONS}
    head, switch = st.columns([3, 2])
    head.subheader(t.t("ui.ov.title"))
    chosen = switch.segmented_control(
        t.t("ui.ov.basis"), [str(Basis.GROSS), str(Basis.NET)], default=state.kept("ov.basis", str(Basis.GROSS)),
        required=True, format_func=lambda b: t.t(f"ui.ov.basis.{b}"), key=state.k("ov.basis"),
    )  # fmt: skip
    state.keep("ov.basis", chosen)
    basis = Basis(chosen)
    if config.catalog is None:
        st.caption(t.t("ui.no_catalog"))
    tabs = st.tabs([_tab_title(t, direction, rows[direction]) for direction in DIRECTIONS])
    for tab, direction in zip(tabs, DIRECTIONS, strict=True):
        with tab:
            _tab(t, config, direction, rows[direction], basis, day, house_land, house_region, leave)
