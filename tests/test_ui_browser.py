"""The monthly-rate table in a real browser: ``st.data_editor`` is a canvas grid that AppTest cannot edit.

Opt-in (marker ``browser``, left out of the normal run by ``addopts``)::

    pip install -e ".[ui,browser]"
    python -m playwright install chromium
    python -m pytest -m browser tests/test_ui_browser.py

Each test starts its own editor server (``streamlit run``, English) on a free port with an empty data folder.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
playwright = pytest.importorskip("playwright.sync_api")

import edibert.ui as ui_package
from edibert.editor.userstore import read_document, save_user_tariff
from edibert.tariff import IMPORT
from edibert.ui.config import ENV_CATALOG, ENV_DATA_DIR, ENV_LANG

pytestmark = pytest.mark.browser

APP = Path(ui_package.__file__).with_name("app.py")
SRC = Path(ui_package.__file__).resolve().parents[2]
START_TIMEOUT_S = 60


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "data"
    path.mkdir()
    return path


@pytest.fixture
def editor_url(data_dir: Path, tmp_path: Path) -> Iterator[str]:
    """``python -m streamlit run app.py`` on a free port, English, data in ``data_dir``; stopped after the test."""
    port = _free_port()
    env = {key: value for key, value in os.environ.items() if key != ENV_CATALOG}
    env.update({ENV_DATA_DIR: str(data_dir), ENV_LANG: "en", "PYTHONPATH": os.pathsep.join([str(SRC), env.get("PYTHONPATH", "")])})
    command = [sys.executable, "-m", "streamlit", "run", str(APP), "--server.port", str(port), "--server.headless", "true",
               "--browser.gatherUsageStats", "false"]  # fmt: skip
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + START_TIMEOUT_S
            while True:
                try:
                    urllib.request.urlopen(f"{url}/_stcore/health", timeout=2)
                    break
                except OSError:
                    if server.poll() is not None or time.monotonic() > deadline:
                        pytest.fail(f"editor server did not start, see {tmp_path / 'server.log'}")
                    time.sleep(0.3)
            yield url
        finally:
            server.terminate()
            server.wait(timeout=10)


@pytest.fixture
def page(editor_url: str) -> Iterator[playwright.Page]:
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1200})
            page.set_default_timeout(30_000)
            page.goto(editor_url)
            page.get_by_text("Create a new tariff").wait_for()
            yield page
        finally:
            browser.close()


ROW_PX = 35  # Streamlit's data editor: header and rows are 35 px high
ROW_MARKER_PX = 15  # inside the row-marker column left of the first data column
FIRST_COLUMN_PX = 50  # inside the first data column (year)


def settle(page: playwright.Page) -> None:
    """Wait until the rerun that the last input started has finished."""
    page.wait_for_timeout(300)
    page.wait_for_function("!document.querySelector('[data-testid=stStatusWidget]')")
    page.wait_for_timeout(300)


class RateTable:
    """The monthly-rate table, driven by mouse and keyboard on its canvas. Columns: 0 year, 1 month, 2 cent."""

    def __init__(self, page: playwright.Page) -> None:
        self.page = page
        self.grid = page.get_by_test_id("stDataFrame")

    def _row_y(self, row: int) -> float:
        box = self.grid.get_by_test_id("data-grid-canvas").bounding_box()
        assert box is not None
        return box["y"] + ROW_PX * (row + 1) + ROW_PX / 2

    def _x(self, offset: float) -> float:
        box = self.grid.get_by_test_id("data-grid-canvas").bounding_box()
        assert box is not None
        return box["x"] + offset

    def set(self, row: int, column: int, text: str) -> None:
        self.page.mouse.click(self._x(FIRST_COLUMN_PX), self._row_y(row))
        for _ in range(column):
            self.page.keyboard.press("ArrowRight")
        self.page.keyboard.press("Enter")
        editor = self.page.locator("input.gdg-input")
        editor.fill(text)
        editor.press("Enter")
        editor.wait_for(state="detached")
        settle(self.page)

    def add_row(self, row: int, year: int, month: int, cent: float) -> None:
        """Add row number ``row`` with the toolbar button and type its cells one by one (each cell is a rerun)."""
        self.grid.hover()
        self.grid.get_by_role("button", name="Add row").click()
        settle(self.page)
        for column, value in enumerate((year, month, cent)):
            self.set(row, column, str(value))

    def delete_row(self, row: int) -> None:
        self.page.mouse.click(self._x(ROW_MARKER_PX), self._row_y(row))
        self.page.keyboard.press("Delete")
        settle(self.page)


def saved_rates(data_dir: Path) -> list[tuple[int, int, float]]:
    (tariff,) = read_document(data_dir / "user_tariffs.json")["import_tariffs"]
    return [(rate["year"], rate["month"], rate["tariff_cent_kwh"]) for rate in tariff["monthly_rates"]]


def seed_table(data_dir: Path, *rates: tuple[int, int, float]) -> None:
    raw = {"id": "user_table", "label": "Table", "type": "monthly_table", "supplier_id": "user_s", "vat_percent": 20,
           "monthly_rates": [{"year": y, "month": m, "tariff_cent_kwh": c} for y, m, c in rates]}  # fmt: skip
    save_user_tariff(data_dir / "user_tariffs.json", raw, IMPORT)


def open_seeded(page: playwright.Page) -> RateTable:
    page.reload()  # the server read no file at start; the sidebar lists the seeded tariff after a reload
    page.get_by_role("button", name="Purchase: Table").click()
    settle(page)
    return RateTable(page)


def save(page: playwright.Page) -> None:
    page.get_by_role("button", name="Save tariff").click()
    settle(page)


def test_a_new_row_is_saved_with_every_cell(page, data_dir):
    """TE4 end to end. Regression: a new row lost its month after the year was typed, because the table
    was rebuilt from the draft on every run and so changed its identity after each cell (0.1.h S2)."""
    today = date.today()  # noqa: DTZ011 (the page starts the table with the local date too)
    following = (today.year + today.month // 12, today.month % 12 + 1)
    page.get_by_role("button", name="New purchase tariff").click()
    settle(page)
    page.get_by_label("Name of the tariff").fill("Table")
    page.keyboard.press("Enter")
    settle(page)
    page.get_by_text("Monthly prices").click()
    settle(page)
    page.get_by_label("VAT (%)").fill("20")
    page.keyboard.press("Enter")
    settle(page)
    table = RateTable(page)
    table.set(0, 2, "12.5")
    table.add_row(1, *following, 13.5)
    save(page)
    assert saved_rates(data_dir) == [(today.year, today.month, 12.5), (*following, 13.5)]


def test_a_reopened_table_keeps_its_rows_and_takes_a_new_one(page, data_dir):
    seed_table(data_dir, (2026, 1, 10.0), (2026, 2, 11.0))
    table = open_seeded(page)
    table.add_row(2, 2026, 3, 12.0)
    save(page)
    assert saved_rates(data_dir) == [(2026, 1, 10.0), (2026, 2, 11.0), (2026, 3, 12.0)]


def test_a_deleted_row_is_gone_from_the_file(page, data_dir):
    seed_table(data_dir, (2026, 1, 10.0), (2026, 2, 11.0))
    table = open_seeded(page)
    table.delete_row(0)
    save(page)
    assert saved_rates(data_dir) == [(2026, 2, 11.0)]


def test_month_13_is_shown_as_an_error_and_cannot_be_saved(page, data_dir):
    seed_table(data_dir, (2026, 1, 10.0))
    before = (data_dir / "user_tariffs.json").read_bytes()
    table = open_seeded(page)
    table.set(0, 1, "13")
    page.get_by_text('Invalid value "13" for field "month"').wait_for()  # the page shows the last part of the path
    assert page.get_by_role("button", name="Save tariff").count() == 0
    assert (data_dir / "user_tariffs.json").read_bytes() == before


def test_a_month_listed_twice_is_shown_as_an_error(page, data_dir):
    seed_table(data_dir, (2026, 1, 10.0), (2026, 2, 11.0))
    table = open_seeded(page)
    table.set(1, 1, "1")
    page.get_by_text("The month 2026-01 is listed twice").wait_for()
    assert page.get_by_role("button", name="Save tariff").count() == 0


def test_edits_survive_a_switch_to_another_price_kind_and_back(page, data_dir):
    seed_table(data_dir, (2026, 1, 10.0))
    table = open_seeded(page)
    table.set(0, 2, "12.5")
    page.get_by_text("Fixed price").click()
    settle(page)
    page.get_by_text("Monthly prices").click()
    settle(page)
    save(page)
    assert saved_rates(data_dir) == [(2026, 1, 12.5)]
