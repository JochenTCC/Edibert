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
        t.t("ui.language"), list(SUPPORTED_LANGUAGES), format_func=lambda code: t.t(f"language.{code}"), key=state.LANG
    )


def _house(t: Translator, config: UiConfig) -> None:
    house = state.house()
    with st.expander(t.t("ui.house")):
        house.timezone = st.selectbox(t.t("ui.timezone"), list(COMMON_TIMEZONES), index=_index(COMMON_TIMEZONES, house.timezone), accept_new_options=True, key="house.timezone")
        house.land = st.selectbox(t.t("ui.land"), list(LANDS), index=LANDS.index(house.land), key="house.land")
        regions = _regions(house.land)
        house.region = st.selectbox(
            t.t("ui.region"), regions, index=_index(regions, house.region), format_func=lambda c: _region_label(house.land, c),
            help=t.t("ui.region_help"), key=f"house.region.{house.land}",
        )  # fmt: skip
        house.capabilities = st.multiselect(
            t.t("ui.capabilities"), REQUIRES, default=house.capabilities, format_func=lambda r: t.t(f"requirement.{r}"), key="house.capabilities"
        )
        house.grid_enabled = st.checkbox(t.t("ui.grid_enabled"), value=house.grid_enabled, key="house.grid_enabled")
        if house.grid_enabled:
            house.grid_base_cent = st.number_input(t.t("ui.grid_base"), min_value=0.0, value=house.grid_base_cent, step=0.1, format="%.2f", key="house.grid_base")
            st.caption(t.t("ui.grid_rules"))
            widgets.rule_editor(t, house.grid_rules, "house.grid")
        if st.button(t.t("ui.house_save"), key="house.save"):
            save_house(config.house_file, house)
            state.notify(t.t("ui.house_saved"))


def _index(options, value) -> int:
    return list(options).index(value) if value in options else 0


def _open(raw: dict, direction: str) -> None:
    state.adopt(TariffDraft.from_raw(raw, direction))


def _new(direction: str) -> None:
    state.adopt(TariffDraft(direction=direction))


def _delete(config: UiConfig, tariff_id: str, direction: str) -> None:
    delete_user_tariff(config.user_file, tariff_id, direction)
    state.adopt(None)


def _tariffs(t: Translator, config: UiConfig) -> None:
    st.subheader(t.t("ui.tariffs"))
    document = read_document(config.user_file)
    shown = False
    for direction in (IMPORT, EXPORT):
        for raw in document.get(SECTIONS[direction], []):
            shown = True
            title = f"{t.t(f'ui.direction.{direction}')}: {raw.get('label') or raw['id']}"
            st.button(title, key=f"open.{direction}.{raw['id']}", on_click=_open, args=(raw, direction), width="stretch")
    if not shown:
        st.caption(t.t("ui.no_tariffs"))
    st.button(t.t("ui.new_import"), key="new.import", on_click=_new, args=(IMPORT,), width="stretch")
    st.button(t.t("ui.new_export"), key="new.export", on_click=_new, args=(EXPORT,), width="stretch")
    draft = state.draft()
    if draft is not None and draft.id:
        st.button(t.t("ui.delete"), key="delete", on_click=_delete, args=(config, draft.id, draft.direction))


def _copy_catalog(t: Translator, config: UiConfig) -> None:
    with st.expander(t.t("ui.copy_catalog")):
        if config.catalog is None:
            st.caption(t.t("ui.no_catalog"))
            return
        document = json.loads(config.catalog.read_text(encoding="utf-8"))
        entries = [(d, raw) for d in (IMPORT, EXPORT) for raw in document.get(SECTIONS[d], [])]
        choice = st.selectbox(
            t.t("ui.copy_pick"), range(len(entries)), format_func=lambda i: f"{t.t(f'ui.direction.{entries[i][0]}')}: {entries[i][1].get('label', entries[i][1]['id'])}",
            key="copy.pick",
        )  # fmt: skip
        if st.button(t.t("ui.copy_button"), key="copy.go"):
            direction, raw = entries[choice]
            taken = user_tariff_ids(config.user_file)[direction]
            _open(copy_as_template(raw, taken, t.t("ui.copy_suffix")), direction)
            st.rerun()


def _import(t: Translator, config: UiConfig) -> None:
    with st.expander(t.t("ui.import_title")):
        text = st.text_area(t.t("ui.import_paste"), key="import.text")
        upload = st.file_uploader(t.t("ui.import_file"), type=["json"], key="import.file")
        if upload is not None:
            text = upload.getvalue().decode("utf-8")
        direction = st.radio(t.t("ui.import_direction"), (IMPORT, EXPORT), format_func=lambda d: t.t(f"ui.direction.{d}"), horizontal=True, key="import.direction")
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
        if st.button(t.t("ui.import_add"), key="import.add", disabled=not chosen):
            for item in chosen:
                save_user_tariff(config.user_file, item.raw, item.direction)
            state.notify(t.t("ui.import_done", count=len(chosen)))
            st.rerun()


def _import_item(t: Translator, item, number: int) -> list:
    name = item.raw.get("id", "?")
    if item.error is not None:
        st.error(t.t("ui.import_error", tariff_id=name, message=t.error(item.error)))
        return []
    if item.renamed_from:
        st.info(t.t("ui.import_renamed", old=item.renamed_from, new=name))
    if item.collides and not st.checkbox(t.t("ui.import_replace", tariff_id=name), key=f"import.replace.{number}"):
        st.warning(t.t("ui.import_collides", tariff_id=name))
        return []
    st.success(t.t("ui.import_ok", tariff_id=name))
    return [item]


def render(t: Translator, config: UiConfig) -> None:
    with st.sidebar:
        _language(t)
        st.caption(t.t("ui.data_dir", path=str(config.data_dir)))
        _house(t, config)
        _tariffs(t, config)
        _copy_catalog(t, config)
        _import(t, config)
