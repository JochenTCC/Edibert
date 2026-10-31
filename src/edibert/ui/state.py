"""Session state of the editor. One session per browser tab, so nothing here is global.

Every key goes through the key prefix of the current render (``scope``), so a host page can embed
the editor next to its own widgets, even twice. The standalone page uses the empty prefix.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import streamlit as st

from edibert.editor.house import HouseSettings, load_house
from edibert.editor.model import RuleDraft, TariffDraft
from edibert.i18n import Translator
from edibert.ui.config import UiConfig

LANG = "ui.lang"
VER = "ui.ver"
DRAFT = "ui.draft"
STEP = "ui.step"
HOUSE = "ui.house"
NOTICE = "ui.notice"
UID = "ui.uid"
INIT = "ui.init"
OPENED = "ui.opened"
PENDING_DELETE = "ui.pending_delete"
PENDING_LEAVE = "ui.pending_leave"
BASELINE = "ui.baseline"
FETCHED_PACKAGE = "ui.fetched_package"
DB_STATUS = "ui.db_status"

# The prefix of the render that is running. Not session data: it is set for the duration of one
# render call (``scope``) and reset afterwards, so sessions and embeds never see each other's prefix.
_PREFIX: ContextVar[str] = ContextVar("edibert_ui_prefix", default="")


@contextmanager
def scope(prefix: str) -> Iterator[None]:
    """Run a render with ``prefix`` in front of every session and widget key."""
    token = _PREFIX.set(prefix)
    try:
        yield
    finally:
        _PREFIX.reset(token)


def bound(callback: Callable[..., None]) -> Callable[..., None]:
    """``callback`` for ``on_click``: Streamlit runs callbacks before the next render, outside ``scope``."""
    prefix = _PREFIX.get()

    def run(*args: object, **kwargs: object) -> None:
        with scope(prefix):
            callback(*args, **kwargs)

    return run


def k(name: str) -> str:
    """A fixed key (session value or long-lived widget) in the current scope."""
    return f"{_PREFIX.get()}{name}"


def init(config: UiConfig) -> None:
    """Create the session defaults once (language from the configuration, saved or host house settings)."""
    ss = st.session_state
    if config.host_house is not None:
        ss[k(LANG)] = config.language  # the host decides the language on every run
    if k(INIT) in ss:
        return
    ss[k(INIT)] = True
    ss[k(LANG)] = config.language
    ss[k(VER)] = 0
    ss[k(UID)] = 0
    ss[k(DRAFT)] = None
    ss[k(STEP)] = 1
    ss[k(NOTICE)] = None
    ss[k(OPENED)] = None
    ss[k(PENDING_DELETE)] = None
    ss[k(PENDING_LEAVE)] = None
    ss[k(BASELINE)] = None
    ss[k(FETCHED_PACKAGE)] = None
    ss[k(DB_STATUS)] = {}
    if config.host_house is None:
        ss[k(HOUSE)] = load_house(config.house_file)
        assign_uids(ss[k(HOUSE)].grid_rules)


def translator() -> Translator:
    return Translator(st.session_state[k(LANG)])


def next_uid() -> int:
    st.session_state[k(UID)] += 1
    return st.session_state[k(UID)]


def assign_uids(rules: Iterable[RuleDraft]) -> None:
    """Give every rule a stable number that its form widgets use as key (never stored)."""
    for rule in rules:
        if not rule.uid:
            rule.uid = next_uid()


def adopt(draft: TariffDraft | None, *, saved: bool = True) -> None:
    """Make ``draft`` the tariff being edited. New widget keys (version) start the form fresh.

    ``saved=False`` (a catalog copy): the draft counts as unsaved before the first change.
    """
    ss = st.session_state
    ss[k(DRAFT)] = draft
    ss[k(VER)] += 1
    ss[k(STEP)] = 1
    ss[k(PENDING_DELETE)] = None
    ss[k(PENDING_LEAVE)] = None
    ss[k(BASELINE)] = draft.to_raw() if draft is not None and saved else None
    if draft is not None:
        assign_uids(draft.rules)


def mark_saved() -> None:
    """The open draft is now what the file holds."""
    st.session_state[k(BASELINE)] = draft().to_raw()  # type: ignore[union-attr]


def unsaved() -> bool:
    """True while the open draft differs from its saved (or freshly opened) state."""
    current = draft()
    return current is not None and current.to_raw() != st.session_state[k(BASELINE)]


def draft() -> TariffDraft | None:
    return st.session_state[k(DRAFT)]


def house() -> HouseSettings:
    return st.session_state[k(HOUSE)]


def step() -> int:
    return st.session_state[k(STEP)]


def set_step(number: int) -> None:
    st.session_state[k(STEP)] = number


def opened() -> tuple[str, str] | None:
    """The last ``open_tariff`` request of the host that was adopted."""
    return st.session_state[k(OPENED)]


def set_opened(request: tuple[str, str] | None) -> None:
    st.session_state[k(OPENED)] = request


def pending_delete() -> tuple[str, str, str] | None:
    """``(direction, tariff_id, warning)`` of a delete that waits for the user's confirmation."""
    return st.session_state[k(PENDING_DELETE)]


def set_pending_delete(pending: tuple[str, str, str] | None) -> None:
    st.session_state[k(PENDING_DELETE)] = pending


def pending_leave() -> tuple | None:
    """The action (open, new, copy) that waits because the open draft is not saved."""
    return st.session_state[k(PENDING_LEAVE)]


def set_pending_leave(action: tuple | None) -> None:
    st.session_state[k(PENDING_LEAVE)] = action


def fetched_package() -> dict | None:
    """The package document loaded from the server, until it is imported or replaced."""
    return st.session_state[k(FETCHED_PACKAGE)]


def set_fetched_package(document: dict | None) -> None:
    st.session_state[k(FETCHED_PACKAGE)] = document


def db_status() -> dict[tuple[str, str], dict]:
    """Status answers asked in this session, by ``(db_id, version)``."""
    return st.session_state[k(DB_STATUS)]


def key(name: str) -> str:
    """Widget key tied to the current draft version, independent of the UI language."""
    return f"{_PREFIX.get()}{st.session_state[k(VER)]}.{name}"


def notify(message: str, kind: str = "success") -> None:
    st.session_state[k(NOTICE)] = (kind, message)


def take_notice() -> tuple[str, str] | None:
    """The pending notice (shown once, after the rerun that follows a save)."""
    notice = st.session_state[k(NOTICE)]
    st.session_state[k(NOTICE)] = None
    return notice
