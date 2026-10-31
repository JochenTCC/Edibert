"""The editor as a component of a host page (Earnie's *Tarife* page), and a tariff preview for the host.

The host owns the page: page config, title, language and the house. The editor brings its tariff list,
form and preview and keeps every key behind ``UiConfig.key_prefix``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from edibert.contribution import ShareDefault, check_share_default
from edibert.editor.model import TariffDraft
from edibert.editor.userstore import SECTIONS, read_document
from edibert.errors import EdibertError, ErrorCode
from edibert.i18n import Translator
from edibert.tariff import EXPORT, IMPORT, Tariff
from edibert.ui import preview, share, sidebar, state
from edibert.ui.config import HostHouse, UiConfig, check_language
from edibert.ui.steps import render_steps

DIRECTIONS = (IMPORT, EXPORT)


def _check_prefix(prefix: str) -> None:
    if not prefix:
        raise ValueError("An embedded editor needs a non-empty key_prefix, e.g. 'host.tariffs.'.")


def show_notice() -> None:
    notice = state.take_notice()
    if notice:
        kind, message = notice
        {"success": st.success, "warning": st.warning}.get(kind, st.error)(message)


def _find_user_tariff(config: UiConfig, direction: str, tariff_id: str) -> Mapping[str, Any]:
    if direction not in DIRECTIONS:
        raise ValueError(f"open_tariff direction must be one of {DIRECTIONS}, got '{direction}'.")
    for raw in read_document(config.user_file).get(SECTIONS[direction], []):
        if raw.get("id") == tariff_id:
            return raw
    raise EdibertError(
        ErrorCode.TARIFF_NOT_FOUND, f"No user tariff '{tariff_id}' in '{config.user_file}'.", tariff_id=tariff_id
    )


def _open_requested(t: Translator, config: UiConfig, request: tuple[str, str] | None) -> None:
    """Adopt the host's ``open_tariff`` once; the same request on later reruns keeps the user's edits."""
    if request is None or request == state.opened():
        return
    state.set_opened(request)
    direction, tariff_id = request
    try:
        raw = _find_user_tariff(config, direction, tariff_id)
    except EdibertError as err:
        st.error(t.error(err))
        return
    state.adopt(TariffDraft.from_raw(dict(raw), direction))


def render_body(t: Translator, config: UiConfig) -> None:
    """Notice, form and preview of the open tariff (shared by the standalone page and the embed)."""
    show_notice()
    draft = state.draft()
    if draft is None:
        st.info(t.t("ui.start_hint"))
        return
    if state.unsaved():
        st.caption(f":orange[● {t.t('ui.unsaved_mark')}]")
    editor, side = st.columns([5, 7])
    with editor:
        render_steps(t, draft)
    with side:
        preview.render(t, draft, config)


def render_editor(
    config: UiConfig,
    *,
    share_default: ShareDefault,
    list_container: Any = None,
    open_tariff: tuple[str, str] | None = None,
) -> None:
    """The editor inside a host page.

    ``config.key_prefix`` must be non-empty; ``config.host_house`` (optional) replaces the editor's own
    house settings, and then nothing is read from or written to ``house.json``. The house settings and
    the own grid fee and the row with the tariff list, new/copy/import go into ``list_container`` (default: above form and preview).
    ``open_tariff=(direction, id)`` opens that user tariff once per distinct request; an unknown ID is shown
    as an error. ``share_default`` (required, no default) says whether saved tariffs start selected in the
    share section: ``ShareDefault.OPT_IN`` for Earnie, ``ShareDefault.SHARE`` for stand-alone Edibert.
    """
    check_share_default(share_default)
    _check_prefix(config.key_prefix)
    check_language(config.language, "language")
    with state.scope(config.key_prefix):
        state.init(config)
        t = state.translator()
        _open_requested(t, config, open_tariff)
        with list_container if list_container is not None else st.container():
            sidebar.render_house(t, config)
            sidebar.render_grid(t, config)
            sidebar.render_tools(t, config)
            share.render(t, config, share_default)
        render_body(t, config)


def render_preview(tariff: Tariff, house: HostHouse, *, language: str, key_prefix: str) -> None:
    """Hints and price curves of ``tariff`` for ``house`` (the host's preview of a selected tariff)."""
    _check_prefix(key_prefix)
    t = Translator(check_language(language, "language"))
    with state.scope(key_prefix):
        preview.render_curves(t, tariff, house.context, house.grid_fee, list(house.capabilities))
