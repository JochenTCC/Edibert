"""The Streamlit page. Started by ``python -m edbert ui`` (see ``app.py``)."""

from __future__ import annotations

import streamlit as st

from edbert.ui import preview, sidebar, state
from edbert.ui.config import config_from_env
from edbert.ui.steps import render_steps


def _notice() -> None:
    notice = st.session_state.get(state.NOTICE)
    if notice:
        kind, message = notice
        (st.success if kind == "success" else st.error)(message)
        st.session_state[state.NOTICE] = None


def main() -> None:
    config = config_from_env()
    state.init(config)
    t = state.translator()
    st.set_page_config(page_title=t.t("ui.title"), layout="wide")
    sidebar.render(t, config)
    st.title(t.t("ui.title"))
    _notice()
    draft = state.draft()
    if draft is None:
        st.info(t.t("ui.start_hint"))
        return
    editor, side = st.columns([5, 7])
    with editor:
        render_steps(t, draft)
    with side:
        preview.render(t, draft, config)
