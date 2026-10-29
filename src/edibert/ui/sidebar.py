"""Sidebar: language, house settings, my tariffs, new/copy/import."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from edibert.context import region_codes
from edibert.editor.catalog import (
    CatalogEntry,
    catalog_database,
    filter_entries,
    lands_of,
    read_catalog,
    settlement_interval,
    type_keys_of,
)
from edibert.editor.house import COMMON_TIMEZONES, LANDS, save_house
from edibert.editor.model import TariffDraft, validate
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
from edibert.identity import db_ref_for
from edibert.rules import REQUIRES
from edibert.tariff import EXPORT, IMPORT
from edibert.ui import package_import, preview, state, widgets
from edibert.ui.config import UiConfig

AT_STATES = {
    "1": "Burgenland", "2": "Kärnten", "3": "Niederösterreich", "4": "Oberösterreich", "5": "Salzburg",
    "6": "Steiermark", "7": "Tirol", "8": "Vorarlberg", "9": "Wien",
}  # fmt: skip
ALL = ""  # the "all" option of the catalog filters


def region_label(land: str, code: str) -> str:
    if not code:
        return "–"
    return f"{code} – {AT_STATES[code]}" if land == "AT" and code in AT_STATES else code


def _regions(land: str) -> list[str]:
    return ["", *region_codes(land)]


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
            t.t("ui.region"), regions, index=_index(regions, house.region), format_func=lambda c: region_label(house.land, c),
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


def _house_land(config: UiConfig) -> str | None:
    """Land of the house (host profile or own settings): the visible start value of a new tariff."""
    if config.host_house is not None:
        return config.host_house.context.land
    return state.house().land or None


def _house_region(config: UiConfig) -> str | None:
    if config.host_house is not None:
        return config.host_house.context.region
    return state.house().region or None


def _perform(action: tuple) -> None:
    """Leave the open draft: open a user tariff, start a new one or open a catalog copy."""
    name, first, second = action
    if name == "open":
        state.adopt(TariffDraft.from_raw(first, second))
    elif name == "new":
        state.adopt(TariffDraft(direction=first, land=second))
    elif name == "copy":
        state.adopt(TariffDraft.from_raw(first, second), saved=False)
    else:
        raise ValueError(f"Unknown editor action '{name}'.")


def _leave(action: tuple) -> None:
    """``_perform``, or hold it for the unsaved-changes prompt while the open draft is not saved."""
    if state.unsaved():
        state.set_pending_leave(action)
    else:
        _perform(action)


def _save_and_leave(t: Translator, config: UiConfig, action: tuple) -> None:
    draft = state.draft()
    assert draft is not None
    validation = validate(draft, user_tariff_ids(config.user_file)[draft.direction])
    if not validation.ok:  # the prompt offers saving only for a valid draft
        raise ValueError("Save-and-leave on a draft that does not validate.")
    preview.store(t, config, draft, validation)
    _perform(action)


def _leave_prompt(t: Translator, config: UiConfig) -> None:
    """Save / discard / cancel, while an action waits for the unsaved open draft."""
    action = state.pending_leave()
    draft = state.draft()
    if action is None or draft is None:
        return
    validation = validate(draft, user_tariff_ids(config.user_file)[draft.direction])
    with st.container(border=True):
        st.warning(t.t("ui.leave_unsaved", label=draft.label or "–"))
        save, discard, cancel = st.columns(3)
        save.button(
            t.t("ui.leave_save"), key=state.k("leave.save"), type="primary", disabled=not validation.ok,
            on_click=state.bound(_save_and_leave), args=(t, config, action), width="stretch",
        )  # fmt: skip
        discard.button(t.t("ui.leave_discard"), key=state.k("leave.discard"), on_click=state.bound(_perform), args=(action,), width="stretch")
        cancel.button(t.t("ui.leave_cancel"), key=state.k("leave.cancel"), on_click=state.bound(state.set_pending_leave), args=(None,), width="stretch")
        if not validation.ok:
            st.caption(t.t("ui.leave_invalid", message=t.error(validation.error)))  # type: ignore[arg-type]


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


def tariff_title(t: Translator, raw: Mapping[str, Any], direction: str) -> str:
    """List entry: direction, label and, for market prices, the settlement interval."""
    title = f"{t.t(f'ui.direction.{direction}')}: {raw.get('label') or raw['id']}"
    mtu = settlement_interval(raw, direction)
    return f"{title} · {t.t(f'ui.mtu_short.{mtu}')}" if mtu else title


def _tariffs(t: Translator, config: UiConfig) -> None:
    st.subheader(t.t("ui.tariffs"))
    document = read_document(config.user_file)
    shown = False
    for direction in (IMPORT, EXPORT):
        for raw in document.get(SECTIONS[direction], []):
            shown = True
            st.button(
                tariff_title(t, raw, direction), key=state.k(f"open.{direction}.{raw['id']}"), on_click=state.bound(_leave),
                args=(("open", raw, direction),), width="stretch",
            )  # fmt: skip
    if not shown:
        st.caption(t.t("ui.no_tariffs"))
    land = _house_land(config)
    st.button(t.t("ui.new_import"), key=state.k("new.import"), on_click=state.bound(_leave), args=(("new", IMPORT, land),), width="stretch")
    st.button(t.t("ui.new_export"), key=state.k("new.export"), on_click=state.bound(_leave), args=(("new", EXPORT, land),), width="stretch")
    draft = state.draft()
    stored = {raw.get("id") for raw in document.get(SECTIONS[draft.direction], [])} if draft is not None else set()
    if draft is not None and draft.id in stored:  # an unsaved catalog copy has an ID but nothing to delete
        _delete_buttons(t, config, draft)


def _type_label(t: Translator, key: str) -> str:
    kind, _, mtu = key.partition(":")
    return f"{t.t(f'ui.kind.{kind}')} · {t.t(f'ui.mtu_short.{mtu}')}" if mtu else t.t(f"ui.kind.{kind}")


def _all_or(t: Translator, value: str, label) -> str:
    return t.t("ui.filter_all") if value == ALL else label(value)


def _catalog_filters(t: Translator, config: UiConfig, entries: list[CatalogEntry]) -> tuple[str | None, str | None, str | None]:
    """Land (preset: the house land), direction and type; ``None`` = any."""
    lands = [ALL, *lands_of(entries)]
    house_land = _house_land(config)
    land = st.selectbox(
        t.t("ui.filter_land"), lands, index=_index(lands, house_land), format_func=lambda c: _all_or(t, c, str),
        key=state.k(f"copy.land.{house_land}"),
    )  # fmt: skip
    direction = st.selectbox(
        t.t("ui.filter_direction"), [ALL, IMPORT, EXPORT], format_func=lambda d: _all_or(t, d, lambda v: t.t(f"ui.direction.{v}")),
        key=state.k("copy.direction"),
    )  # fmt: skip
    land_value, direction_value = land or None, direction or None
    narrowed = [e for e in entries if land_value in (None, e.land) and direction_value in (None, e.direction)]
    kinds = [ALL, *type_keys_of(narrowed)]
    kind = st.selectbox(
        t.t("ui.filter_type"), kinds, format_func=lambda k: _all_or(t, k, lambda v: _type_label(t, v)),
        key=state.k(f"copy.type.{land}.{direction}"),
    )  # fmt: skip
    return land_value, direction_value, kind or None


def _copy_catalog(t: Translator, config: UiConfig) -> None:
    with st.expander(t.t("ui.copy_catalog")):
        if config.catalog is None:
            st.caption(t.t("ui.no_catalog"))
            return
        entries = read_catalog(config.catalog)
        land, direction, kind = _catalog_filters(t, config, entries)
        region = _house_region(config)
        shown = filter_entries(entries, land=land, direction=direction, kind=kind, house_land=_house_land(config), house_region=region)
        if not region:
            st.caption(t.t("ui.copy_no_region"))
        if not shown:
            st.caption(t.t("ui.copy_none"))
            return
        choice = st.selectbox(
            t.t("ui.copy_pick"), range(len(shown)), format_func=lambda i: tariff_title(t, shown[i].raw, shown[i].direction),
            key=state.k(f"copy.pick.{land}.{direction}.{kind}"),
        )  # fmt: skip
        entry = shown[choice]
        taken = user_tariff_ids(config.user_file)[entry.direction]
        database = catalog_database(config.catalog)
        db_ref = db_ref_for(entry.raw, entry.direction, database) if database is not None else None
        copy = copy_as_template(entry.raw, taken, t.t("ui.copy_suffix"), db_ref)
        st.button(t.t("ui.copy_button"), key=state.k("copy.go"), on_click=state.bound(_leave), args=(("copy", copy, entry.direction),))


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
            t.t("ui.host_house", timezone=ctx.timezone, land=ctx.land or "–", region=region_label(ctx.land or "", ctx.region or ""))
        )
        grid = host.grid_fee
        st.caption(t.t("ui.host_grid", area=grid.area_id) if grid is not None else t.t("ui.host_grid_off"))
        st.caption(t.t("ui.host_house_hint"))


def render_house(t: Translator, config: UiConfig) -> None:
    """The editor's own house settings, or the host's house facts read-only."""
    if config.host_house is None:
        _house(t, config)
    else:
        _host_house(t, config)


def render_tools(t: Translator, config: UiConfig) -> None:
    """The row above form and preview: my tariffs with new/delete, copy from catalog, import."""
    _leave_prompt(t, config)
    mine, catalog, imports = st.columns([3, 5, 3])
    with mine:
        _tariffs(t, config)
    with catalog:
        _copy_catalog(t, config)
    with imports:
        _import(t, config)


def render(t: Translator, config: UiConfig) -> None:
    """The standalone page's sidebar: language, data folder and the house settings."""
    with st.sidebar:
        _language(t)
        st.caption(t.t("ui.data_dir", path=str(config.data_dir)))
        render_house(t, config)
        package_import.render(t, config)
