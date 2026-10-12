"""The free forecast methods ``hold`` and ``mirror`` and how the publisher uses them."""

import json
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from market_helpers import FakeWeb, energy_charts_json, utc
from test_publish import AFTERNOON, DAY_START, MORNING, SPOT, setup

from edbert.errors import EdbertError, ErrorCode
from edbert.market.forecast import (
    HoldLastForecaster,
    MirrorForecaster,
    build_forecaster,
)
from edbert.market.service import MarketService
from edbert.market.sources import SLOT
from edbert.publish.config import parse_publish_config

VIENNA = ZoneInfo("Europe/Vienna")
MQTT = {"host": "h"}


def day_of_prices(start, base=0.0):
    """One price per quarter hour for 24 hours: ``base`` + slot index."""
    return {start + SLOT * index: base + index for index in range(96)}


def test_hold_keeps_the_last_known_price_constant():
    known = day_of_prices(DAY_START)
    start = DAY_START + timedelta(days=1)
    result = HoldLastForecaster().forecast(known, start, start + timedelta(hours=2))
    assert sorted(result) == [start + SLOT * i for i in range(8)]
    assert set(result.values()) == {95.0}


def test_hold_without_any_earlier_price_returns_nothing():
    assert HoldLastForecaster().forecast({}, DAY_START, DAY_START + timedelta(hours=1)) == {}


def test_mirror_takes_the_same_time_of_day_from_the_nearest_earlier_day():
    known = {**day_of_prices(DAY_START, 1000.0), **day_of_prices(DAY_START - timedelta(days=1), 0.0)}
    start = DAY_START + timedelta(days=2)  # the day after tomorrow: tomorrow has no price
    result = MirrorForecaster(VIENNA).forecast(known, start, start + timedelta(hours=1))
    assert [result[start + SLOT * i] for i in range(4)] == [1000.0, 1001.0, 1002.0, 1003.0]


def test_mirror_does_not_look_further_back_than_seven_days_and_leaves_gaps():
    known = day_of_prices(DAY_START)
    near, far = DAY_START + timedelta(days=7), DAY_START + timedelta(days=8)
    result = MirrorForecaster(VIENNA).forecast(known, near, far + SLOT)
    assert near in result
    assert far not in result  # 8 days back is too old; nothing is invented


def test_mirror_follows_the_wall_clock_across_the_summer_to_winter_change():
    friday_10 = utc("2026-10-23T08:00")  # 10:00 in Vienna (UTC+2)
    monday_10 = utc("2026-10-26T09:00")  # 10:00 in Vienna (UTC+1) after the clock change
    result = MirrorForecaster(VIENNA).forecast({friday_10: 7.0}, monday_10, monday_10 + SLOT)
    assert result == {monday_10: 7.0}


def test_builder_chooses_the_method():
    assert isinstance(build_forecaster("hold", "", "", VIENNA), HoldLastForecaster)
    assert isinstance(build_forecaster("mirror", "", "", VIENNA), MirrorForecaster)
    sentinel = object()
    assert build_forecaster("plugin", "p", "k", VIENNA, loader=lambda name, key: (name, key, sentinel)) == ("p", "k", sentinel)


def forecast_of(tmp_path, method, hours, prices, **config):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 24, price=prices))
    publisher, link = setup(tmp_path, [SPOT], web, resolution_min=60, forecast={"method": method, "hours": hours}, **config)
    publisher.run_cycle(MORNING)
    return link.attributes("user_spot")


def test_mirror_forecast_is_published_for_the_day_after_the_known_prices(tmp_path):
    attributes = forecast_of(tmp_path, "mirror", 24, lambda hour: 100.0 + hour)
    assert attributes["forecast_method"] == "mirror"
    assert [item["start"][:13] for item in attributes["forecast"][:2]] == ["2026-12-16T00", "2026-12-16T01"]
    assert [item["value"] for item in attributes["forecast"][:2]] == [0.115, 0.116]  # same hours of today plus 1.5 ct
    assert attributes["raw_tomorrow"] == []
    assert attributes["tomorrow_valid"] is False


def test_hold_forecast_is_a_constant_line(tmp_path):
    attributes = forecast_of(tmp_path, "hold", 24, lambda hour: 100.0 + hour)
    assert len(attributes["forecast"]) == 24
    assert {item["value"] for item in attributes["forecast"]} == {0.138}  # 123 EUR/MWh from 23:00 plus 1.5 ct


class PartialForecaster:
    """Knows only the first ten quarter hours."""

    def forecast(self, known, start, end):
        return {start + SLOT * index: 20.0 for index in range(10)}


def test_forecast_stops_at_the_last_whole_hour_without_a_gap(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 24))
    publisher, link = setup(tmp_path, [SPOT], web, loader=lambda name, key: PartialForecaster(), resolution_min=60, forecast={"method": "plugin", "name": "p", "hours": 24})
    report = publisher.run_cycle(MORNING)
    assert report.notes == []
    assert len(link.attributes("user_spot")["forecast"]) == 2  # 10 quarter hours -> 2 whole hours


def test_no_forecast_section_means_no_forecast(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 24))
    publisher, link = setup(tmp_path, [SPOT], web)
    publisher.run_cycle(MORNING)
    attributes = link.attributes("user_spot")
    assert (attributes["forecast"], attributes["forecast_method"]) == ([], None)


def test_cache_keeps_the_history_that_mirroring_needs(tmp_path):
    first = MarketService("AT", tmp_path, get=FakeWeb(energy_charts=energy_charts_json(DAY_START, 24)))
    first.load(VIENNA, MORNING)
    tomorrow = DAY_START + timedelta(days=1)
    second = MarketService("AT", tmp_path, get=FakeWeb(energy_charts=energy_charts_json(tomorrow, 24)))
    data = second.load(VIENNA, MORNING + timedelta(days=1))
    assert DAY_START in data.prices  # yesterday is still there
    assert tomorrow in data.prices
    assert min(data.prices) >= MORNING - timedelta(days=8)


def test_forecast_hours_are_limited_to_72():
    assert parse_publish_config({"mqtt": MQTT, "tariffs": [{"id": "a"}], "forecast": {"hours": 72}}).forecast.hours == 72
    with pytest.raises(EdbertError) as err:
        parse_publish_config({"mqtt": MQTT, "tariffs": [{"id": "a"}], "forecast": {"hours": 73}})
    assert err.value.code == ErrorCode.VALUE_INVALID


def test_config_method_rules():
    assert parse_publish_config({"mqtt": MQTT, "tariffs": [{"id": "a"}], "forecast": {}}).forecast.method == "mirror"
    with pytest.raises(EdbertError) as err:
        parse_publish_config({"mqtt": MQTT, "tariffs": [{"id": "a"}], "forecast": {"method": "crystal-ball"}})
    assert err.value.code == ErrorCode.VALUE_INVALID
    with pytest.raises(EdbertError) as err:
        parse_publish_config({"mqtt": MQTT, "tariffs": [{"id": "a"}], "forecast": {"method": "plugin"}})
    assert err.value.code == ErrorCode.FIELD_MISSING
    with pytest.raises(EdbertError) as err:
        parse_publish_config({"mqtt": MQTT, "tariffs": [{"id": "a"}], "forecast": {"method": "hold", "name": "x"}})
    assert err.value.code == ErrorCode.VALUE_INVALID


def test_afternoon_with_tomorrow_known_mirrors_after_tomorrow(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START, 48, price=lambda hour: 100.0 + hour))
    publisher, link = setup(tmp_path, [SPOT], web, resolution_min=60, forecast={"method": "mirror", "hours": 24})
    publisher.run_cycle(AFTERNOON)
    forecast = link.attributes("user_spot")["forecast"]
    assert forecast[0]["start"].startswith("2026-12-17T00")
    assert forecast[0]["value"] == 0.139  # tomorrow's 00:00 (hour 24 = 124 EUR/MWh) plus 1.5 ct
    assert json.loads(link.sent["edbert/import/user_spot/attributes"])["tomorrow_valid"] is True
