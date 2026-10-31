"""Catalog exchange inside the publisher (0.1.d client follow-ups): report use, status, package import."""

import json
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from market_helpers import FakeWeb, utc
from test_publish import MQTT, FakeLink

from edibert.editor.house import HouseSettings, save_house
from edibert.editor.userstore import save_user_tariff
from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.exchange import (
    ENV_OFF,
    ExchangeClient,
    ExchangeConfig,
    HttpAnswer,
    UsageReport,
)
from edibert.identity import tariff_version
from edibert.package import build_package, public_key_text
from edibert.publish.config import parse_publish_config
from edibert.publish.exchange_jobs import STATE_FILE, CatalogExchange
from edibert.publish.service import build_publisher
from edibert.tariff import IMPORT

NOW = utc("2026-12-15T09:00")
BASE = {"id": "at_x_fix", "label": "X Fix", "type": "fixed_cent", "supplier_id": "x", "land": "AT", "fix_cent_kwh": 20, "vat_percent": 20}
MONTHLY = {
    "id": "at_x_monthly", "type": "monthly_table", "supplier_id": "x", "land": "AT", "vat_percent": 20,
    "monthly_rates": [{"year": 2026, "month": 9, "tariff_cent_kwh": 9.0}, {"year": 2026, "month": 10, "tariff_cent_kwh": 9.5}],
}  # fmt: skip
OTHER = {**BASE, "id": "at_y_fix", "label": "Y Fix", "supplier_id": "y", "fix_cent_kwh": 25}
AREA = {"id": "AT-X", "label": "X", "land": "AT", "base_cent_kwh": {"unmetered_power": 8.0, "metered_power": 6.0}}
ALL_ON = {"report_use": True, "status": True, "packages": True}
KEY_ID = "test-1"
DB_ID = "AT/import/at_x_fix"


@pytest.fixture(scope="module")
def signing():
    key = Ed25519PrivateKey.generate()
    return key, {KEY_ID: public_key_text(key.public_key())}


def tariffs_doc(*imports, **root):
    return {"tariff_format": 1, "import_tariffs": list(imports), "export_tariffs": [], **root}


def grid_doc():
    return {"tariff_format": 1, "rule_sets": {}, "areas": [AREA]}


def package(signing, *imports, package_id="2026-12-a", database="free", **root):
    manifest = {
        "database": database, "package_id": package_id, "issued_at": "2026-12-14T08:00:00+00:00",
        "valid_until": "2027-03-31", "tariff_format": 1, "key_id": KEY_ID,
    }  # fmt: skip
    return build_package(tariffs_doc(*imports, **root), grid_doc(), manifest, signing[0])


class Server:
    """Answers per route; records every request. ``down`` makes every request fail like a dead network."""

    def __init__(self, package_doc=None, status=None):
        self.package_doc = package_doc
        self.status = status or {}
        self.requests = []
        self.down = False

    def __call__(self, method, url, body, headers, timeout):
        if self.down:
            raise OSError("network down")
        data = None if body is None else json.loads(body)
        self.requests.append((method, url.split("/edibert/v1")[1], data, headers))
        if "/packages/" in url:
            if self.package_doc is None:
                return HttpAnswer(304, {}, b"")
            return HttpAnswer(200, {}, json.dumps(self.package_doc).encode())
        if url.endswith("/status"):
            entries = [self.status.get(item["db_id"], {**item, "known": False}) | {"version": item["version"]} for item in data["entries"]]
            return HttpAnswer(200, {}, json.dumps({"entries": entries}).encode())
        return HttpAnswer(204, {}, b"")

    def routes(self):
        return [route for _, route, _, _ in self.requests]


def at_once(refs, secret, start):
    """Report plan with every report due right away (the real planner spreads them over the day)."""
    return [UsageReport(start, ref.id, ref.version, "unused") for ref in refs]


def setup(tmp_path, signing, server, *, settings=ALL_ON, catalog_doc=None, key=None, published=("at_x_fix",), planner=at_once):
    save_house(tmp_path / "house.json", HouseSettings(timezone="Europe/Vienna", land="AT"))
    catalog = tmp_path / "tariffs.json"
    catalog.write_text(json.dumps(catalog_doc or tariffs_doc(BASE, package={"database": "free", "package_id": "2026-11-a",
                       "issued_at": "2026-11-01T00:00:00+00:00", "valid_until": "2027-01-31"})), encoding="utf-8")  # fmt: skip
    (tmp_path / "grid_fees.json").write_text(json.dumps(grid_doc()), encoding="utf-8")
    document = {"mqtt": MQTT, "tariffs": [{"id": item} for item in published], "exchange": settings}
    (tmp_path / "publish.json").write_text(json.dumps(document), encoding="utf-8")
    link = FakeLink()

    def factory(exchange_settings):
        from edibert.publish.exchange_command import used_ref_map

        config = parse_publish_config(document)
        client = ExchangeClient(ExchangeConfig("https://db.test", key), server, env={})
        return CatalogExchange(client, exchange_settings, tmp_path, catalog, config.tariffs,
                               lambda: used_ref_map(tmp_path, catalog, config.tariffs),
                               trusted_keys=signing[1], planner=planner)  # fmt: skip

    publisher = build_publisher(tmp_path, catalog=catalog, link_factory=lambda _: link, get=FakeWeb(), env={}, exchange_factory=factory)
    return publisher, link


# --- configuration -----------------------------------------------------------------------------


def test_exchange_block_names_every_job():
    config = parse_publish_config({"mqtt": {"host": "h"}, "tariffs": [{"id": "a"}], "exchange": ALL_ON})
    assert (config.exchange.report_use, config.exchange.status, config.exchange.packages) == (True, True, True)
    assert parse_publish_config({"mqtt": {"host": "h"}, "tariffs": [{"id": "a"}]}).exchange is None
    for raw, code in (({"status": True, "packages": True}, ErrorCode.FIELD_MISSING),
                      ({**ALL_ON, "upload": True}, ErrorCode.TARIFF_UNKNOWN_FIELD),
                      ({**ALL_ON, "status": "yes"}, ErrorCode.VALUE_INVALID)):  # fmt: skip
        with pytest.raises(EdibertError) as err:
            parse_publish_config({"mqtt": {"host": "h"}, "tariffs": [{"id": "a"}], "exchange": raw})
        assert err.value.code is code


def test_without_exchange_block_or_with_the_off_switch_nothing_is_sent(tmp_path):
    save_house(tmp_path / "house.json", HouseSettings(timezone="Europe/Vienna", land="AT"))
    catalog = tmp_path / "tariffs.json"
    catalog.write_text(json.dumps(tariffs_doc(BASE)), encoding="utf-8")
    for extra in ({}, {"exchange": ALL_ON}):
        (tmp_path / "publish.json").write_text(json.dumps({"mqtt": MQTT, "tariffs": [{"id": "at_x_fix"}], **extra}), encoding="utf-8")
        publisher = build_publisher(tmp_path, catalog=catalog, link_factory=FakeLink, get=FakeWeb(), env={ENV_OFF: "1"})
        assert publisher.exchange is None
        assert publisher.run_cycle(NOW).published == ["at_x_fix"]
    assert not (tmp_path / STATE_FILE).exists()


def test_packages_need_a_catalog(tmp_path):
    save_house(tmp_path / "house.json", HouseSettings(timezone="Europe/Vienna", land="AT"))
    save_user_tariff(tmp_path / "user_tariffs.json", {**BASE, "id": "user_fix", "supplier_id": "user_s"}, IMPORT)
    (tmp_path / "publish.json").write_text(json.dumps({"mqtt": MQTT, "tariffs": [{"id": "user_fix"}], "exchange": ALL_ON}), encoding="utf-8")
    with pytest.raises(EdibertError) as err:
        build_publisher(tmp_path, link_factory=FakeLink, get=FakeWeb(), env={})
    assert err.value.code is ErrorCode.VALUE_INVALID


# --- report use and status ---------------------------------------------------------------------


def test_reports_go_out_when_due_and_a_restart_does_not_repeat_them(tmp_path, signing):
    server = Server()
    settings = {"report_use": True, "status": False, "packages": False}
    publisher, _ = setup(tmp_path, signing, server, settings=settings)
    publisher.run_cycle(NOW)
    usage = [data for _, route, data, _ in server.requests if route == "/usage"]
    assert usage == [{"db_id": DB_ID, "version": tariff_version(BASE, IMPORT), "pseudonym": usage[0]["pseudonym"]}]
    again, _ = setup(tmp_path, signing, server, settings=settings)
    again.run_cycle(NOW + timedelta(hours=3))
    assert server.routes().count("/usage") == 1
    again.run_cycle(NOW + timedelta(days=1, minutes=1))  # a new day gets a new plan
    assert server.routes().count("/usage") == 2


def test_reports_wait_for_their_time(tmp_path, signing):
    server = Server()

    def later(refs, secret, start):
        return [UsageReport(start + timedelta(hours=5), ref.id, ref.version, "unused") for ref in refs]

    publisher, _ = setup(tmp_path, signing, server, settings={"report_use": True, "status": False, "packages": False}, planner=later)
    publisher.run_cycle(NOW)
    assert "/usage" not in server.routes()
    publisher.run_cycle(NOW + timedelta(hours=5))
    assert server.routes() == ["/usage"]


def test_server_failure_never_takes_prices_down_and_keeps_the_report(tmp_path, signing):
    server = Server()
    server.down = True
    publisher, link = setup(tmp_path, signing, server)
    report = publisher.run_cycle(NOW)
    assert report.published == ["at_x_fix"] and link.state("at_x_fix") == "0.2"
    failed = [note.params["job"] for note in report.notes if note.code is WarningCode.EXCHANGE_JOB_FAILED]
    assert sorted(failed) == ["packages", "report_use", "status"]
    server.down = False
    publisher.run_cycle(NOW + timedelta(minutes=15))  # retried only after an hour
    assert server.routes() == ["/usage"]
    publisher.run_cycle(NOW + timedelta(hours=1))
    assert server.routes().count("/status") == 1 and any(route.startswith("/packages/") for route in server.routes())


def test_status_reaches_the_attributes(tmp_path, signing):
    version = tariff_version(BASE, IMPORT)
    newer = "b" * 64
    server = Server(status={DB_ID: {"db_id": DB_ID, "known": True, "reliable": True, "installations_12m": 4,
                                    "latest_version": newer, "latest_valid_from": "2027-01-01"}})  # fmt: skip
    publisher, link = setup(tmp_path, signing, server, settings={"report_use": False, "status": True, "packages": False})
    publisher.run_cycle(NOW)
    assert link.attributes("at_x_fix")["catalog"] == {
        "database": "free", "db_id": DB_ID, "version": version, "checked_at": NOW.isoformat(), "known": True,
        "reliable": True, "installations_12m": 4, "newer_version": True, "newer_valid_from": "2027-01-01",
    }  # fmt: skip
    publisher.run_cycle(NOW + timedelta(hours=6))
    assert server.routes().count("/status") == 1  # once a day


# --- catalog package ---------------------------------------------------------------------------


def test_package_without_conflicts_is_imported_and_published_at_once(tmp_path, signing):
    changed = {**BASE, "fix_cent_kwh": 30}
    server = Server(package(signing, changed, OTHER))
    publisher, link = setup(tmp_path, signing, server, settings={"report_use": False, "status": False, "packages": True})
    publisher.run_cycle(NOW)
    assert link.state("at_x_fix") == "0.3"
    catalog = json.loads((tmp_path / "tariffs.json").read_text(encoding="utf-8"))
    assert catalog["package"]["package_id"] == "2026-12-a"
    assert server.requests[0][3]["If-None-Match"] == '"2026-11-a"'
    assert publisher.exchange.refs[next(iter(publisher.exchange.refs))].version == tariff_version(changed, IMPORT)


def test_package_that_would_change_local_monthly_rates_is_held(tmp_path, signing):
    entered = {**MONTHLY, "monthly_rates": [*MONTHLY["monthly_rates"], {"year": 2026, "month": 11, "tariff_cent_kwh": 9.9}]}
    local = tariffs_doc(BASE, entered)
    server = Server(package(signing, BASE, MONTHLY))
    publisher, _ = setup(tmp_path, signing, server, catalog_doc=local, settings={"report_use": False, "status": False, "packages": True})
    report = publisher.run_cycle(NOW)
    assert [note.code for note in report.notes] == [WarningCode.PACKAGE_HELD_CONFLICTS]
    assert json.loads((tmp_path / "tariffs.json").read_text(encoding="utf-8")) == local
    later = publisher.run_cycle(NOW + timedelta(hours=2))  # still reported, not asked again
    assert [note.code for note in later.notes] == [WarningCode.PACKAGE_HELD_CONFLICTS] and len(server.requests) == 1


def test_package_that_drops_a_published_tariff_is_held(tmp_path, signing):
    server = Server(package(signing, OTHER))
    publisher, link = setup(tmp_path, signing, server, settings={"report_use": False, "status": False, "packages": True})
    report = publisher.run_cycle(NOW)
    held = [note for note in report.notes if note.code is WarningCode.PACKAGE_HELD_REMOVES_USED]
    assert held and held[0].params["entries"] == "import/at_x_fix"
    assert link.state("at_x_fix") == "0.2"


def test_verified_catalog_is_not_replaced_without_an_access_key(tmp_path, signing):
    verified = tariffs_doc(BASE, package={"database": "verified", "package_id": "v-1", "issued_at": "2026-11-01T00:00:00+00:00",
                                          "valid_until": "2027-01-31"})  # fmt: skip
    server = Server(package(signing, OTHER))
    publisher, _ = setup(tmp_path, signing, server, catalog_doc=verified, settings={"report_use": False, "status": False, "packages": True})
    report = publisher.run_cycle(NOW)
    assert [note.code for note in report.notes] == [WarningCode.PACKAGE_HELD_DATABASE]
    assert server.requests == []
    keyed_server = Server(None)
    (tmp_path / "keyed").mkdir()
    keyed, _ = setup(tmp_path / "keyed", signing, keyed_server, catalog_doc=verified, key="ek_test",
                     settings={"report_use": False, "status": False, "packages": True})  # fmt: skip
    keyed.run_cycle(NOW)
    _, route, _, headers = keyed_server.requests[0]
    assert (route, headers["Authorization"], headers["If-None-Match"]) == ("/packages/verified/latest", "Bearer ek_test", '"v-1"')


def test_broken_state_file_is_an_error(tmp_path, signing):
    (tmp_path / STATE_FILE).write_text("{oops", encoding="utf-8")
    with pytest.raises(EdibertError) as err:
        setup(tmp_path, signing, Server())
    assert err.value.code is ErrorCode.FILE_INVALID
