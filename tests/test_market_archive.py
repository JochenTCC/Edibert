"""Market prices for arbitrary ranges: month cache, DST in UTC, HTTP 429, gaps, prices known at a moment."""

import email.message
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import make
from market_helpers import FakeWeb, energy_charts_json, utc

from edibert.context import PricingContext
from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.market import sources
from edibert.market.archive import ARCHIVE_DIR, MarketArchive, known_at, market_range
from edibert.market.sources import SLOT, RateLimited, parse_energy_charts
from edibert.series import tariff_price_series

VIENNA = ZoneInfo("Europe/Vienna")
NOW = utc("2026-10-26T10:00")


def stamp_price(stamp: int) -> float:
    """EUR/MWh that differs for every quarter hour (so a mixed-up hour shows)."""
    return float(stamp // 900 % 97)


def charts(skip=lambda stamp: False):
    """Energy-Charts answer for the requested dates: quarter-hourly from 2025-10, hourly before (UTC days)."""

    def answer(params):
        first = datetime.fromisoformat(params["start"]).replace(tzinfo=UTC)
        last = datetime.fromisoformat(params["end"]).replace(tzinfo=UTC) + timedelta(days=1)
        stamps, moment = [], first
        while moment < last:
            stamps.append(int(moment.timestamp()))
            moment += SLOT if moment >= utc("2025-10-01T00:00") else timedelta(hours=1)
        prices = [None if skip(stamp) else stamp_price(stamp) for stamp in stamps]
        return json.dumps({"unix_seconds": stamps, "price": prices})

    return answer


def archive(tmp_path, web, now=NOW, **extra):
    waits = []
    return MarketArchive("AT", tmp_path, get=web, clock=lambda: now, sleep=waits.append, **extra), waits


def cent_at(moment: datetime) -> float:
    return stamp_price(int(moment.timestamp())) / 10


def test_autumn_dst_night_keeps_both_repeated_hours(tmp_path):
    web = FakeWeb(energy_charts=charts())
    start, end = utc("2025-10-25T22:00"), utc("2025-10-26T03:00")  # 00:00 CEST to 04:00 CET: five hours
    result, _ = archive(tmp_path, web)
    data = result.prices(start, end)
    assert (len(data.prices), data.complete, data.notes) == (20, True, ())
    assert all(data.prices[slot] == cent_at(slot) for slot in data.prices)
    ctx = PricingContext("Europe/Vienna")
    spot = make({"id": "sp", "type": "spot_hourly", "supplier_id": "s", "prices_include_vat": False,
                 "vat_percent": 0, "settlement_mtu": "60min"})  # fmt: skip
    series = tariff_price_series(spot, ctx, start, end, resolution_min=60, market=data.prices)
    assert [p.start.strftime("%H:%M%z") for p in series.points][2:4] == ["02:00+0200", "02:00+0100"]
    first, second = series.points[2], series.points[3]
    assert first.market_cent != second.market_cent  # each real hour has its own mean
    assert first.market_cent == pytest.approx(sum(cent_at(utc("2025-10-26T00:00") + SLOT * i) for i in range(4)) / 4)


def test_months_are_cached_and_not_asked_again(tmp_path):
    web = FakeWeb(energy_charts=charts())
    start, end = utc("2025-09-30T22:00"), utc("2025-11-01T00:15")
    data = archive(tmp_path, web)[0].prices(start, end)
    assert data.complete
    assert len(web.calls) == 3  # September, October, November (one slot of it)
    assert [call[1]["start"] for call in web.calls] == ["2025-08-31", "2025-09-30", "2025-10-31"]
    files = sorted(path.name for path in (tmp_path / ARCHIVE_DIR / "AT").iterdir())
    assert files == ["2025-09.json", "2025-10.json", "2025-11.json"]
    offline = FakeWeb()
    again = archive(tmp_path, offline, now=NOW + timedelta(days=30))[0].prices(start, end)
    assert again.prices == data.prices
    assert offline.calls == []


def test_hourly_months_are_expanded_to_quarter_hours(tmp_path):
    start = utc("2025-03-01T00:00")
    data = archive(tmp_path, FakeWeb(energy_charts=charts()))[0].prices(start, start + timedelta(hours=2))
    assert len(data.prices) == 8
    assert data.prices[start + SLOT * 3] == data.prices[start] == cent_at(start)


def test_rate_limit_is_waited_out(tmp_path):
    answers = [RateLimited("429", 7.0), RateLimited("429", None), charts()]

    def web(url, params, timeout):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer(params)

    result, waits = archive(tmp_path, web)
    data = result.prices(utc("2025-03-01T00:00"), utc("2025-03-01T01:00"))
    assert data.complete
    assert waits == [7.0, 120.0]  # Retry-After, else a growing pause (second attempt: 2 x 60 s)


def test_rate_limit_without_end_is_reported_then_an_error(tmp_path):
    web = FakeWeb(energy_charts=RateLimited("HTTP 429", None))
    result, waits = archive(tmp_path, web, max_attempts=3)
    with pytest.raises(EdibertError) as err:
        result.prices(utc("2025-03-01T00:00"), utc("2025-03-01T01:00"))
    assert err.value.code == ErrorCode.MARKET_DATA_UNAVAILABLE
    assert len(web.calls) == 3
    assert waits == [60.0, 120.0]


def test_a_failing_month_beside_a_cached_one_is_reported(tmp_path):
    archive(tmp_path, FakeWeb(energy_charts=charts()))[0].prices(utc("2025-03-01T00:00"), utc("2025-03-02T00:00"))
    data = archive(tmp_path, FakeWeb())[0].prices(utc("2025-02-28T23:00"), utc("2025-03-01T01:00"))
    assert len(data.prices) == 4
    assert data.missing[0] == utc("2025-02-28T23:00")
    assert [note.code for note in data.notes] == [WarningCode.MARKET_SOURCE_FAILED, WarningCode.MARKET_RANGE_INCOMPLETE]
    incomplete = data.notes[-1].params
    assert (incomplete["missing_slots"], incomplete["missing_from"]) == (4, "2025-02-28T23:00:00+00:00")


def test_gaps_are_reported_and_never_filled(tmp_path):
    gap = int(utc("2025-11-05T10:15").timestamp())
    web = FakeWeb(energy_charts=charts(skip=lambda stamp: stamp == gap))
    data = archive(tmp_path, web)[0].prices(utc("2025-11-05T10:00"), utc("2025-11-05T11:00"))
    assert data.missing == (utc("2025-11-05T10:15"),)
    assert utc("2025-11-05T10:15") not in data.prices
    assert data.notes[-1].code == WarningCode.MARKET_RANGE_INCOMPLETE
    again = FakeWeb()  # asked long after the month: the gap is final, no new request
    archive(tmp_path, again, now=NOW + timedelta(days=1))[0].prices(utc("2025-11-05T10:00"), utc("2025-11-05T11:00"))
    assert again.calls == []


def test_the_current_month_is_asked_again_after_the_retry_pause(tmp_path):
    now = utc("2026-10-26T10:00")  # tomorrow's prices are not there yet
    published_until = utc("2026-10-26T23:00")
    web = FakeWeb(energy_charts=charts(skip=lambda stamp: stamp >= published_until.timestamp()))
    first = archive(tmp_path, web, now=now)[0].prices(utc("2026-10-26T22:00"), utc("2026-10-27T00:00"))
    assert len(first.missing) == 4
    archive(tmp_path, web, now=now + timedelta(minutes=5))[0].prices(utc("2026-10-26T22:00"), utc("2026-10-27T00:00"))
    assert len(web.calls) == 1  # inside the retry pause
    web.answers["energy_charts"] = charts()
    later = archive(tmp_path, web, now=now + timedelta(hours=3))[0].prices(utc("2026-10-26T22:00"), utc("2026-10-27T00:00"))
    assert len(web.calls) == 2
    assert later.complete


def test_future_months_are_not_requested(tmp_path):
    web = FakeWeb(energy_charts=charts())
    with pytest.raises(EdibertError) as err:
        archive(tmp_path, web)[0].prices(utc("2027-01-01T00:00"), utc("2027-01-02T00:00"))
    assert err.value.code == ErrorCode.MARKET_DATA_UNAVAILABLE
    assert web.calls == []


def test_damaged_cache_is_reported_and_rebuilt(tmp_path):
    path = tmp_path / ARCHIVE_DIR / "AT" / "2025-03.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    data = archive(tmp_path, FakeWeb(energy_charts=charts()))[0].prices(utc("2025-03-01T00:00"), utc("2025-03-01T01:00"))
    assert data.complete
    assert [note.code for note in data.notes] == [WarningCode.MARKET_CACHE_UNREADABLE]
    assert json.loads(path.read_text(encoding="utf-8"))["zone"] == "AT"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2025, 3, 1, 0, 0), datetime(2025, 3, 1, 1, 0)),  # naive: no instant without a time zone
        (utc("2025-03-01T00:10"), utc("2025-03-01T01:00")),
        (utc("2025-03-01T01:00"), utc("2025-03-01T01:00")),
    ],
)
def test_bad_ranges_are_errors(tmp_path, start, end):
    with pytest.raises(EdibertError) as err:
        archive(tmp_path, FakeWeb())[0].prices(start, end)
    assert err.value.code == ErrorCode.VALUE_INVALID


def test_unknown_zone_is_an_error(tmp_path):
    with pytest.raises(EdibertError) as err:
        MarketArchive("FR", tmp_path)
    assert err.value.code == ErrorCode.VALUE_INVALID


def test_market_range_uses_the_archive(tmp_path, monkeypatch):
    web = FakeWeb(energy_charts=charts())
    monkeypatch.setattr("edibert.market.archive.http_get", web)
    data = market_range("AT", utc("2025-03-01T00:00"), utc("2025-03-01T01:00"), tmp_path)
    assert (data.zone, len(data.prices)) == ("AT", 4)
    assert len(web.calls) == 1


def test_known_at_follows_the_publish_hour():
    prices = {utc("2026-10-25T23:00") + SLOT * i: 1.0 for i in range(96 * 3)}  # 26, 27 and 28 October (Vienna)
    morning = known_at(prices, utc("2026-10-26T10:00"), VIENNA)  # 11:00: tomorrow not published
    afternoon = known_at(prices, utc("2026-10-26T11:00"), VIENNA)  # 12:00: tomorrow published
    assert max(morning).astimezone(VIENNA).isoformat() == "2026-10-26T23:45:00+01:00"
    assert max(afternoon).astimezone(VIENNA).isoformat() == "2026-10-27T23:45:00+01:00"
    with pytest.raises(EdibertError):
        known_at(prices, datetime(2026, 10, 26, 12), VIENNA)


def test_http_429_becomes_rate_limited(monkeypatch):
    headers = email.message.Message()
    headers["Retry-After"] = "30"

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", headers, None)

    monkeypatch.setattr(sources.urllib.request, "urlopen", refuse)
    with pytest.raises(RateLimited) as err:
        sources.http_get(sources.ENERGY_CHARTS_URL, {"bzn": "AT"}, 5)
    assert err.value.retry_after == 30.0
    headers.replace_header("Retry-After", "Wed, 21 Oct 2026 07:28:00 GMT")
    with pytest.raises(RateLimited) as err:
        sources.http_get(sources.ENERGY_CHARTS_URL, {"bzn": "AT"}, 5)
    assert err.value.retry_after is None


def test_other_http_errors_stay_source_errors(monkeypatch):
    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", email.message.Message(), None)

    monkeypatch.setattr(sources.urllib.request, "urlopen", fail)
    with pytest.raises(sources.SourceError) as err:
        sources.http_get(sources.ENERGY_CHARTS_URL, {}, 5)
    assert not isinstance(err.value, RateLimited)


def test_a_gap_in_the_timestamps_is_not_filled():
    start = utc("2025-03-01T00:00")
    data = json.loads(energy_charts_json(start, 2))  # two hourly values ...
    data["unix_seconds"].append(int((start + timedelta(hours=4)).timestamp()))  # ... and one after a gap
    data["price"].append(50.0)
    prices = parse_energy_charts(json.dumps(data))
    hours = [start, start + timedelta(hours=1), start + timedelta(hours=4)]
    assert sorted(prices) == [hour + SLOT * i for hour in hours for i in range(4)]
