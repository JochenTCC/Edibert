"""The "share" section: which saved tariffs go to the tariff database, with the exact payload of each."""

from __future__ import annotations

import streamlit as st

from edibert.contribution import (
    ContributionItem,
    SendResult,
    SendStatus,
    ShareDefault,
    contribution_items,
    initially_selected,
    payload_text,
    send_selected,
)
from edibert.editor.userstore import SECTIONS, read_document, save_user_tariff
from edibert.errors import EdibertError, EdibertWarning, WarningCode
from edibert.i18n import Translator
from edibert.ui import state
from edibert.ui.config import UiConfig

# Rejection codes of the server (contract docs/spec/catalog-exchange.md § 2) with a text of their own; any
# other code is shown as it came.
REJECT_CODES = ("CONTRIBUTION_FORMAT_UNSUPPORTED", "TARIFF_INVALID", "CONTRIBUTION_INDIVIDUAL", "VERSION_MISMATCH", "MODERATION_REJECTED")


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
        results = send_selected(config.contribution_transport, chosen)
    except EdibertError as err:
        st.error(t.error(err))
        return
    _take_db_refs(config, chosen, results)
    message, kind = result_message(t, chosen, results)
    state.notify(message, kind)
    st.rerun()


def _reject_reason(t: Translator, code: str | None) -> str:
    if code in REJECT_CODES:
        return t.t(f"ui.share_reject.{code}")
    return t.t("ui.share_reject_other", code=code or "?")


def result_message(t: Translator, chosen: list[ContributionItem], results: list[SendResult]) -> tuple[str, str]:
    """The notice after sending: the counts, then one line per rejected tariff with the server's reason.

    The kind is ``"warning"`` as soon as one tariff was rejected, else ``"success"``.
    """
    counts = {status: sum(result.status is status for result in results) for status in SendStatus}
    lines = [
        t.t("ui.share_done", accepted=counts[SendStatus.ACCEPTED], duplicate=counts[SendStatus.DUPLICATE], rejected=counts[SendStatus.REJECTED])
    ]
    for item, result in zip(chosen, results, strict=True):
        if result.status is SendStatus.REJECTED:
            title = f"{t.t(f'ui.direction.{item.direction}')}: {item.label}"
            lines.append(t.t("ui.share_rejected", label=title, reason=_reject_reason(t, result.code)))
    return "  \n".join(lines), "warning" if counts[SendStatus.REJECTED] else "success"


def _take_db_refs(config: UiConfig, chosen: list[ContributionItem], results: list[SendResult]) -> None:
    """An accepted or duplicate tariff now stands for a database entry: it takes the ``db_ref`` the server named."""
    document = read_document(config.user_file)
    for item, result in zip(chosen, results, strict=True):
        if result.db_ref is None:
            continue
        raw = next(raw for raw in document[SECTIONS[item.direction]] if raw.get("id") == item.tariff_id)
        save_user_tariff(config.user_file, {**raw, "db_ref": result.db_ref.to_dict()}, item.direction)


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
