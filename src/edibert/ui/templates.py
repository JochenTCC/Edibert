"""Templates of the tariff database in the editor (0.1.d D4): opt-in, filter, "Copy as template".

Templates are versions nobody checked (route 5). They are shown only after the user switched them on, always with
their trust level, and only copied into the user's own tariffs: the copy carries ``db_ref`` (database ID and
version) and is the user's own from then on. A template is never imported as catalog.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from edibert.editor.userstore import copy_as_template
from edibert.errors import EdibertError
from edibert.exchange import Template, TemplateList
from edibert.i18n import Translator
from edibert.tariff import EXPORT, IMPORT
from edibert.ui import state
from edibert.ui.config import UiConfig


def template_copy(template: Template, taken: set[str], label_suffix: str) -> dict[str, Any]:
    """The user tariff a template becomes: the template's tariff under a new ``user_`` ID, with its ``db_ref``."""
    local_id = template.db_id.split("/", 2)[2]
    return copy_as_template({**template.tariff, "id": local_id}, taken, label_suffix, template.db_ref.to_dict())


def _load(t: Translator, config: UiConfig, filters: tuple[str, str, str | None, str | None]) -> None:
    """Load the templates (a callback, so the table shows them in the same run); an error becomes the notice."""
    assert config.exchange is not None
    try:
        found = config.exchange.list_templates(*filters)
    except EdibertError as err:
        state.notify(t.error(err), "error")
        return
    state.set_templates((filters, found))


def _opted(name: str) -> None:
    state.keep(name, st.session_state[state.k(name)])


def _opt_in(t: Translator) -> bool:
    """The opt-in, kept in the editor state: the expander is not drawn in the edit view, and the table above it
    reads the value before the expander runs, so a change is stored in its callback."""
    name = "templates.opt_in"
    agreed = st.checkbox(t.t("ui.templates_opt_in"), value=state.kept(name, False), key=state.k(name),
                         on_change=state.bound(_opted), args=(name,))  # fmt: skip
    state.keep(name, agreed)
    return agreed


def render(t: Translator, config: UiConfig, land: str | None) -> None:
    """Expander with the opt-in and the filters (land, direction, supplier search) and "load". The loaded
    templates appear as rows of the overview table (origin "template", with their trust level)."""
    with st.expander(t.t("ui.templates_title")):
        if config.exchange is None:
            st.caption(t.t("ui.templates_off"))
            return
        if not _opt_in(t):
            st.caption(t.t("ui.templates_hint"))
            return
        st.warning(t.t("ui.templates_unchecked"))
        land_text = st.text_input(t.t("ui.templates_land"), value=land or "", max_chars=2, key=state.k("templates.land"))
        direction = st.radio(t.t("ui.import_direction"), (IMPORT, EXPORT), format_func=lambda d: t.t(f"ui.direction.{d}"),
                             horizontal=True, key=state.k("templates.direction"))  # fmt: skip
        supplier = st.text_input(t.t("ui.templates_supplier"), key=state.k("templates.supplier")).strip() or None
        filters = (land_text.strip().upper(), direction, None, supplier)
        st.button(t.t("ui.templates_load"), key=state.k("templates.load"), disabled=len(filters[0]) != 2,
                  on_click=state.bound(_load), args=(t, config, filters))  # fmt: skip
        loaded = state.templates()
        if loaded is None:
            return
        found: TemplateList = loaded[1]  # type: ignore[assignment]
        shown_direction = loaded[0][1]
        if not found.templates:
            st.caption(t.t("ui.templates_none"))
        elif found.truncated:
            st.caption(t.t("ui.templates_truncated", count=len(found.templates)))
        else:
            st.caption(t.t("ui.templates_loaded", count=len(found.templates), direction=t.t(f"ui.direction.{shown_direction}")))
