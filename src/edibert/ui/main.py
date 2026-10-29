"""The Streamlit page. Started by ``python -m edibert ui`` (see ``app.py``)."""

from __future__ import annotations

import streamlit as st

from edibert.contribution import ShareDefault
from edibert.ui import share, sidebar, state
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
        sidebar.render_tools(t, config)
        share.render(t, config, ShareDefault.SHARE)  # stand-alone Edibert shares by default (concept 2026-10-29)
        render_body(t, config)
