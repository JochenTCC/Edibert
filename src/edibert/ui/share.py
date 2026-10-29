"""The "share" section: which saved tariffs go to the free catalog, with the exact payload of each."""

from __future__ import annotations

import streamlit as st

from edibert.contribution import (
    ContributionItem,
    SendStatus,
    ShareDefault,
    contribution_items,
    initially_selected,
    payload_text,
    send_selected,
)
from edibert.editor.userstore import read_document
from edibert.errors import EdibertError, EdibertWarning, WarningCode
from edibert.i18n import Translator
from edibert.ui import state
from edibert.ui.config import UiConfig


def _item(t: Translator, item: ContributionItem, share_default: ShareDefault) -> bool:
    """Checkbox and, while selected, the exact JSON of one tariff; ``True`` when it is selected."""
    title = f"{t.t(f'ui.direction.{item.direction}')}: {item.label}"
    if item.error is not None:
        st.caption(t.t("ui.share_refused", label=title, message=t.error(item.error)))
        return False
    assert item.payload is not None
    chosen = st.checkbox(title, value=initially_selected(item, share_default), key=state.k(f"share.{item.direction}.{item.tariff_id}"))
    if chosen:
        st.code(payload_text(item.payload), language="json")
    return chosen


def _send(t: Translator, config: UiConfig, chosen: list[ContributionItem]) -> None:
    try:
        results = send_selected(config.contribution_transport, [item.payload for item in chosen if item.payload is not None])
    except EdibertError as err:
        st.error(t.error(err))
        return
    counts = {status: sum(result.status is status for result in results) for status in SendStatus}
    state.notify(
        t.t("ui.share_done", accepted=counts[SendStatus.ACCEPTED], duplicate=counts[SendStatus.DUPLICATE], rejected=counts[SendStatus.REJECTED])
    )
    st.rerun()


def render(t: Translator, config: UiConfig, share_default: ShareDefault) -> None:
    """Per saved tariff: include or leave out, the payload preview, and the send button.

    ``share_default`` comes from the embedding program (stand-alone: ``SHARE``, Earnie: ``OPT_IN``). Without a
    transport in ``config`` sharing is off: the section says so and the send button stays disabled.
    """
    with st.expander(t.t("ui.share_title")):
        st.caption(t.t("ui.share_intro_share" if share_default is ShareDefault.SHARE else "ui.share_intro_opt_in"))
        off = config.contribution_transport is None
        if off:
            off_note = t.warning(EdibertWarning(WarningCode.CONTRIBUTION_TRANSPORT_OFF, "No contribution transport configured."))
            st.caption(f":orange[{off_note}]")  # a caption: the host page shows the section on every run
        try:
            items = contribution_items(read_document(config.user_file))
        except EdibertError as err:
            st.error(t.error(err))
            return
        if not items:
            st.caption(t.t("ui.share_none"))
            return
        chosen = [item for item in items if _item(t, item, share_default)]
        if st.button(t.t("ui.share_send"), key=state.k("share.send"), disabled=off or not chosen):
            _send(t, config, chosen)
