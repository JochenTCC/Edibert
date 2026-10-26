"""MQTT publishing: topics, payloads, offline handling, forecasts, configuration."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from market_helpers import FakeWeb, energy_charts_json, utc

from edibert.editor.house import HouseSettings, save_house
from edibert.editor.userstore import save_user_tariff
from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.market.sources import SLOT, SourceError
from edibert.publish.config import parse_publish_config
from edibert.publish.service import build_publisher, seconds_to_next_quarter
from edibert.tariff import IMPORT

MORNING = utc("2026-12-15T09:00")  # 10:00 in Vienna
AFTERNOON = utc("2026-12-15T12:00")  # 13:00: tomorrow's prices are out
DAY_START = utc("2026-12-14T23:00")
FIXED = {"id": "user_fix", "type": "fixed_cent", "supplier_id": "user_s", "label": "Fix", "fix_cent_kwh": 30.0}
SPOT = {"id": "user_spot", "type": "spot_hourly", "supplier_id": "user_s", "label": "Spot", "settlement_fee_cent_kwh": 1.5}
MQTT = {"host": "broker.local", "base_topic": "edibert"}


class FakeLink:
    def __init__(self, settings=None):
        self.settings = settings
        self.sent: dict[str, str] = {}
        self.log: list[str] = []
        self.closed = False

    def publish(self, topic, payload, *, retain=True):
        assert retain
        self.sent[topic] = payload
        self.log.append(topic)

    def close(self):
        self.closed = True

    def attributes(self, tariff_id, direction=IMPORT):
        return json.loads(self.sent[f"edibert/{direction}/{tariff_id}/attributes"])

    def state(self, tariff_id, direction=IMPORT):
        return self.sent[f"edibert/{direction}/{tariff_id}/state"]


def setup(tmp_path, tariffs, web=None, loader=None, **config):
    save_house(tmp_path / "house.json", HouseSettings(timezone="Europe/Vienna", land="AT"))
    for raw in tariffs:
        save_user_tariff(tmp_path / "user_tariffs.json", raw, IMPORT)
    document = {"mqtt": MQTT, "tariffs": [{"id": raw["id"]} for raw in tariffs], **config}
    (tmp_path / "publish.json").write_text(json.dumps(document), encoding="utf-8")
    link = FakeLink()
    extra = {"forecaster_loader": loader} if loader else {}
    publisher = build_publisher(tmp_path, link_factory=lambda settings: link, get=web or FakeWeb(), env={}, **extra)
    return publisher, link


def test_fixed_tariff_is_published_without_any_network_access(tmp_path):
    web = FakeWeb()
    publisher, link = setup(tmp_path, [FIXED], web)
    publisher.announce()
    report = publisher.run_cycle(MORNING)
    assert (report.published, report.offline, web.calls) == (["user_fix"], [], [])
    assert link.state("user_fix") == "0.3"
    attributes = link.attributes("user_fix")
    assert (len(attributes["raw_today"]), len(attributes["raw_tomorrow"]), attributes["tomorrow_valid"]) == (96, 96, True)
    assert attributes["raw_today"][0]["start"] == "2026-12-15T00:00:00+01:00"
    assert attributes["raw_today"][0]["value"] == 0.3
    assert (attributes["unit"], attributes["market"], attributes["quality"]) == ("EUR/kWh", None, "exact")
    assert link.sent["edibert/import/user_fix/availability"] == "online"
    assert link.sent["edibert/status"] == "online"


def test_discovery_registers_a_home_assistant_sensor(tmp_path):
    publisher, link = setup(tmp_path, [FIXED])
    publisher.announce()
    config = json.loads(link.sent["homeassistant/sensor/edibert_import_user_fix/config"])
    assert config["state_topic"] == "edibert/import/user_fix/state"
    assert config["json_attributes_topic"] == "edibert/import/user_fix/attributes"
    assert config["unit_of_measurement"] == "EUR/kWh"
    assert config["unique_id"] == "edibert_import_user_fix"
    assert {"topic": "edibert/status"} in config["availability"]


def test_spot_tariff_uses_the_market_data_and_hides_tomorrow_until_it_exists(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 24, price=lambda i: 100.0))
    publisher, link = setup(tmp_path, [SPOT], web)
    report = publisher.run_cycle(MORNING)
    assert report.published == ["user_spot"]
    assert link.state("user_spot") == "0.115"  # 10 ct market + 1.5 ct fee
    attributes = link.attributes("user_spot")
    assert (len(attributes["raw_today"]), attributes["raw_tomorrow"], attributes["tomorrow_valid"]) == (96, [], False)
    assert attributes["market"]["source"] == "energy-charts"
    assert "CC BY 4.0" in attributes["market"]["attribution"]
    assert attributes["average_today"] == attributes["min_today"] == attributes["max_today"] == 0.115
    assert any(note.code == WarningCode.MARKET_DATA_INCOMPLETE for note in report.notes) is False


def test_tomorrow_appears_after_the_publication(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 48, price=lambda i: 100.0 + i))
    publisher, link = setup(tmp_path, [SPOT], web, resolution_min=60)
    publisher.run_cycle(AFTERNOON)
    attributes = link.attributes("user_spot")
    assert (len(attributes["raw_today"]), len(attributes["raw_tomorrow"]), attributes["resolution_min"]) == (24, 24, 60)
    assert attributes["raw_tomorrow"][0]["start"] == "2026-12-16T00:00:00+01:00"
    assert link.state("user_spot") == str(round((100.0 + 13) / 1000 + 0.015, 5))  # 13:00 Vienna is hour 13 of the day


def test_state_follows_the_clock(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 24, price=lambda i: 100.0 + i))
    publisher, link = setup(tmp_path, [SPOT], web, resolution_min=60)
    publisher.run_cycle(MORNING)
    first = link.state("user_spot")
    publisher.run_cycle(MORNING + timedelta(hours=1))
    assert float(link.state("user_spot")) == pytest.approx(float(first) + 0.001)
    assert link.attributes("user_spot")["next"] == pytest.approx(float(first) + 0.002)


def test_market_failure_takes_only_market_tariffs_offline(tmp_path):
    web = FakeWeb(energy_charts=SourceError("down"), awattar=SourceError("down"))
    publisher, link = setup(tmp_path, [FIXED, SPOT], web)
    report = publisher.run_cycle(MORNING)
    assert report.published == ["user_fix"]
    assert sorted(name for name, _ in report.offline) == ["market", "user_spot"]
    assert link.sent["edibert/import/user_spot/availability"] == "offline"
    assert "edibert/import/user_spot/state" not in link.sent  # nothing is invented
    assert link.sent["edibert/import/user_fix/availability"] == "online"


class FakeForecaster:
    def __init__(self, fail=False):
        self.fail = fail
        self.requests = []

    def forecast(self, known, start, end):
        self.requests.append((start, end))
        if self.fail:
            raise RuntimeError("model broke")
        count = int((end - start) / SLOT)
        return {start + SLOT * index: 20.0 for index in range(count)}


def test_forecaster_plugin_adds_forecast_values_after_the_known_prices(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 24, price=lambda i: 100.0))
    forecaster = FakeForecaster()
    publisher, link = setup(tmp_path, [SPOT], web, loader=lambda name, key: forecaster, forecast={"method": "plugin", "name": "demo", "hours": 24})
    publisher.run_cycle(MORNING)
    attributes = link.attributes("user_spot")
    assert len(attributes["forecast"]) == 96
    assert attributes["forecast"][0]["start"] == "2026-12-16T00:00:00+01:00"
    assert attributes["forecast"][0]["value"] == 0.215  # 20 ct forecast + 1.5 ct fee
    assert forecaster.requests == [(utc("2026-12-15T23:00"), utc("2026-12-16T23:00"))]
    assert attributes["raw_tomorrow"] == []  # a forecast never pretends to be a price


def test_failing_forecaster_leaves_exact_prices_intact_and_is_reported(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 24, price=lambda i: 100.0))
    publisher, link = setup(tmp_path, [SPOT], web, loader=lambda name, key: FakeForecaster(fail=True), forecast={"method": "plugin", "name": "demo"})
    report = publisher.run_cycle(MORNING)
    assert [note.code for note in report.notes] == [WarningCode.FORECAST_FAILED]
    assert link.attributes("user_spot")["forecast"] == []
    assert link.state("user_spot") == "0.115"


def test_missing_forecaster_plugin_is_an_error(tmp_path):
    save_house(tmp_path / "house.json", HouseSettings())
    save_user_tariff(tmp_path / "user_tariffs.json", FIXED, IMPORT)
    document = {"mqtt": MQTT, "tariffs": [{"id": "user_fix"}], "forecast": {"method": "plugin", "name": "nope"}}
    (tmp_path / "publish.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(EdibertError) as err:
        build_publisher(tmp_path, link_factory=FakeLink, env={})
    assert err.value.code == ErrorCode.FORECASTER_UNAVAILABLE


def test_forecast_key_comes_from_the_environment(tmp_path):
    seen = []
    setup(tmp_path, [FIXED], loader=lambda name, key: seen.append((name, key)), forecast={"method": "plugin", "name": "demo"})
    assert seen == [("demo", "")]  # build_publisher passes what the environment holds (nothing here)
    other = build_publisher(tmp_path, link_factory=FakeLink, env={"EDIBERT_FORECAST_KEY": "k"}, forecaster_loader=lambda name, key: seen.append(key))
    assert other.config.forecast.name == "demo"
    assert seen[-1] == "k"


def test_unknown_tariff_in_the_config_is_an_error(tmp_path):
    save_house(tmp_path / "house.json", HouseSettings())
    (tmp_path / "publish.json").write_text(json.dumps({"mqtt": MQTT, "tariffs": [{"id": "user_none"}]}), encoding="utf-8")
    with pytest.raises(EdibertError) as err:
        build_publisher(tmp_path, link_factory=FakeLink, env={})
    assert err.value.code == ErrorCode.VALUE_INVALID


def test_entsoe_token_comes_from_the_environment(tmp_path):
    publisher, _ = setup(tmp_path, [SPOT])
    assert publisher.market.token == ""
    other = build_publisher(tmp_path, link_factory=FakeLink, env={"ENTSOE_API_TOKEN": " abc "})
    assert other.market.token == "abc"


def test_loop_publishes_each_quarter_and_says_offline_on_exit(tmp_path):
    publisher, link = setup(tmp_path, [FIXED])
    times = iter([MORNING, MORNING, MORNING + timedelta(minutes=15), MORNING + timedelta(minutes=15)])
    pauses = []

    def sleep(seconds):
        pauses.append(seconds)
        if len(pauses) == 2:
            raise KeyboardInterrupt

    publisher.run_forever(clock=lambda: next(times), sleep=sleep)
    assert link.closed
    assert link.log.count("edibert/import/user_fix/state") == 2
    assert all(1 <= pause <= 17 * 60 for pause in pauses)


def test_seconds_to_next_quarter():
    assert seconds_to_next_quarter(datetime(2026, 12, 15, 9, 0, 0, tzinfo=UTC)) == 15 * 60 + 2
    assert seconds_to_next_quarter(datetime(2026, 12, 15, 9, 14, 30, tzinfo=UTC)) == 32
    assert seconds_to_next_quarter(datetime(2026, 12, 15, 9, 59, 59, tzinfo=UTC)) == 3


def test_config_accepts_the_documented_shape():
    config = parse_publish_config({
        "mqtt": {"host": "h", "port": 8883, "tls": True, "username_env": "U", "password_env": "P", "base_topic": "/earnie/", "discovery_prefix": "ha"},
        "tariffs": [{"id": "a"}, {"id": "b", "direction": "export"}],
        "resolution_min": 30,
        "forecast": {"method": "plugin", "name": "m", "hours": 12},
    })  # fmt: skip
    assert (config.mqtt.port, config.mqtt.tls, config.mqtt.base_topic, config.mqtt.discovery_prefix) == (8883, True, "earnie", "ha")
    assert [(t.id, t.direction) for t in config.tariffs] == [("a", "import"), ("b", "export")]
    assert (config.resolution_min, config.forecast.hours) == (30, 12)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ({"tariffs": [{"id": "a"}]}, ErrorCode.FIELD_MISSING),
        ({"mqtt": {"host": "h"}}, ErrorCode.FIELD_MISSING),
        ({"mqtt": {"host": "h"}, "tariffs": []}, ErrorCode.VALUE_INVALID),
        ({"mqtt": {"host": "h"}, "tariffs": [{"id": "a"}, {"id": "a"}]}, ErrorCode.VALUE_INVALID),
        ({"mqtt": {"host": "h"}, "tariffs": [{"id": "a", "direction": "sideways"}]}, ErrorCode.VALUE_INVALID),
        ({"mqtt": {"host": "h"}, "tariffs": [{"id": "a"}], "resolution_min": 20}, ErrorCode.VALUE_INVALID),
        ({"mqtt": {"host": "h", "port": 0}, "tariffs": [{"id": "a"}]}, ErrorCode.VALUE_INVALID),
        ({"mqtt": {"host": "h", "password": "x"}, "tariffs": [{"id": "a"}]}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"mqtt": {"host": "h"}, "tariffs": [{"id": "a"}], "oops": 1}, ErrorCode.TARIFF_UNKNOWN_FIELD),
    ],
)
def test_config_errors_are_coded(raw, code):
    with pytest.raises(EdibertError) as err:
        parse_publish_config(raw)
    assert err.value.code == code
