"""Import of a signed catalog package in the standalone editor (Catalog P5): check, preview, decide, write.

The package comes from a file or from the tariff database server (route 1: the one catalog of checked versions;
unchecked versions are templates to copy, never a catalog). Only the standalone page offers
it; a host application (Earnie) owns its catalog files and imports itself.
"""

from __future__ import annotations

import json

import streamlit as st

from edibert.catalog_import import (
    CHOICES,
    PACKAGE_INFO_KEY,
    ImportPlan,
    apply_package_import,
    plan_package_import,
    write_catalog_pair,
)
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import GRID_CATALOG_FILE
from edibert.i18n import Translator
from edibert.package import verify_package
from edibert.ui import state
from edibert.ui.config import UiConfig


def _read_local(path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc


def _summary(t: Translator, plan: ImportPlan) -> None:
    manifest = plan.package.manifest
    st.success(
        t.t(
            "ui.package_ok",
            package_id=manifest.package_id,
            valid_until=manifest.valid_until.isoformat(),
        )
    )
    for note in plan.package.warnings:
        st.warning(t.warning(note))
    counts = {change: sum(1 for item in plan.changes if item.change == change) for change in ("added", "changed", "removed")}
    st.caption(t.t("ui.package_changes", **counts))
    removed = [item.key for item in plan.changes if item.change == "removed"]
    if removed:
        st.caption(t.t("ui.package_removed", entries=", ".join(removed)))


def _decisions(t: Translator, plan: ImportPlan) -> dict[str, str]:
    """One choice per conflict; nothing is preselected, so every lost monthly rate is a conscious decision."""
    if not plan.conflicts:
        return {}
    st.warning(t.t("ui.package_conflicts", count=len(plan.conflicts)))
    chosen: dict[str, str] = {}
    for conflict in plan.conflicts:
        package = "–" if conflict.package_cent is None else t.number(conflict.package_cent)
        choice = st.radio(
            t.t("ui.package_conflict", entry=conflict.key, local=t.number(conflict.local_cent), package=package),
            CHOICES, index=None, format_func=lambda c: t.t(f"ui.package_choice.{c}"), horizontal=True,
            key=state.k(f"package.conflict.{conflict.key}"),
        )  # fmt: skip
        if choice is not None:
            chosen[conflict.key] = choice
    return chosen


def _download(t: Translator, config: UiConfig) -> None:
    """Button that loads the newest catalog package."""
    if config.exchange is None:
        st.caption(t.t("ui.package_server_off"))
        return
    info = ((_read_local(config.catalog) or {}) if config.catalog else {}).get(PACKAGE_INFO_KEY) or {}
    if not st.button(t.t("ui.package_fetch"), key=state.k("package.fetch")):
        return
    try:
        document = config.exchange.fetch_package(info.get("package_id"))
    except EdibertError as err:
        st.error(t.error(err))
        return
    if document is None:
        st.info(t.t("ui.package_unchanged", package_id=info.get("package_id")))
        return
    state.set_fetched_package(document)


def _document(t: Translator, config: UiConfig) -> dict | None:
    """The package to check: an uploaded file wins over one loaded from the server."""
    upload = st.file_uploader(t.t("ui.package_file"), type=["json"], key=state.k("package.file"))
    _download(t, config)
    if upload is not None:
        return json.loads(upload.getvalue().decode("utf-8"))
    document = state.fetched_package()
    if document is None:
        st.caption(t.t("ui.package_hint"))
    return document


def render(t: Translator, config: UiConfig) -> None:
    with st.expander(t.t("ui.package_title")):
        if config.catalog is None:
            st.caption(t.t("ui.no_catalog"))
            return
        grid_path = config.catalog.parent / GRID_CATALOG_FILE
        try:
            document = _document(t, config)
            if document is None:
                return
            package = verify_package(document)
            plan = plan_package_import(package, _read_local(config.catalog), _read_local(grid_path))
        except (EdibertError, ValueError) as err:
            st.error(t.error(err) if isinstance(err, EdibertError) else t.t("ui.package_unreadable"))
            return
        _summary(t, plan)
        chosen = _decisions(t, plan)
        if st.button(t.t("ui.package_apply"), key=state.k("package.apply"), disabled=len(chosen) < len(plan.conflicts)):
            try:
                tariffs, grid_fees = apply_package_import(plan, chosen)
                write_catalog_pair(config.catalog, tariffs, grid_path, grid_fees)
            except EdibertError as err:
                st.error(t.error(err))
                return
            state.set_fetched_package(None)
            state.notify(t.t("ui.package_done", package_id=package.manifest.package_id))
            st.rerun()
