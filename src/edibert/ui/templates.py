"""Templates of the tariff database in the editor (0.1.d D4): opt-in, filter, "Copy as template".

Templates are versions nobody checked (route 5). They are shown only after the user switched them on, always with
their trust level, and only copied into the user's own tariffs: the copy carries ``db_ref`` (database ID and
version) and is the user's own from then on. A template is never imported as catalog.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from edibert.editor.userstore import copy_as_template, user_tariff_ids
from edibert.errors import EdibertError
from edibert.exchange import Template, TemplateList
from edibert.i18n import Translator
from edibert.tariff import EXPORT, IMPORT
from edibert.trust import trust_level
from edibert.ui import state
from edibert.ui.config import UiConfig


def template_copy(template: Template, taken: set[str], label_suffix: str) -> dict[str, Any]:
    """The user tariff a template becomes: the template's tariff under a new ``user_`` ID, with its ``db_ref``."""
    local_id = template.db_id.split("/", 2)[2]
    return copy_as_template({**template.tariff, "id": local_id}, taken, label_suffix, template.db_ref.to_dict())


def _title(t: Translator, item: Template) -> str:
    label = str(item.tariff.get("label") or item.db_id)
    trust = t.t(f"trust.{trust_level(item.check_state, item.reliable)}")
    return f"{label} · {item.tariff.get('supplier_id', '')} · {trust} · {item.installations_12m}"


def _load(t: Translator, config: UiConfig, filters: tuple[str, str, str | None, str | None]) -> None:
    assert config.exchange is not None
    try:
        found = config.exchange.list_templates(*filters)
    except EdibertError as err:
        st.error(t.error(err))
        return
    state.set_templates((filters, found))


def render(t: Translator, config: UiConfig, land: str | None, leave: Callable[[tuple], None]) -> None:
    """Expander with the opt-in, the filters (land, direction, supplier search) and the copy button."""
    with st.expander(t.t("ui.templates_title")):
        if config.exchange is None:
            st.caption(t.t("ui.templates_off"))
            return
        if not st.checkbox(t.t("ui.templates_opt_in"), value=False, key=state.k("templates.opt_in")):
            st.caption(t.t("ui.templates_hint"))
            return
        st.warning(t.t("ui.templates_unchecked"))
        land_text = st.text_input(t.t("ui.templates_land"), value=land or "", max_chars=2, key=state.k("templates.land"))
        direction = st.radio(t.t("ui.import_direction"), (IMPORT, EXPORT), format_func=lambda d: t.t(f"ui.direction.{d}"),
                             horizontal=True, key=state.k("templates.direction"))  # fmt: skip
        supplier = st.text_input(t.t("ui.templates_supplier"), key=state.k("templates.supplier")).strip() or None
        filters = (land_text.strip().upper(), direction, None, supplier)
        if st.button(t.t("ui.templates_load"), key=state.k("templates.load"), disabled=len(filters[0]) != 2):
            _load(t, config, filters)
        loaded = state.templates()
        if loaded is None or loaded[0] != filters:
            return
        found: TemplateList = loaded[1]  # type: ignore[assignment]
        if not found.templates:
            st.caption(t.t("ui.templates_none"))
            return
        if found.truncated:
            st.caption(t.t("ui.templates_truncated", count=len(found.templates)))
        items = found.templates
        choice = st.selectbox(t.t("ui.templates_pick"), range(len(items)), format_func=lambda i: _title(t, items[i]),
                              key=state.k(f"templates.pick.{'.'.join(str(f) for f in filters)}"))  # fmt: skip
        item = items[choice]
        if item.latest_checked_version is not None:
            st.info(t.t("ui.templates_checked_exists"))
        copy = template_copy(item, user_tariff_ids(config.user_file)[item.direction], t.t("ui.copy_suffix"))
        st.button(t.t("ui.templates_copy"), key=state.k("templates.copy"), on_click=state.bound(leave),
                  args=(("copy", copy, item.direction),))  # fmt: skip
