"""Status of a copied tariff in the tariff database (0.1.d S3): reliable, how often used, newer version.

The answer comes from the server on request, or from the publisher's last status query (``exchange_state.json``
in the data folder), so the editor shows something without asking the server on every rerun. Only a tariff whose
prices still match its ``db_ref`` has a status: a changed copy is a version the database does not know.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import streamlit as st

from edibert.editor.model import TariffDraft
from edibert.errors import EdibertError
from edibert.exchange import StatusEntry
from edibert.i18n import Translator
from edibert.identity import differs_from_db
from edibert.publish.exchange_jobs import STATE_FILE
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
    for item in saved.get("status") or []:
        if (item.get("db_id"), item.get("version")) == (db_id, version):
            return {**item, "checked_at": saved.get("status_at")}
    return None


def _ask(config: UiConfig, db_id: str, version: str) -> None:
    assert config.exchange is not None
    entry: StatusEntry = config.exchange.query_status([(db_id, version)])[0]
    state.db_status()[(db_id, version)] = {
        "known": entry.known, "reliable": entry.reliable, "installations_12m": entry.installations_12m,
        "latest_version": entry.latest_version,
        "latest_valid_from": entry.latest_valid_from.isoformat() if entry.latest_valid_from else None,
        "checked_at": datetime.now(UTC).isoformat(),
    }  # fmt: skip


def _show(t: Translator, found: dict[str, Any]) -> None:
    checked = (found.get("checked_at") or "")[:10]
    if not found["known"]:
        st.caption(t.t("ui.db_status_unknown", checked=checked))
        return
    reliable = t.t("ui.db_status_reliable" if found["reliable"] else "ui.db_status_not_reliable")
    st.caption(t.t("ui.db_status", reliable=reliable, count=found["installations_12m"], checked=checked))
    if found.get("latest_version") and found["latest_version"] != found.get("version", found["latest_version"]):
        st.caption(t.t("ui.db_status_newer", valid_from=found.get("latest_valid_from") or "–"))


def render(t: Translator, config: UiConfig, draft: TariffDraft) -> None:
    """Status line under the "copied from" note, and a button that asks the server now."""
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
