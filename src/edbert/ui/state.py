"""Session state of the editor. One session per browser tab, so nothing here is global."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from edbert.editor.house import HouseSettings, load_house
from edbert.editor.model import RuleDraft, TariffDraft
from edbert.i18n import Translator
from edbert.ui.config import UiConfig

LANG = "ui.lang"
VER = "ui.ver"
DRAFT = "ui.draft"
STEP = "ui.step"
HOUSE = "ui.house"
NOTICE = "ui.notice"
UID = "ui.uid"


def init(config: UiConfig) -> None:
    """Create the session defaults once (language from the configuration, saved house settings)."""
    ss = st.session_state
    if "ui.init" in ss:
        return
    ss["ui.init"] = True
    ss[LANG] = config.language
    ss[VER] = 0
    ss[UID] = 0
    ss[DRAFT] = None
    ss[STEP] = 1
    ss[NOTICE] = None
    ss[HOUSE] = load_house(config.house_file)
    assign_uids(ss[HOUSE].grid_rules)


def translator() -> Translator:
    return Translator(st.session_state[LANG])


def next_uid() -> int:
    st.session_state[UID] += 1
    return st.session_state[UID]


def assign_uids(rules: Iterable[RuleDraft]) -> None:
    """Give every rule a stable number that its form widgets use as key (never stored)."""
    for rule in rules:
        if not rule.uid:
            rule.uid = next_uid()


def adopt(draft: TariffDraft | None) -> None:
    """Make ``draft`` the tariff being edited. New widget keys (version) start the form fresh."""
    ss = st.session_state
    ss[DRAFT] = draft
    ss[VER] += 1
    ss[STEP] = 1
    if draft is not None:
        assign_uids(draft.rules)


def draft() -> TariffDraft | None:
    return st.session_state[DRAFT]


def house() -> HouseSettings:
    return st.session_state[HOUSE]


def key(name: str) -> str:
    """Widget key tied to the current draft version, independent of the UI language."""
    return f"{st.session_state[VER]}.{name}"


def notify(message: str, kind: str = "success") -> None:
    st.session_state[NOTICE] = (kind, message)
