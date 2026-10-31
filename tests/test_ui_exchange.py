"""Editor and tariff database server (0.1.d S3): package download in the sidebar, status of a copied tariff."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

pytest.importorskip("streamlit")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_ui_app import start

import edibert.package as package_module
from edibert.editor.userstore import save_user_tariff
from edibert.exchange import ENV_OFF, ENV_URL
from edibert.identity import db_ref_for, tariff_version
from edibert.package import build_package, public_key_text
from edibert.publish.exchange_jobs import STATE_FILE
from edibert.tariff import IMPORT
from edibert.ui.config import ENV_CATALOG, ENV_DATA_DIR, ENV_LANG

CATALOG = {"id": "at_x_fix", "label": "X Fix", "type": "fixed_cent", "supplier_id": "x", "land": "AT", "fix_cent_kwh": 20, "vat_percent": 20}
NEWER = {**CATALOG, "fix_cent_kwh": 22}
AREA = {"id": "AT-X", "label": "X", "land": "AT", "base_cent_kwh": {"unmetered_power": 8.0, "metered_power": 6.0}}
COPY = {**CATALOG, "id": "user_copy", "supplier_id": "user_demo", "db_ref": db_ref_for(CATALOG, IMPORT, "free")}
DB_ID = "AT/import/at_x_fix"
KEY_ID = "test-1"


class _Handler(BaseHTTPRequestHandler):
    package: ClassVar[dict | None] = None
    status: ClassVar[list] = []
    seen: ClassVar[list] = []

    def _answer(self, code, body=None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        _Handler.seen.append(("GET", self.path, self.headers.get("If-None-Match")))
        self._answer(304) if _Handler.package is None else self._answer(200, _Handler.package)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.seen.append(("POST", self.path, body))
        self._answer(200, {"entries": _Handler.status})

    def log_message(self, *_):
        pass


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv(ENV_LANG, "en")
    return tmp_path / "data"


@pytest.fixture
def server(monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _Handler.package, _Handler.status, _Handler.seen = None, [], []
    monkeypatch.delenv(ENV_OFF, raising=False)
    monkeypatch.setenv(ENV_URL, f"http://127.0.0.1:{httpd.server_address[1]}")
    yield _Handler
    httpd.shutdown()


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    path = tmp_path / "tariffs.json"
    info = {"database": "verified", "package_id": "v-old", "issued_at": "2026-10-01T00:00:00+00:00", "valid_until": "2027-12-31"}
    path.write_text(json.dumps({"tariff_format": 1, "package": info, "import_tariffs": [CATALOG], "export_tariffs": []}), encoding="utf-8")
    (tmp_path / "grid_fees.json").write_text(json.dumps({"tariff_format": 1, "rule_sets": {}, "areas": [AREA]}), encoding="utf-8")
    monkeypatch.setenv(ENV_CATALOG, str(path))
    return path


def signed_package(monkeypatch):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(package_module, "TRUSTED_KEYS", {KEY_ID: public_key_text(key.public_key())})
    manifest = {"database": "verified", "package_id": "v-new", "issued_at": "2026-11-01T00:00:00+00:00",
                "valid_until": "2027-12-31", "tariff_format": 1, "key_id": KEY_ID}  # fmt: skip
    tariffs = {"tariff_format": 1, "import_tariffs": [NEWER], "export_tariffs": []}
    return build_package(tariffs, {"tariff_format": 1, "rule_sets": {}, "areas": [AREA]}, manifest, key)


def captions(app):
    return [item.value for item in app.caption] + [item.value for item in app.sidebar.caption]


def test_package_from_the_server_is_checked_and_imported(data_dir, catalog, server, monkeypatch):
    server.package = signed_package(monkeypatch)
    app = start()
    app.sidebar.button(key="package.fetch").click().run()
    assert not app.exception
    assert server.seen[0] == ("GET", "/edibert/v1/packages/verified/latest", '"v-old"')
    assert any("package v-new of the verified tariff database" in item.value for item in app.sidebar.success)
    app.sidebar.button(key="package.apply").click().run()
    assert json.loads(catalog.read_text(encoding="utf-8"))["package"]["package_id"] == "v-new"


def test_unchanged_package_says_so(data_dir, catalog, server):
    app = start()
    app.sidebar.button(key="package.fetch").click().run()
    assert "The catalog already holds the newest package (v-old)." in [item.value for item in app.sidebar.info]


def test_package_download_is_off_with_the_off_switch(data_dir, catalog):
    app = start()
    assert any("Loading from the tariff database server is switched off" in text for text in captions(app))
    assert not [button for button in app.sidebar.button if button.key == "package.fetch"]


def test_status_of_a_copied_tariff_is_asked_on_request(data_dir, catalog, server):
    save_user_tariff(data_dir / "user_tariffs.json", COPY, IMPORT)
    version = tariff_version(CATALOG, IMPORT)
    server.status = [{"db_id": DB_ID, "version": version, "known": True, "reliable": True, "installations_12m": 3,
                      "latest_version": "b" * 64, "latest_valid_from": "2027-01-01"}]  # fmt: skip
    app = start()
    app.button(key="open.import.user_copy").click().run()
    assert not any(text.startswith("Tariff database (") for text in captions(app))
    app.button(key=f"db_status.ask.{DB_ID}").click().run()
    assert server.seen[-1] == ("POST", "/edibert/v1/status", {"entries": [{"db_id": DB_ID, "version": version}]})
    texts = captions(app)
    assert any("reliable, used by 3 installations" in text for text in texts)
    assert "A newer version is valid from 2027-01-01. Import the newest catalog package and copy the tariff again." in texts


def test_status_from_the_publisher_is_shown_without_asking(data_dir, catalog):
    save_user_tariff(data_dir / "user_tariffs.json", COPY, IMPORT)
    version = tariff_version(CATALOG, IMPORT)
    (data_dir / STATE_FILE).write_text(json.dumps({"state_format": 1, "status_at": "2026-10-30T08:00:00+00:00", "status": [
        {"db_id": DB_ID, "version": version, "known": True, "reliable": False, "installations_12m": 1,
         "latest_version": version, "latest_valid_from": None}]}), encoding="utf-8")  # fmt: skip
    app = start()
    app.button(key="open.import.user_copy").click().run()
    assert "Tariff database (2026-10-30): not yet reliable, used by 1 installations in the last 12 months." in captions(app)


def test_changed_copy_has_no_status(data_dir, catalog, server):
    save_user_tariff(data_dir / "user_tariffs.json", {**COPY, "fix_cent_kwh": 25}, IMPORT)
    app = start()
    app.button(key="open.import.user_copy").click().run()
    assert not [button for button in app.button if button.key == f"db_status.ask.{DB_ID}"]
