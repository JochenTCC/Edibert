"""Editor and tariff database server (0.1.d S3, D4): package download, status of a copy, templates, merge hint."""

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
COPY = {**CATALOG, "id": "user_copy", "supplier_id": "user_demo", "db_ref": db_ref_for(CATALOG, IMPORT)}
SHARED = {"label": "Shared Fix", "type": "fixed_cent", "supplier_id": "user_sun", "land": "AT", "fix_cent_kwh": 19.5,
          "vat_percent": 20, "prices_include_vat": True}  # fmt: skip
DB_ID = "AT/import/at_x_fix"
KEY_ID = "test-1"


class _Handler(BaseHTTPRequestHandler):
    package: ClassVar[dict | None] = None
    status: ClassVar[list] = []
    templates: ClassVar[list] = []
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
        if self.path.startswith("/edibert/v1/templates"):
            self._answer(200, {"templates": _Handler.templates, "truncated": False})
            return
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
    _Handler.package, _Handler.status, _Handler.seen, _Handler.templates = None, [], [], []
    monkeypatch.delenv(ENV_OFF, raising=False)
    monkeypatch.setenv(ENV_URL, f"http://127.0.0.1:{httpd.server_address[1]}")
    yield _Handler
    httpd.shutdown()


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    path = tmp_path / "tariffs.json"
    info = {"package_id": "v-old", "issued_at": "2026-10-01T00:00:00+00:00", "valid_until": "2027-12-31"}
    path.write_text(json.dumps({"tariff_format": 1, "package": info, "import_tariffs": [CATALOG], "export_tariffs": []}), encoding="utf-8")
    (tmp_path / "grid_fees.json").write_text(json.dumps({"tariff_format": 1, "rule_sets": {}, "areas": [AREA]}), encoding="utf-8")
    monkeypatch.setenv(ENV_CATALOG, str(path))
    return path


def signed_package(monkeypatch):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(package_module, "TRUSTED_KEYS", {KEY_ID: public_key_text(key.public_key())})
    manifest = {"package_id": "v-new", "issued_at": "2026-11-01T00:00:00+00:00",
                "valid_until": "2027-12-31", "tariff_format": 1, "key_id": KEY_ID}  # fmt: skip
    check = {"state": "checked", "checked_at": "2026-10-25", "source": "price sheet"}
    tariffs = {"tariff_format": 1, "import_tariffs": [{**NEWER, "check": check}], "export_tariffs": []}
    return build_package(tariffs, {"tariff_format": 1, "rule_sets": {}, "areas": [AREA]}, manifest, key)


def captions(app):
    return [item.value for item in app.caption] + [item.value for item in app.sidebar.caption]


def test_package_from_the_server_is_checked_and_imported(data_dir, catalog, server, monkeypatch):
    server.package = signed_package(monkeypatch)
    app = start()
    app.sidebar.button(key="package.fetch").click().run()
    assert not app.exception
    assert server.seen[0] == ("GET", "/edibert/v1/packages/catalog/latest", '"v-old"')
    assert any("catalog package v-new, valid until 2027-12-31" in item.value for item in app.sidebar.success)
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
                      "latest_version": "b" * 64, "latest_valid_from": "2027-01-01", "check_state": "unchecked",
                      "checked_at": None, "latest_checked_version": "b" * 64, "merged_into": None}]  # fmt: skip
    app = start()
    app.button(key="open.import.user_copy").click().run()
    assert not any(text.startswith("Tariff database (") for text in captions(app))
    app.button(key=f"db_status.ask.{DB_ID}").click().run()
    assert server.seen[-1] == ("POST", "/edibert/v1/status", {"entries": [{"db_id": DB_ID, "version": version}]})
    texts = captions(app)
    assert any("reliable (used by several, not checked), used by 3 installations" in text for text in texts)
    assert "A newer version is valid from 2027-01-01. Import the newest catalog package and copy the tariff again." in texts
    assert any("A checked version of this tariff is available" in item.value for item in app.info)


def test_status_from_the_publisher_is_shown_without_asking(data_dir, catalog):
    save_user_tariff(data_dir / "user_tariffs.json", COPY, IMPORT)
    version = tariff_version(CATALOG, IMPORT)
    (data_dir / STATE_FILE).write_text(json.dumps({"state_format": 2, "status_at": "2026-10-30T08:00:00+00:00", "status": [
        {"db_id": DB_ID, "version": version, "known": True, "reliable": False, "installations_12m": 1,
         "latest_version": version, "latest_valid_from": None, "check_state": "checked", "checked_at": "2026-01-10",
         "latest_checked_version": version, "merged_into": None}]}), encoding="utf-8")  # fmt: skip
    app = start()
    app.button(key="open.import.user_copy").click().run()
    assert "Tariff database (2026-10-30): checked, used by 1 installations in the last 12 months." in captions(app)
    assert any("your copy is version" in item.value for item in app.info)
    assert any("Check overdue: the last check was on 2026-01-10" in item.value for item in app.warning)


def test_changed_copy_has_no_status(data_dir, catalog, server):
    save_user_tariff(data_dir / "user_tariffs.json", {**COPY, "fix_cent_kwh": 25}, IMPORT)
    app = start()
    app.button(key="open.import.user_copy").click().run()
    assert not [button for button in app.button if button.key == f"db_status.ask.{DB_ID}"]


def test_merged_entry_relinks_the_copy_only_after_confirmation(data_dir, catalog, server):
    save_user_tariff(data_dir / "user_tariffs.json", COPY, IMPORT)
    version = tariff_version(CATALOG, IMPORT)
    target = {"db_id": "AT/import/shared_other", "version": version}
    server.status = [{"db_id": DB_ID, "version": version, "known": True, "reliable": False, "installations_12m": 1,
                      "latest_version": version, "latest_valid_from": None, "check_state": "unchecked", "checked_at": None,
                      "latest_checked_version": None, "merged_into": target}]  # fmt: skip
    app = start()
    app.button(key="open.import.user_copy").click().run()
    app.button(key=f"db_status.ask.{DB_ID}").click().run()
    assert any("merged this entry into AT/import/shared_other" in item.value for item in app.info)
    app.button(key=f"db_status.relink_ask.{DB_ID}").click().run()
    app.button(key=f"db_status.relink_no.{DB_ID}").click().run()  # declined: nothing changes
    assert not app.exception
    app.button(key=f"db_status.relink_ask.{DB_ID}").click().run()
    app.button(key=f"db_status.relink_yes.{DB_ID}").click().run()
    assert not app.exception
    saved = json.loads((data_dir / "user_tariffs.json").read_text(encoding="utf-8"))["import_tariffs"][0]
    assert saved["db_ref"]["id"] == DB_ID  # the file changes only when the user saves the draft


def test_templates_are_behind_an_opt_in_and_copied_as_own_tariff(data_dir, catalog, server):
    from edibert.exchange import payload_version

    server.templates = [{"db_id": "AT/import/shared_abc", "version": payload_version({"direction": "import", "tariff": SHARED}),
                         "direction": "import", "tariff": SHARED, "valid_from": None, "check_state": "unchecked",
                         "reliable": True, "installations_12m": 2, "latest_version": None, "latest_checked_version": None}]  # fmt: skip
    app = start()
    assert not [button for button in app.button if button.key == "templates.load"]  # opt-in first
    app.checkbox(key="templates.opt_in").check().run()
    app.text_input(key="templates.land").input("AT").run()
    app.button(key="templates.load").click().run()
    assert ("GET", "/edibert/v1/templates?land=AT&direction=import", None) in server.seen
    assert any("Templates are not checked" in item.value for item in app.warning)
    app.button(key="templates.copy").click().run()
    assert not app.exception


def test_old_db_ref_opens_the_migration_gate(data_dir, catalog):
    data_dir.mkdir(parents=True, exist_ok=True)
    old = {**COPY, "db_ref": {"database": "free", **COPY["db_ref"]}}
    (data_dir / "user_tariffs.json").write_text(json.dumps({"tariff_format": 1, "import_tariffs": [old], "export_tariffs": []}), encoding="utf-8")
    app = start()
    assert any("still uses the old copy reference" in item.value for item in app.error)
    app.button(key="migrate.run").click().run()
    saved = json.loads((data_dir / "user_tariffs.json").read_text(encoding="utf-8"))["import_tariffs"][0]
    assert saved["db_ref"] == COPY["db_ref"]
