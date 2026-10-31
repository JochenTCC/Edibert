"""Exchange with the tariff database server (contract v2): routes, error mapping, pseudonyms, report plan, CLI."""

import json
import threading
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from random import Random
from typing import ClassVar

import pytest

from edibert.cli import main
from edibert.contribution import (
    SendStatus,
    contribution_items,
    contribution_payload,
    send_selected,
)
from edibert.editor.userstore import read_document, save_user_tariff
from edibert.errors import EdibertError, ErrorCode
from edibert.exchange import (
    ENV_OFF,
    ExchangeClient,
    ExchangeConfig,
    HttpAnswer,
    ServerTransport,
    exchange_config_from_env,
    install_secret,
    payload_version,
    plan_usage_reports,
    urllib_send,
    usage_pseudonym,
    used_ref,
)
from edibert.identity import db_ref_for, differs_from_db, tariff_version
from edibert.tariff import EXPORT, IMPORT, DbRef

USER = {"id": "user_fix", "label": "Mine", "type": "fixed_cent", "supplier_id": "user_demo", "land": "AT", "fix_cent_kwh": 21, "vat_percent": 20}
CATALOG = {"id": "at_x_fix", "label": "X Fix", "type": "fixed_cent", "supplier_id": "x", "land": "AT", "fix_cent_kwh": 20, "vat_percent": 20}
# a user copy of CATALOG with unchanged prices
COPY = {**CATALOG, "id": "user_copy", "supplier_id": "user_demo", "db_ref": db_ref_for(CATALOG, IMPORT)}
V1 = "a" * 64
V2 = "b" * 64


class FakeServer:
    """Records requests and answers from a queue of ``(status, body, headers)``."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, method, url, body, headers, timeout):
        self.requests.append({"method": method, "url": url, "body": None if body is None else json.loads(body), "headers": headers})
        status, data, extra = self.answers.pop(0)
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        return HttpAnswer(status, extra, raw)


def client(*answers, env=None):
    fake = FakeServer(*answers)
    return ExchangeClient(ExchangeConfig("https://db.test/"), fake, env=env or {}), fake


def test_off_switch_stops_every_request():
    exchange, fake = client(env={ENV_OFF: "1"})
    with pytest.raises(EdibertError) as err:
        exchange.query_status([("AT/import/x", V1)])
    assert err.value.code is ErrorCode.EXCHANGE_OFF
    assert fake.requests == []
    assert exchange_config_from_env({ENV_OFF: "1"}) is None
    assert exchange_config_from_env({}).base_url == "https://cloudserver.earnie-hems.com"


def test_fetch_catalog_package_with_etag_and_unchanged_answer():
    exchange, fake = client((200, {"edibert_package": 2}, {}), (304, b"", {}))
    assert exchange.fetch_package() == {"edibert_package": 2}
    assert exchange.fetch_package(known_package_id="p-7") is None
    first, second = fake.requests
    assert first["url"] == "https://db.test/edibert/v1/packages/catalog/latest"
    assert "Authorization" not in first["headers"] and "If-None-Match" not in first["headers"]
    assert second["headers"]["If-None-Match"] == '"p-7"'


@pytest.mark.parametrize(
    ("status", "body", "code", "server_code"),
    [
        (401, {"code": "UNAUTHORIZED"}, ErrorCode.EXCHANGE_ACCESS_DENIED, "UNAUTHORIZED"),
        (403, {"code": "FORBIDDEN"}, ErrorCode.EXCHANGE_ACCESS_DENIED, "FORBIDDEN"),
        (404, {"code": "NO_PACKAGE"}, ErrorCode.EXCHANGE_REJECTED, "NO_PACKAGE"),
        (422, b"not json", ErrorCode.EXCHANGE_REJECTED, "422"),
        (429, {}, ErrorCode.EXCHANGE_RATE_LIMITED, None),
        (503, {}, ErrorCode.EXCHANGE_UNREACHABLE, None),
    ],
)
def test_http_errors_are_coded(status, body, code, server_code):
    exchange, _ = client((status, body, {"retry-after": "60"}))
    with pytest.raises(EdibertError) as err:
        exchange.fetch_package()
    assert err.value.code is code
    if server_code is not None:
        assert err.value.params["server_code"] == server_code


def test_network_failure_is_unreachable():
    def down(*_):
        raise OSError("connection refused")

    with pytest.raises(EdibertError) as err:
        ExchangeClient(ExchangeConfig(), down, env={}).fetch_package()
    assert err.value.code is ErrorCode.EXCHANGE_UNREACHABLE


def test_submit_sends_payload_with_version_and_takes_the_db_ref():
    payload = contribution_payload(USER, IMPORT)
    based_on = DbRef("AT/import/at_x_fix", V1)
    exchange, fake = client((200, {"status": "accepted", "code": None, "db_id": "AT/import/f_12", "version": V2}, {}))
    answer = exchange.submit(payload, based_on)
    body = fake.requests[0]["body"]
    assert body["version"] == tariff_version(USER, IMPORT) == payload_version(payload)
    assert body["based_on"] == {"id": "AT/import/at_x_fix", "version": V1}
    assert {k: body[k] for k in payload} == json.loads(json.dumps(payload))
    assert "id" not in body["tariff"]
    assert answer.status is SendStatus.ACCEPTED and answer.db_ref == DbRef("AT/import/f_12", V2)


def test_submit_rejection_and_invalid_answers():
    payload = contribution_payload(USER, IMPORT)
    exchange, _ = client((200, {"status": "rejected", "code": "VERSION_MISMATCH"}, {}))
    assert exchange.submit(payload).code == "VERSION_MISMATCH"
    for bad in ({"status": "maybe"}, {"status": "accepted", "db_id": "x", "version": V1}, {"status": "duplicate", "db_id": "AT/import/x", "version": "short"}):
        exchange, _ = client((200, bad, {}))
        with pytest.raises(EdibertError) as err:
            exchange.submit(payload)
        assert err.value.code is ErrorCode.EXCHANGE_ANSWER_INVALID


def test_server_transport_is_the_share_adapter():
    exchange, fake = client((200, {"status": "duplicate", "db_id": "AT/import/f_1", "version": V1}, {}))
    [item] = contribution_items({"tariff_format": 1, "import_tariffs": [USER], "export_tariffs": []})
    [result] = send_selected(ServerTransport(exchange), [item])
    assert result.status is SendStatus.DUPLICATE and result.db_ref == DbRef("AT/import/f_1", V1)
    assert "based_on" not in fake.requests[0]["body"]


def test_server_transport_sends_based_on_for_a_tariff_with_db_ref():
    """Regression (Backlog-Bugfixes 2026-10-30): the share section never sent ``based_on``."""
    exchange, fake = client((200, {"status": "accepted", "db_id": COPY["db_ref"]["id"], "version": V1}, {}))
    [item] = contribution_items({"tariff_format": 1, "import_tariffs": [COPY], "export_tariffs": []})
    send_selected(ServerTransport(exchange), [item])
    assert fake.requests[0]["body"]["based_on"] == DbRef(**COPY["db_ref"]).to_dict()


def test_usage_report_carries_exactly_three_fields():
    exchange, fake = client((204, b"", {}))
    exchange.report_usage("AT/import/x", V1, V2)
    assert fake.requests[0]["body"] == {"db_id": "AT/import/x", "version": V1, "pseudonym": V2}
    assert fake.requests[0]["url"].endswith("/edibert/v1/usage")


def test_status_is_parsed_and_asked_in_chunks():
    refs = [(f"AT/import/t{i}", V1) for i in range(150)]

    def answer(entries):
        items = [{"db_id": d, "version": v, "known": False} for d, v in entries]
        items[0] = {"db_id": entries[0][0], "version": V1, "known": True, "reliable": True, "installations_12m": 3,
                    "latest_version": V2, "latest_valid_from": "2027-01-01", "check_state": "unchecked",
                    "checked_at": None, "latest_checked_version": V2,
                    "merged_into": {"db_id": "AT/import/other", "version": V2}}  # fmt: skip
        return (200, {"entries": items}, {})

    exchange, fake = client(answer(refs[:100]), answer(refs[100:]))
    result = exchange.query_status(refs)
    assert len(fake.requests) == 2 and len(fake.requests[1]["body"]["entries"]) == 50
    assert result[0].reliable and result[0].outdated and result[0].latest_valid_from == date(2027, 1, 1)
    assert result[0].check_state == "unchecked" and result[0].checked_available
    assert result[0].merged_into == DbRef("AT/import/other", V2)
    assert not result[1].known and not result[1].outdated and not result[1].checked_available


@pytest.mark.parametrize(
    "change",
    [{"check_state": "maybe"}, {"check_state": None}, {"latest_checked_version": "short"},
     {"merged_into": "AT/import/other"}, {"checked_at": "soon"}],
)
def test_status_v2_fields_are_checked(change):
    item = {"db_id": "AT/import/x", "version": V1, "known": True, "reliable": False, "installations_12m": 0,
            "latest_version": V1, "latest_valid_from": None, "check_state": "checked", "checked_at": "2026-11-02",
            "latest_checked_version": V1, "merged_into": None}  # fmt: skip
    exchange, _ = client((200, {"entries": [item]}, {}))
    assert exchange.query_status([("AT/import/x", V1)])[0].checked_at == date(2026, 11, 2)
    exchange, _ = client((200, {"entries": [{**item, **change}]}, {}))
    with pytest.raises(EdibertError) as err:
        exchange.query_status([("AT/import/x", V1)])
    assert err.value.code is ErrorCode.EXCHANGE_ANSWER_INVALID


def template_item(tariff=None, **changes):
    tariff = tariff or {key: value for key, value in contribution_payload(USER, IMPORT)["tariff"].items()}
    version = payload_version({"direction": IMPORT, "tariff": tariff})
    return {"db_id": "AT/import/shared_abc", "version": version, "direction": "import", "tariff": tariff,
            "valid_from": None, "check_state": "unchecked", "reliable": True, "installations_12m": 2,
            "latest_version": version, "latest_checked_version": None, **changes}  # fmt: skip


def test_templates_are_listed_with_filters_and_checked_versions():
    exchange, fake = client((200, {"templates": [template_item()], "truncated": False}, {}))
    found = exchange.list_templates("AT", "import", supplier=" demo ")
    assert fake.requests[0]["url"] == "https://db.test/edibert/v1/templates?land=AT&direction=import&supplier=demo"
    assert fake.requests[0]["method"] == "GET" and fake.requests[0]["body"] is None
    [item] = found.templates
    assert item.db_ref == DbRef("AT/import/shared_abc", tariff_version(USER, IMPORT)) and not found.truncated
    exchange, fake = client((200, {"templates": [], "truncated": False}, {}))
    exchange.list_templates("AT", "grid", grid_area="AT-VBG")
    assert fake.requests[0]["url"].endswith("/templates?land=AT&direction=grid&grid_area=AT-VBG")


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [(("at", "import"), {}), (("AT", "both"), {}), (("AT", "import"), {"grid_area": "AT-VBG"}), (("AT", "import"), {"supplier": "x"})],
)
def test_template_filters_are_checked_before_asking(args, kwargs):
    exchange, fake = client()
    with pytest.raises(EdibertError) as err:
        exchange.list_templates(*args, **kwargs)
    assert err.value.code is ErrorCode.VALUE_INVALID and fake.requests == []


def test_template_whose_prices_do_not_match_its_version_is_refused():
    for bad in (template_item(version=V1), template_item(direction="export"), template_item(check_state="maybe")):
        exchange, _ = client((200, {"templates": [bad], "truncated": False}, {}))
        with pytest.raises(EdibertError) as err:
            exchange.list_templates("AT", "import")
        assert err.value.code is ErrorCode.EXCHANGE_ANSWER_INVALID
    exchange, _ = client((200, {"templates": []}, {}))
    with pytest.raises(EdibertError) as err:
        exchange.list_templates("AT", "import")
    assert err.value.code is ErrorCode.EXCHANGE_ANSWER_INVALID


def test_template_copy_is_an_own_tariff_with_db_ref():
    from edibert.exchange import _template
    from edibert.ui.templates import template_copy

    item = _template(template_item(), IMPORT, "/templates")
    copy = template_copy(item, {"user_shared_abc"}, "(copy)")
    assert copy["id"] == "user_shared_abc_2" and copy["db_ref"] == item.db_ref.to_dict()
    assert differs_from_db(copy, IMPORT) is False


def test_status_answer_must_match_the_request():
    exchange, _ = client((200, {"entries": []}, {}))
    with pytest.raises(EdibertError) as err:
        exchange.query_status([("AT/import/x", V1)])
    assert err.value.code is ErrorCode.EXCHANGE_ANSWER_INVALID


def test_install_secret_is_kept_and_pseudonyms_differ_per_tariff(tmp_path):
    secret = install_secret(tmp_path)
    assert install_secret(tmp_path) == secret and len(secret) == 32
    first, second = usage_pseudonym(secret, "AT/import/a"), usage_pseudonym(secret, "AT/export/b")
    assert first != second and len(first) == 64
    assert usage_pseudonym(secret, "AT/import/a") == first
    assert usage_pseudonym(b"other" * 7, "AT/import/a") != first
    (tmp_path / "exchange_secret").write_text("broken", encoding="ascii")
    with pytest.raises(EdibertError) as err:
        install_secret(tmp_path)
    assert err.value.code is ErrorCode.FILE_INVALID


def test_report_plan_sends_each_entry_alone_at_a_random_time():
    start = datetime(2026, 10, 29, tzinfo=UTC)
    refs = [DbRef("AT/import/a", V1), DbRef("AT/import/a", V1), DbRef("AT/export/b", V2)]
    plan = plan_usage_reports(refs, b"s" * 32, start, Random(4))
    assert len(plan) == 2
    assert all(start <= report.send_at < start + timedelta(days=1) for report in plan)
    assert plan == sorted(plan, key=lambda report: report.send_at)
    assert plan[0].send_at != plan[1].send_at


def test_used_ref_counts_only_database_versions():
    assert used_ref(COPY, IMPORT, False) == DbRef(**COPY["db_ref"])
    assert used_ref({**COPY, "fix_cent_kwh": 25}, IMPORT, False) is None  # prices changed since the copy
    assert used_ref(USER, IMPORT, True) is None  # own tariff never shared
    assert used_ref(CATALOG, IMPORT, True) == DbRef("AT/import/at_x_fix", tariff_version(CATALOG, IMPORT))
    assert used_ref(CATALOG, IMPORT, False) is None  # seed catalog, not from a package


def test_share_section_stores_the_db_ref_of_accepted_tariffs(tmp_path):
    from edibert.contribution import SendResult, contribution_items
    from edibert.ui.config import UiConfig
    from edibert.ui.share import _take_db_refs

    config = UiConfig(tmp_path, None, "en")
    save_user_tariff(config.user_file, USER, IMPORT)
    save_user_tariff(config.user_file, {**USER, "id": "user_feed", "type": "fixed", "k_push_cent": 7}, EXPORT)
    items = contribution_items(read_document(config.user_file))
    ref = DbRef("AT/import/f_9", tariff_version(USER, IMPORT))
    _take_db_refs(config, items, [SendResult(SendStatus.ACCEPTED, None, ref), SendResult(SendStatus.REJECTED, "X")])
    document = read_document(config.user_file)
    assert document["import_tariffs"][0]["db_ref"] == ref.to_dict()
    assert "db_ref" not in document["export_tariffs"][0]


class _Handler(BaseHTTPRequestHandler):
    seen: ClassVar[list] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        _Handler.seen.append((self.path, json.loads(self.rfile.read(length)), self.headers["User-Agent"]))
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        self.send_response(404)
        body = json.dumps({"code": "NO_PACKAGE", "message": "none"}).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@pytest.fixture
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Handler.seen = []
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_urllib_transport_against_a_local_server(local_server):
    exchange = ExchangeClient(ExchangeConfig(local_server), urllib_send, env={})
    exchange.report_usage("AT/import/x", V1, V2)
    assert _Handler.seen[0][0] == "/edibert/v1/usage" and _Handler.seen[0][2].startswith("Edibert/")
    with pytest.raises(EdibertError) as err:
        exchange.fetch_package()
    assert err.value.params["server_code"] == "NO_PACKAGE"


def test_cli_report_sends_one_request_per_tariff_in_use(tmp_path, local_server, monkeypatch, capsys):
    monkeypatch.setenv("EDIBERT_EXCHANGE_URL", local_server)
    monkeypatch.delenv(ENV_OFF, raising=False)
    catalog = tmp_path / "tariffs.json"
    catalog.write_text(json.dumps({"tariff_format": 1, "package": {"package_id": "p1"},
                                   "import_tariffs": [CATALOG], "export_tariffs": []}), encoding="utf-8")  # fmt: skip
    save_user_tariff(tmp_path / "user_tariffs.json", COPY, IMPORT)
    save_user_tariff(tmp_path / "user_tariffs.json", {**USER, "id": "user_own"}, IMPORT)
    (tmp_path / "publish.json").write_text(json.dumps({
        "mqtt": {"host": "localhost"},
        "tariffs": [{"id": "at_x_fix"}, {"id": "user_copy"}, {"id": "user_own"}],
    }), encoding="utf-8")  # fmt: skip
    code = main(["exchange", "report", "--data-dir", str(tmp_path), "--catalog", str(catalog), "--no-delay"])
    assert code == 0, capsys.readouterr().err
    # catalog tariff and the unchanged copy are the same database version: one report, not two
    assert [path for path, _, _ in _Handler.seen] == ["/edibert/v1/usage"]
    assert set(_Handler.seen[0][1]) == {"db_id", "version", "pseudonym"}


def test_cli_stops_when_switched_off(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(ENV_OFF, "1")
    assert main(["exchange", "fetch", "--out", str(tmp_path / "p.json")]) == 2
    assert main(["exchange", "templates", "--land", "AT", "--direction", "import"]) == 2
    assert ENV_OFF in capsys.readouterr().err


def test_standalone_editor_gets_the_server_transport_unless_switched_off(monkeypatch):
    from edibert.ui.config import config_from_env

    assert config_from_env().contribution_transport is None  # EDIBERT_EXCHANGE_OFF=1 (conftest)
    monkeypatch.delenv(ENV_OFF)
    monkeypatch.setenv("EDIBERT_EXCHANGE_URL", "https://db.test")
    transport = config_from_env().contribution_transport
    assert isinstance(transport, ServerTransport) and transport.client.config.base_url == "https://db.test"
