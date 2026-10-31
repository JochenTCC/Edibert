"""Status of a copied tariff in the tariff database (0.1.d D4): trust level, check, use, newer or merged entry.

The answer comes from the server on request, or from the publisher's last status query (``exchange_state.json``
in the data folder), so the editor shows something without asking the server on every rerun. Only a tariff whose
prices still match its ``db_ref`` has a status: a changed copy is a version the database does not know.
When moderation merged the entry into another one, the editor offers to re-link the copy; it never does so
without the user's confirmation, because the copy is the user's.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import streamlit as st

from edibert.editor.model import TariffDraft
from edibert.errors import EdibertError
from edibert.exchange import StatusEntry
from edibert.i18n import Translator
from edibert.identity import differs_from_db
from edibert.publish.exchange_jobs import STATE_FILE, STATE_FORMAT
from edibert.trust import CATALOG_CHECK_STATES, check_overdue, trust_level
from edibert.ui import state
from edibert.ui.config import UiConfig


def _from_publisher(config: UiConfig, db_id: str, version: str) -> dict[str, Any] | None:
    path = config.data_dir / STATE_FILE
    if not path.exists():
        return None
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # the publisher reports its own broken file; the editor just has no status to show
    if saved.get("state_format") != STATE_FORMAT:
        return None  # an older publisher state has no check state; the publisher drops it on its next start
    for item in saved.get("status") or []:
        if (item.get("db_id"), item.get("version")) == (db_id, version):
            return {**item, "status_at": saved.get("status_at")}
    return None


def _ask(config: UiConfig, db_id: str, version: str) -> None:
    assert config.exchange is not None
    entry: StatusEntry = config.exchange.query_status([(db_id, version)])[0]
    state.db_status()[(db_id, version)] = {
        "known": entry.known, "reliable": entry.reliable, "installations_12m": entry.installations_12m,
        "latest_version": entry.latest_version,
        "latest_valid_from": entry.latest_valid_from.isoformat() if entry.latest_valid_from else None,
        "check_state": entry.check_state, "checked_at": entry.checked_at.isoformat() if entry.checked_at else None,
        "latest_checked_version": entry.latest_checked_version,
        "merged_into": {"db_id": entry.merged_into.id, "version": entry.merged_into.version} if entry.merged_into else None,
        "status_at": datetime.now(UTC).isoformat(),
    }  # fmt: skip


def _show(t: Translator, found: dict[str, Any]) -> None:
    asked = (found.get("status_at") or "")[:10]
    if not found["known"]:
        st.caption(t.t("ui.db_status_unknown", checked=asked))
        return
    state_name, checked_at = found.get("check_state"), found.get("checked_at")
    trust = t.t(f"trust.{trust_level(state_name, found['reliable'])}")
    st.caption(t.t("ui.db_status", trust=trust, count=found["installations_12m"], checked=asked))
    if checked_at:
        st.caption(t.t("ui.db_status_check_date", date=checked_at))
        if check_overdue(state_name, date.fromisoformat(checked_at), date.today()):
            st.warning(t.t("ui.db_status_overdue", date=checked_at))
    version, checked = found.get("version"), found.get("latest_checked_version")
    if checked and checked != version:
        st.info(t.t("ui.db_status_checked_available", version=str(checked)[:8]))
    elif checked and state_name in CATALOG_CHECK_STATES:  # the copied version itself was promoted
        st.info(t.t("ui.db_status_checked_same", version=str(checked)[:8]))
    if found.get("latest_version") and found["latest_version"] != found.get("version", found["latest_version"]):
        st.caption(t.t("ui.db_status_newer", valid_from=found.get("latest_valid_from") or "–"))


def _merged(t: Translator, draft: TariffDraft, found: dict[str, Any], db_id: str) -> None:
    """Hint for a merged entry; the copy is re-linked only after an explicit confirmation."""
    target = found.get("merged_into")
    if not found.get("known") or not isinstance(target, dict):
        return
    st.info(t.t("ui.db_status_merged", target=target["db_id"]))
    asking = state.k(f"db_status.relink.{db_id}")
    if not st.session_state.get(asking):
        if st.button(t.t("ui.db_status_relink"), key=state.k(f"db_status.relink_ask.{db_id}")):
            st.session_state[asking] = True
            st.rerun()
        return
    st.warning(t.t("ui.db_status_relink_confirm", target=target["db_id"], version=str(target["version"])[:8]))
    yes, no = st.columns(2)
    if yes.button(t.t("ui.db_status_relink_yes"), key=state.k(f"db_status.relink_yes.{db_id}"), type="primary"):
        draft.extra["db_ref"] = {"id": target["db_id"], "version": target["version"]}
        st.session_state[asking] = False
        state.notify(t.t("ui.db_status_relinked", target=target["db_id"]), "info")
        st.rerun()
    if no.button(t.t("ui.db_status_relink_no"), key=state.k(f"db_status.relink_no.{db_id}")):
        st.session_state[asking] = False
        st.rerun()


def render(t: Translator, config: UiConfig, draft: TariffDraft) -> None:
    """Status lines under the "copied from" note, the merge hint, and a button that asks the server now."""
    ref = draft.extra.get("db_ref")
    if not isinstance(ref, dict):
        return
    try:
        if differs_from_db(draft.to_raw(), draft.direction):
            return
    except EdibertError:
        return  # the form shows the error itself
    db_id, version = str(ref.get("id")), str(ref.get("version"))
    found = state.db_status().get((db_id, version))
    if found is not None:
        found = {**found, "version": version}
    else:
        found = _from_publisher(config, db_id, version)
    if found is not None:
        _show(t, found)
        _merged(t, draft, found, db_id)
    if config.exchange is None:
        if found is None:
            st.caption(t.t("ui.db_status_off"))
        return
    if st.button(t.t("ui.db_status_ask"), key=state.k(f"db_status.ask.{db_id}")):
        try:
            _ask(config, db_id, version)
        except EdibertError as err:
            st.error(t.error(err))
            return
        st.rerun()
