"""Edibert brand assets for the stand-alone page: sidebar logo and browser tab icon.

The embedded editor (``embed.render_body``) shows no logo; the host application brings its own.
The PNG files are rendered from the SVG sources next to them (wordmark as outlines, no font needed).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO_LIGHT = ASSETS / "edibert-logo-light.png"
LOGO_DARK = ASSETS / "edibert-logo-dark.png"
PAGE_ICON = ASSETS / "edibert-icon.png"


def logo_for_theme(theme_type: str | None) -> Path:
    """The logo with the wordmark readable on the given Streamlit theme (``light`` unless ``dark``)."""
    return LOGO_DARK if theme_type == "dark" else LOGO_LIGHT


def render_logo() -> None:
    """Show the theme-matching logo in Streamlit's sidebar chrome."""
    st.logo(str(logo_for_theme(st.context.theme.type)), size="large")
