"""Sidebar: language, house settings, my tariffs, new/copy/import."""

from __future__ import annotations

import json

import holidays as holidays_lib
import streamlit as st

from edibert.editor.house import COMMON_TIMEZONES, LANDS, save_house
from edibert.editor.model import TariffDraft
from edibert.editor.userstore import (
    SECTIONS,
    copy_as_template,
    delete_user_tariff,
    parse_import_text,
    read_document,
    save_user_tariff,
    user_tariff_ids,
)
from edibert.errors import EdibertError
from edibert.i18n import SUPPORTED_LANGUAGES, Translator
from edibert.rules import REQUIRES
from edibert.tariff import EXPORT, IMPORT
from edibert.ui import state, widgets
from edibert.ui.config import UiConfig

AT_STATES = {
    "1": "Burgenland", "2": "Kärnten", "3": "Niederösterreich", "4": "Oberösterreich", "5": "Salzburg",
    "6": "Steiermark", "7": "Tirol", "8": "Vorarlberg", "9": "Wien",
}  # fmt: skip


def _region_label(land: str, code: str) -> str:
    if not code:
        return "–"
    return f"{code} – {AT_STATES[code]}" if land == "AT" and code in AT_STATES else code


def _regions(land: str) -> list[str]:
    try:
        return ["", *sorted(holidays_lib.country_holidays(land).subdivisions)]
    except NotImplementedError:
        return [""]


def _language(t: Translator) -> None:
    st.selectbox(
        t.t("ui.language"), list(SUPPORTED_LANGUAGES), format_func=lambda code: t.t(f"language.{code}"), key=state.k(state.LANG)
    )


def _house(t: Translator, config: UiConfig) -> None:
    house = state.house()
    with st.expander(t.t("ui.house")):
        house.timezone = st.selectbox(t.t("ui.timezone"), list(COMMON_TIMEZONES), index=_index(COMMON_TIMEZONES, house.timezone), accept_new_options=True, key=state.k("house.timezone"))
        house.land = st.selectbox(t.t("ui.land"), list(LANDS), index=LANDS.index(house.land), key=state.k("house.land"))
        regions = _regions(house.land)
        house.region = st.selectbox(
            t.t("ui.region"), regions, index=_index(regions, house.region), format_func=lambda c: _region_label(house.land, c),
            help=t.t("ui.region_help"), key=state.k(f"house.region.{house.land}"),
        )  # fmt: skip
        house.capabilities = st.multiselect(
            t.t("ui.capabilities"), REQUIRES, default=house.capabilities, format_func=lambda r: t.t(f"requirement.{r}"), key=state.k("house.capabilities")
        )
        house.grid_enabled = st.checkbox(t.t("ui.grid_enabled"), value=house.grid_enabled, key=state.k("house.grid_enabled"))
        if house.grid_enabled:
            house.grid_base_cent = st.number_input(t.t("ui.grid_base"), min_value=0.0, value=house.grid_base_cent, step=0.1, format="%.2f", key=state.k("house.grid_base"))
            st.caption(t.t("ui.grid_rules"))
            widgets.rule_editor(t, house.grid_rules, state.k("house.grid"))
        if st.button(t.t("ui.house_save"), key=state.k("house.save")):
            save_house(config.house_file, house)
            state.notify(t.t("ui.house_saved"))


def _index(options, value) -> int:
    return list(options).index(value) if value in options else 0


def _open(raw: dict, direction: str) -> None:
    state.adopt(TariffDraft.from_raw(raw, direction))


def _house_land(config: UiConfig) -> str | None:
    """Land of the house (host profile or own settings): the visible start value of a new tariff."""
    if config.host_house is not None:
        return config.host_house.context.land
    return state.house().land or None


def _new(direction: str, land: str | None) -> None:
    state.adopt(TariffDraft(direction=direction, land=land))


def _delete(config: UiConfig, tariff_id: str, direction: str) -> None:
    delete_user_tariff(config.user_file, tariff_id, direction)
    state.adopt(None)
    if config.on_change is not None:
        config.on_change("delete", direction, tariff_id)


def _ask_delete(config: UiConfig, tariff_id: str, direction: str) -> None:
    """Delete, or hold the delete for confirmation when the host's guard returns a warning."""
    warning = config.delete_guard(direction, tariff_id) if config.delete_guard is not None else None
    if warning is None:
        _delete(config, tariff_id, direction)
    else:
        state.set_pending_delete((direction, tariff_id, warning))


def _cancel_delete() -> None:
    state.set_pending_delete(None)


def _delete_buttons(t: Translator, config: UiConfig, draft: TariffDraft) -> None:
    args = (config, draft.id, draft.direction)
    pending = state.pending_delete()
    if pending is None or pending[:2] != (draft.direction, draft.id):
        st.button(t.t("ui.delete"), key=state.k("delete"), on_click=state.bound(_ask_delete), args=args)
        return
    st.warning(pending[2])
    st.button(t.t("ui.delete_anyway"), key=state.k("delete.confirm"), type="primary", on_click=state.bound(_delete), args=args)
    st.button(t.t("ui.delete_cancel"), key=state.k("delete.cancel"), on_click=state.bound(_cancel_delete))


def _tariffs(t: Translator, config: UiConfig) -> None:
    st.subheader(t.t("ui.tariffs"))
    document = read_document(config.user_file)
    shown = False
    for direction in (IMPORT, EXPORT):
        for raw in document.get(SECTIONS[direction], []):
            shown = True
            title = f"{t.t(f'ui.direction.{direction}')}: {raw.get('label') or raw['id']}"
            st.button(title, key=state.k(f"open.{direction}.{raw['id']}"), on_click=state.bound(_open), args=(raw, direction), width="stretch")
    if not shown:
        st.caption(t.t("ui.no_tariffs"))
    st.button(t.t("ui.new_import"), key=state.k("new.import"), on_click=state.bound(_new), args=(IMPORT, _house_land(config)), width="stretch")
    st.button(t.t("ui.new_export"), key=state.k("new.export"), on_click=state.bound(_new), args=(EXPORT, _house_land(config)), width="stretch")
    draft = state.draft()
    if draft is not None and draft.id:
        _delete_buttons(t, config, draft)


def _copy_catalog(t: Translator, config: UiConfig) -> None:
    with st.expander(t.t("ui.copy_catalog")):
        if config.catalog is None:
            st.caption(t.t("ui.no_catalog"))
            return
        document = json.loads(config.catalog.read_text(encoding="utf-8"))
        entries = [(d, raw) for d in (IMPORT, EXPORT) for raw in document.get(SECTIONS[d], [])]
        choice = st.selectbox(
            t.t("ui.copy_pick"), range(len(entries)), format_func=lambda i: f"{t.t(f'ui.direction.{entries[i][0]}')}: {entries[i][1].get('label', entries[i][1]['id'])}",
            key=state.k("copy.pick"),
        )  # fmt: skip
        if st.button(t.t("ui.copy_button"), key=state.k("copy.go")):
            direction, raw = entries[choice]
            taken = user_tariff_ids(config.user_file)[direction]
            _open(copy_as_template(raw, taken, t.t("ui.copy_suffix")), direction)
            st.rerun()


def _import(t: Translator, config: UiConfig) -> None:
    with st.expander(t.t("ui.import_title")):
        text = st.text_area(t.t("ui.import_paste"), key=state.k("import.text"))
        upload = st.file_uploader(t.t("ui.import_file"), type=["json"], key=state.k("import.file"))
        if upload is not None:
            text = upload.getvalue().decode("utf-8")
        direction = st.radio(t.t("ui.import_direction"), (IMPORT, EXPORT), format_func=lambda d: t.t(f"ui.direction.{d}"), horizontal=True, key=state.k("import.direction"))
        if not text.strip():
            return
        try:
            items = parse_import_text(text, direction, user_tariff_ids(config.user_file))
        except EdibertError as err:
            st.error(t.error(err))
            return
        chosen = []
        for number, item in enumerate(items):
            chosen.extend(_import_item(t, item, number))
        if st.button(t.t("ui.import_add"), key=state.k("import.add"), disabled=not chosen):
            for item in chosen:
                save_user_tariff(config.user_file, item.raw, item.direction)
                if config.on_change is not None:
                    config.on_change("save", item.direction, item.raw["id"])
            state.notify(t.t("ui.import_done", count=len(chosen)))
            st.rerun()


def _import_item(t: Translator, item, number: int) -> list:
    name = item.raw.get("id", "?")
    if item.error is not None:
        st.error(t.t("ui.import_error", tariff_id=name, message=t.error(item.error)))
        return []
    if item.renamed_from:
        st.info(t.t("ui.import_renamed", old=item.renamed_from, new=name))
    if item.collides and not st.checkbox(t.t("ui.import_replace", tariff_id=name), key=state.k(f"import.replace.{number}")):
        st.warning(t.t("ui.import_collides", tariff_id=name))
        return []
    st.success(t.t("ui.import_ok", tariff_id=name))
    return [item]


def _host_house(t: Translator, config: UiConfig) -> None:
    """The host's house facts, read-only (the host edits them in its own pages)."""
    host = config.host_house
    assert host is not None
    ctx = host.context
    with st.expander(t.t("ui.house")):
        if host.description:
            st.caption(host.description)
        st.caption(
            t.t("ui.host_house", timezone=ctx.timezone, land=ctx.land or "–", region=_region_label(ctx.land or "", ctx.region or ""))
        )
        grid = host.grid_fee
        st.caption(t.t("ui.host_grid", area=grid.area_id) if grid is not None else t.t("ui.host_grid_off"))
        st.caption(t.t("ui.host_house_hint"))


def render_tools(t: Translator, config: UiConfig) -> None:
    """House settings, my tariffs and new/copy/import, into the current container."""
    if config.host_house is None:
        _house(t, config)
    else:
        _host_house(t, config)
    _tariffs(t, config)
    _copy_catalog(t, config)
    _import(t, config)


def render(t: Translator, config: UiConfig) -> None:
    """The standalone page's sidebar: language, data folder and the tools."""
    with st.sidebar:
        _language(t)
        st.caption(t.t("ui.data_dir", path=str(config.data_dir)))
        render_tools(t, config)
