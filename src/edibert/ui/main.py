"""The Streamlit page. Started by ``python -m edibert ui`` (see ``app.py``)."""

from __future__ import annotations

import streamlit as st

from edibert.ui import sidebar, state
from edibert.ui.config import config_from_env
from edibert.ui.embed import render_body


def main() -> None:
    config = config_from_env()
    with state.scope(config.key_prefix):
        state.init(config)
        t = state.translator()
        st.set_page_config(page_title=t.t("ui.title"), layout="wide")
        sidebar.render(t, config)
        st.title(t.t("ui.title"))
        render_body(t, config)
