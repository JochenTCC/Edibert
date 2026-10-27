"""The day-ahead chain: cache, source order, freshness, partial answers."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from market_helpers import FakeWeb, awattar_json, energy_charts_json, entsoe_xml, utc

from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.market.cache import cache_path
from edibert.market.service import (
    MarketService,
    expected_window,
    last_day_ahead_date,
    window_slots,
)
from edibert.market.sources import SourceError

VIENNA = ZoneInfo("Europe/Vienna")
DAY_START = utc("2026-12-14T23:00")  # 2026-12-15 00:00 in Vienna
MORNING = utc("2026-12-15T09:00")  # 10:00 Vienna: tomorrow is not published yet
AFTERNOON = utc("2026-12-15T12:00")  # 13:00 Vienna: tomorrow is published


def codes(data):
    return [note.code for note in data.notes]


def full_day_ahead(hours):
    return energy_charts_json(DAY_START, hours)


def service(tmp_path, web, token=""):
    return MarketService("AT", tmp_path, entsoe_token=token, get=web)


def test_publish_hour_decides_which_days_are_expected():
    assert last_day_ahead_date(MORNING.astimezone(VIENNA)).isoformat() == "2026-12-15"
    assert last_day_ahead_date(AFTERNOON.astimezone(VIENNA)).isoformat() == "2026-12-16"
    start, end = expected_window(AFTERNOON, VIENNA)
    assert len(window_slots(start, end)) == 192


def test_dst_days_have_92_and_100_slots():
    spring, autumn = utc("2026-03-29T00:00"), utc("2026-10-25T00:00")
    assert len(window_slots(*expected_window(spring.replace(hour=8), VIENNA))) == 92
    assert len(window_slots(*expected_window(autumn.replace(hour=8), VIENNA))) == 100


def test_energy_charts_is_used_without_token_and_the_result_is_cached(tmp_path):
    web = FakeWeb(energy_charts=full_day_ahead(24))
    data = service(tmp_path, web).load(VIENNA, MORNING)
    assert (data.source, data.complete, data.notes) == ("energy-charts", True, ())
    assert web.hosts() == ["api.energy-charts.info"]
    assert cache_path(tmp_path, "AT").exists()
    again = service(tmp_path, FakeWeb()).load(VIENNA, MORNING + timedelta(minutes=5))  # no source reachable
    assert (again.source, again.complete, again.prices) == ("energy-charts", True, data.prices)


def test_token_puts_entsoe_first_and_its_failure_falls_through_with_a_note(tmp_path):
    web = FakeWeb(entsoe=SourceError("HTTP 503 securityToken=hush"), energy_charts=full_day_ahead(24))
    data = service(tmp_path, web, token="hush").load(VIENNA, MORNING)
    assert web.hosts() == ["web-api.tp.entsoe.eu", "api.energy-charts.info"]
    assert codes(data) == [WarningCode.MARKET_SOURCE_FAILED]
    assert "hush" not in data.notes[0].message


def test_entsoe_answer_is_accepted_when_it_covers_the_window(tmp_path):
    xml = entsoe_xml([("2026-12-14T23:00Z", "2026-12-15T23:00Z", "PT60M", dict.fromkeys(range(1, 25), 50.0))])
    web = FakeWeb(entsoe=xml)
    data = service(tmp_path, web, token="t").load(VIENNA, MORNING)
    assert (data.source, data.complete) == ("entsoe", True)
    assert web.hosts() == ["web-api.tp.entsoe.eu"]


def test_after_the_publish_hour_tomorrow_is_required_and_awattar_can_complete_it(tmp_path):
    web = FakeWeb(energy_charts=full_day_ahead(24), awattar=awattar_json(DAY_START, 48))
    data = service(tmp_path, web).load(VIENNA, AFTERNOON)
    assert (data.source, data.complete) == ("awattar", True)
    assert web.hosts() == ["api.energy-charts.info", "api.awattar.at"]
    assert codes(data) == []


def test_old_cache_without_tomorrow_triggers_a_new_request_after_noon(tmp_path):
    service(tmp_path, FakeWeb(energy_charts=full_day_ahead(24))).load(VIENNA, MORNING)
    web = FakeWeb(energy_charts=full_day_ahead(48))
    data = service(tmp_path, web).load(VIENNA, AFTERNOON)
    assert (data.complete, len(web.calls)) == (True, 1)
    assert len(data.prices) >= 192


def test_partial_answer_is_reported_and_asked_again_only_after_the_retry_pause(tmp_path):
    web = FakeWeb(energy_charts=full_day_ahead(24), awattar=SourceError("down"))
    market = service(tmp_path, web)
    first = market.load(VIENNA, AFTERNOON)
    assert first.complete is False
    assert WarningCode.MARKET_DATA_INCOMPLETE in codes(first)
    assert first.notes[-1].params["missing_from"].startswith("2026-12-16T00:00")
    calls = len(web.calls)
    soon = market.load(VIENNA, AFTERNOON + timedelta(minutes=5))
    assert (soon.complete, len(web.calls)) == (False, calls)  # throttled: the sources are not asked again
    web.answers["energy_charts"] = full_day_ahead(48)
    later = market.load(VIENNA, AFTERNOON + timedelta(minutes=11))
    assert (later.complete, later.source) == (True, "energy-charts")


def test_no_source_and_no_cache_is_an_error(tmp_path):
    with pytest.raises(EdibertError) as err:
        service(tmp_path, FakeWeb()).load(VIENNA, MORNING)
    assert err.value.code == ErrorCode.MARKET_DATA_UNAVAILABLE
    assert err.value.params == {"zone": "AT"}


def test_stale_cache_is_kept_when_all_sources_fail(tmp_path):
    service(tmp_path, FakeWeb(energy_charts=full_day_ahead(24))).load(VIENNA, MORNING)
    data = service(tmp_path, FakeWeb()).load(VIENNA, AFTERNOON + timedelta(hours=3))
    assert data.complete is False
    assert data.source == "energy-charts"
    assert WarningCode.MARKET_SOURCE_FAILED in codes(data)


def test_unreadable_cache_is_noted_and_replaced(tmp_path):
    cache_path(tmp_path, "AT").write_text("{ broken", encoding="utf-8")
    data = service(tmp_path, FakeWeb(energy_charts=full_day_ahead(24))).load(VIENNA, MORNING)
    assert codes(data) == [WarningCode.MARKET_CACHE_UNREADABLE]
    assert data.complete is True


def test_switzerland_has_no_third_source(tmp_path):
    web = FakeWeb(energy_charts=SourceError("down"))
    with pytest.raises(EdibertError):
        MarketService("CH", tmp_path, get=web).load(VIENNA, MORNING)
    assert web.hosts() == ["api.energy-charts.info"]


WEEK = timedelta(days=7)


def test_history_days_fetch_the_lead_days_on_a_fresh_install(tmp_path):
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START - WEEK, 8 * 24))
    data = MarketService("AT", tmp_path, get=web, history_days=7).load(VIENNA, MORNING)
    assert (data.source, data.complete) == ("energy-charts", True)
    assert web.calls[0][1]["start"] == "2026-12-07"  # 2026-12-08 00:00 Vienna is 12-07 23:00 UTC
    assert DAY_START - WEEK in data.prices
    assert len(data.prices) == 8 * 96


def test_a_cache_without_the_lead_days_is_asked_again(tmp_path):
    service(tmp_path, FakeWeb(energy_charts=full_day_ahead(24))).load(VIENNA, MORNING)
    web = FakeWeb(energy_charts=energy_charts_json(DAY_START - WEEK, 8 * 24))
    data = MarketService("AT", tmp_path, get=web, history_days=7).load(VIENNA, MORNING + timedelta(minutes=11))
    assert (data.complete, len(web.calls)) == (True, 1)
    cached = MarketService("AT", tmp_path, get=FakeWeb(), history_days=7).load(VIENNA, MORNING + timedelta(minutes=12))
    assert (cached.complete, cached.prices) == (True, data.prices)


def test_missing_lead_days_are_reported_as_incomplete(tmp_path):
    web = FakeWeb(energy_charts=full_day_ahead(24), awattar=SourceError("down"))
    data = MarketService("AT", tmp_path, get=web, history_days=2).load(VIENNA, MORNING)
    assert data.complete is False
    assert data.notes[-1].code == WarningCode.MARKET_DATA_INCOMPLETE
    assert data.notes[-1].params["missing_from"].startswith("2026-12-13T00:00")


@pytest.mark.parametrize("days", [-1, 8])
def test_history_days_outside_the_kept_history_are_invalid(tmp_path, days):
    with pytest.raises(EdibertError) as err:
        MarketService("AT", tmp_path, history_days=days)
    assert err.value.code == ErrorCode.VALUE_INVALID
