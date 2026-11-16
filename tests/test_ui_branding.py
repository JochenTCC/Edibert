"""Logo and browser tab icon of the stand-alone page."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

import edibert.ui as ui_package
from edibert.ui import branding
from edibert.ui.config import ENV_CATALOG, ENV_DATA_DIR, ENV_LANG

APP = Path(ui_package.__file__).with_name("app.py")  # not imported: importing runs the page
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("asset", [branding.LOGO_LIGHT, branding.LOGO_DARK, branding.PAGE_ICON])
def test_assets_ship_with_the_ui_package(asset):
    assert asset.parent == Path(ui_package.__file__).resolve().parent / "assets"
    assert asset.read_bytes().startswith(PNG_MAGIC)


def test_logo_follows_the_theme():
    assert branding.logo_for_theme("dark") == branding.LOGO_DARK
    assert branding.logo_for_theme("light") == branding.LOGO_LIGHT
    assert branding.logo_for_theme(None) == branding.LOGO_LIGHT


def test_page_renders_logo_and_tab_icon(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv(ENV_LANG, "en")
    monkeypatch.delenv(ENV_CATALOG, raising=False)
    calls: dict[str, object] = {}
    monkeypatch.setattr(branding.st, "logo", lambda image, **kw: calls.update(logo=image, **kw))
    real_config = branding.st.set_page_config
    monkeypatch.setattr(
        branding.st, "set_page_config", lambda **kw: (calls.update(page_icon=kw.get("page_icon")), real_config(**kw))
    )

    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run()

    assert not app.exception
    assert calls == {"logo": str(branding.LOGO_LIGHT), "size": "large", "page_icon": str(branding.PAGE_ICON)}
