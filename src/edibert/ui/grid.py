"""Grid-fee section of the stand-alone editor (0.1.d2): choose a catalog area or enter own values.

The section offers the catalog areas of the house's land and region; ``house.json`` stores the chosen ID. Own values
are the user area ``user_house`` in ``user_grid_fees.json``: work price, time windows (they change the work price
only), further per-kWh components and fixed yearly amounts. "Copy as own values" takes a catalog area or a shared
template with its ``db_ref``; the section then says whether the own values still match that database version.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import streamlit as st

from edibert.editor.house import (
    HOUSE_GRID_AREA,
    GridDraft,
    PartDraft,
    grid_catalog_path,
    load_house_grids,
    save_house,
)
from edibert.errors import EdibertError, ErrorCode
from edibert.exchange import GRID
from edibert.fileformat import USER_GRID_FILE, write_json_atomic
from edibert.gridfee import CATALOG, METERING, GridFee, GridFeeCatalog, area_document
from edibert.i18n import Translator
from edibert.identity import entry_version, grid_db_ref_for
from edibert.trust import trust_level
from edibert.ui import state, widgets
from edibert.ui.config import UiConfig

NONE = ""  # no grid fee
OWN = HOUSE_GRID_AREA


def _catalog_document(config: UiConfig) -> dict[str, Any] | None:
    path = grid_catalog_path(config.catalog)
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def add_part(parts: list[PartDraft]) -> None:
    new = PartDraft()
    state.assign_uids([new])
    parts.append(new)


def remove_part(parts: list[PartDraft], uid: int) -> None:
    parts[:] = [part for part in parts if part.uid != uid]


def _parts(t: Translator, parts: list[PartDraft], name: str, metering: str, unit_key: str) -> None:
    """Rows of components or fixed amounts: label and the value for the house's metering type."""
    for part in parts:
        left, middle, right = st.columns([4, 3, 1])
        part.label = left.text_input(t.t("ui.grid_part_label"), value=part.label, key=state.grid_key(f"{name}.r{part.uid}.label"))
        value = part.values.get(metering)
        if value is None:
            middle.caption(t.t("ui.grid_not_modeled"))
        else:
            new = middle.number_input(t.t(unit_key), min_value=0.0, value=float(value), step=0.01, format="%.4f",
                                      key=state.grid_key(f"{name}.r{part.uid}.value.{metering}"))  # fmt: skip
            if not part.id:  # a new row: the same value for both metering types until the other one is entered
                part.values = dict.fromkeys(METERING, new)
            else:
                part.values[metering] = new
        right.button("✕", key=state.grid_key(f"{name}.r{part.uid}.remove"), on_click=state.bound(remove_part), args=(parts, part.uid))
    st.button(t.t(f"ui.grid_add_{name}"), key=state.grid_key(f"{name}.add"), on_click=state.bound(add_part), args=(parts,))


def _summary(t: Translator, fee: GridFee) -> None:
    """Work price, components and fixed amounts of the resolved grid fee (net)."""
    lines = [t.t("ui.grid_sum_work", cent=t.number(fee.base_cent_kwh))]
    lines += [t.t("ui.grid_sum_component", label=part.label, cent=t.number(part.value)) for part in fee.components]
    lines += [t.t("ui.grid_sum_fixed", label=part.label, eur=t.number(part.value, 2)) for part in fee.fixed]
    if fee.fixed:
        lines.append(t.t("ui.grid_sum_fixed_total", eur=t.number(fee.fixed_eur_year, 2)))
    if fee.rules:
        lines.append(t.t("ui.grid_sum_rules", rules=", ".join(rule.label or rule.id for rule in fee.rules)))
    st.code("\n".join(lines), language=None)


def _copy(draft: GridDraft) -> None:
    state.adopt_grid(draft)
    st.session_state[state.k("house.grid_choice")] = OWN


def _origin(t: Translator, draft: GridDraft) -> None:
    ref = draft.extra.get("db_ref")
    if not isinstance(ref, dict):
        return
    try:
        same = entry_version(draft.entry()) == ref.get("version")
    except EdibertError:
        return  # the values do not validate yet; the save button shows the error
    key = "ui.grid_db_same" if same else "ui.grid_db_differs"
    st.caption(t.t(key, db_id=ref.get("id", ""), version=str(ref.get("version", ""))[:12]))


def _own(t: Translator, config: UiConfig, metering: str) -> None:
    draft = state.grid_draft()
    if draft is None:
        st.error(t.t("ui.grid_user_file_invalid", path=str(config.data_dir / USER_GRID_FILE)))
        return
    _origin(t, draft)
    current = draft.base.get(metering, 0.0)
    value = st.number_input(t.t("ui.grid_base"), min_value=0.0, value=float(current), step=0.1, format=widgets.CENT_FORMAT,
                            key=state.grid_key(f"base.{metering}"))  # fmt: skip
    if not draft.base or set(draft.base.values()) == {current}:
        draft.base = dict.fromkeys(METERING, value)
    else:
        draft.base[metering] = value
    st.caption(t.t("ui.grid_rules"))
    widgets.rule_editor(t, draft.rules, state.grid_key("rules"))
    st.caption(t.t("ui.grid_components"))
    _parts(t, draft.components, "component", metering, "ui.grid_component_value")
    st.caption(t.t("ui.grid_fixed"))
    _parts(t, draft.fixed, "fixed", metering, "ui.grid_fixed_value")
    if draft.levies:
        st.caption(t.t("ui.grid_levies", label=str(draft.levies.get("label") or "")))


def _templates(t: Translator, config: UiConfig, land: str) -> None:
    """Shared grid areas nobody checked yet (route 5, ``direction=grid``): opt-in, copy as own values only."""
    if config.exchange is None:
        return
    if not st.checkbox(t.t("ui.grid_templates_opt_in"), value=False, key=state.k("grid.templates.opt_in")):
        return
    st.warning(t.t("ui.templates_unchecked"))
    if st.button(t.t("ui.templates_load"), key=state.k("grid.templates.load")):
        try:
            state.set_grid_templates((land, config.exchange.list_templates(land, GRID)))
        except EdibertError as err:
            st.error(t.error(err))
            return
    loaded = state.grid_templates()
    if loaded is None or loaded[0] != land:
        return
    items = loaded[1].templates  # type: ignore[attr-defined]
    if not items:
        st.caption(t.t("ui.templates_none"))
        return
    choice = st.selectbox(
        t.t("ui.templates_pick"), range(len(items)), key=state.k(f"grid.templates.pick.{land}"),
        format_func=lambda i: f"{items[i].grid_area.get('label', items[i].db_id)} · "
        f"{t.t('trust.' + trust_level(items[i].check_state, items[i].reliable))} · {items[i].installations_12m}",
    )  # fmt: skip
    item = items[choice]
    entry = item.entry()
    draft = GridDraft.from_entry(entry)
    draft.extra["db_ref"] = item.db_ref.to_dict()
    st.button(t.t("ui.grid_copy_own"), key=state.k("grid.templates.copy"), on_click=state.bound(_copy), args=(draft,))


def _options(grids: GridFeeCatalog, land: str, region: str | None, current: str | None) -> list[str]:
    matching = [area.id for area in grids.areas_for(land, region) if grids.origin.get(area.id) == CATALOG]
    if current and current not in (NONE, OWN) and current not in matching and current in grids.areas:
        matching.append(current)  # keep the saved choice visible after the house moved
    return [NONE, *matching, OWN]


def _save(t: Translator, config: UiConfig, choice: str) -> None:
    house = state.house()
    draft = state.grid_draft()
    if choice == OWN:
        if draft is None:
            return
        path = config.data_dir / USER_GRID_FILE
        base = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        document = draft.document(base)
        write_json_atomic(path, document)
    house.grid_area_id = choice or None
    save_house(config.house_file, house)
    state.notify(t.t("ui.grid_saved"))


def render(t: Translator, config: UiConfig) -> None:
    house = state.house()
    with st.expander(t.t("ui.grid_title")):
        st.caption(t.t("ui.grid_hint"))
        if house.legacy_grid is not None:
            st.warning(t.error(EdibertError(ErrorCode.HOUSE_GRID_LEGACY, "", path=str(config.house_file))))
            return
        try:
            grids = load_house_grids(config.catalog, config.data_dir)
        except EdibertError as err:
            st.error(t.error(err))
            return
        region = house.region or None
        options = _options(grids, house.land, region, house.grid_area_id)
        choice_key = state.k("house.grid_choice")
        if choice_key not in st.session_state or st.session_state[choice_key] not in options:
            st.session_state[choice_key] = house.grid_area_id if house.grid_area_id in options else NONE

        def label(option: str) -> str:
            if option == NONE:
                return t.t("ui.grid_choice_none")
            if option == OWN:
                return t.t("ui.grid_choice_own")
            return f"{grids.areas[option].label} ({option})"

        choice = st.selectbox(t.t("ui.grid_choice"), options, format_func=label, key=choice_key)
        if len(options) == 2:
            st.info(t.t("ui.grid_no_catalog_area", land=house.land, region=house.region or "–"))
        metering = house.power_metering
        try:
            if choice == OWN:
                _own(t, config, metering)
                draft = state.grid_draft()
                fee = draft.resolve(house) if draft is not None else None
            elif choice:
                document = _catalog_document(config)
                fee = dataclasses.replace(house, grid_area_id=choice).grid_fee(grids)
                if grids.areas[choice].check is not None:
                    check = grids.areas[choice].check
                    st.caption(t.t("ui.grid_checked", date=check.checked_at.isoformat()))
                if document is not None:
                    copy = GridDraft.from_entry(area_document(document, choice))
                    copy.extra["db_ref"] = grid_db_ref_for(document, choice)
                    st.button(t.t("ui.grid_copy_own"), key=state.k(f"grid.copy.{choice}"), on_click=state.bound(_copy), args=(copy,))
            else:
                fee = None
            if fee is not None:
                _summary(t, fee)
        except EdibertError as err:
            st.error(t.error(err))
            fee = None
        _templates(t, config, house.land)
        if st.button(t.t("ui.grid_save"), key=state.k("grid.save"), disabled=choice != NONE and fee is None):
            try:
                _save(t, config, choice)
            except EdibertError as err:
                st.error(t.error(err))
                return
            st.rerun()
