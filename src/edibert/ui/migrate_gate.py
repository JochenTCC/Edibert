"""Stand-alone UI gate when tariff-track files still need ``api.migrate``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from edibert.editor.house import save_house
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import TARIFF_TRACK_FILES, write_json_atomic
from edibert.i18n import Translator
from edibert.migration import migrate, plan_migration
from edibert.ui import state
from edibert.ui.config import UiConfig


def _raw_track_docs(data_dir: Path) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for name in TARIFF_TRACK_FILES:
        path = data_dir / name
        if not path.is_file():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc
        if not isinstance(document, dict):
            raise EdibertError(ErrorCode.FILE_INVALID, f"'{path}' is not a JSON object.", path=str(path))
        docs[name] = document
    return docs


def render(t: Translator, config: UiConfig, err: EdibertError) -> None:
    """Show why the editor stopped and, when possible, run the migration with an explicit button."""
    st.error(t.error(err))
    st.info(t.t("ui.migrate_hint"))
    try:
        docs = _raw_track_docs(config.data_dir)
    except EdibertError as load_err:
        st.error(t.error(load_err))
        return
    house = state.house() if config.host_house is None else None
    areas, rule_sets, own_area = house.legacy_migration_input() if house is not None and house.legacy_grid else ([], {}, None)
    if house is not None and house.legacy_grid is None:
        own_area = house.grid_area_id  # the area a monthly grid fee of the tariffs moves to (a user area only)
    options = {"user_grid_areas": areas, "user_grid_rule_sets": rule_sets, "grid_fee_area": own_area}
    plan = plan_migration(docs, **options)
    if house is not None and house.legacy_grid is not None:
        st.caption(t.t("ui.migrate_house", path=str(config.house_file)))
    if plan.changed_files:
        st.caption(t.t("ui.migrate_files", files=", ".join(plan.changed_files)))
    for blocker in plan.blockers:
        st.error(t.error(EdibertError(blocker.code, blocker.message, **blocker.params)))
    answers: dict[str, Any] = {}
    for question in plan.questions:
        label = t.t(f"question.{question.code}", **question.params)
        answers[question.id] = st.number_input(
            label,
            min_value=0.0,
            value=float(question.default) if question.default is not None else 0.0,
            step=0.1,
            key=state.k(f"migrate.q.{question.id}"),
        )
    if st.button(t.t("ui.migrate_run"), key=state.k("migrate.run"), type="primary", disabled=not plan.can_run):
        result = migrate(docs, answers, **options)
        if result.blockers:
            for blocker in result.blockers:
                st.error(t.error(EdibertError(blocker.code, blocker.message, **blocker.params)))
            return
        for name in result.changed_files:
            write_json_atomic(config.data_dir / name, result.docs[name])
        changed = list(result.changed_files)
        if house is not None and house.legacy_grid is not None:
            migrated = house.migrated()
            save_house(config.house_file, migrated)
            st.session_state[state.k(state.HOUSE)] = migrated
            changed.append(config.house_file.name)
        state.reload_grid_draft(config)
        state.notify(t.t("ui.migrate_done", files=", ".join(changed) or "—"))
        st.rerun()
