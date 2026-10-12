"""Parsers and request building of the three day-ahead sources."""

import json

import pytest
from market_helpers import FakeWeb, awattar_json, energy_charts_json, entsoe_xml, utc

from edbert.errors import EdbertError, ErrorCode
from edbert.market.sources import (
    SLOT,
    SourceError,
    fetch_awattar,
    fetch_energy_charts,
    fetch_entsoe,
    parse_awattar,
    parse_energy_charts,
    parse_entsoe,
    redact,
    source_label,
    zone_for_land,
)

START = utc("2026-12-14T23:00")
HOUR = "PT60M"


def test_energy_charts_hourly_is_expanded_and_converted_to_cent():
    prices = parse_energy_charts(energy_charts_json(START, 2, price=lambda i: [80.0, 120.0][i]))
    assert [prices[START + SLOT * i] for i in range(8)] == [8.0] * 4 + [12.0] * 4


def test_energy_charts_quarter_hourly_and_null_slots():
    prices = parse_energy_charts(energy_charts_json(START, 1, price=lambda i: None if i == 1 else 50.0 + i, step_min=15))
    assert START + SLOT not in prices  # no price is not a price
    assert prices[START] == 5.0
    assert prices[START + SLOT * 3] == 5.3


@pytest.mark.parametrize("text", ["not json", "{}", json.dumps({"unix_seconds": [], "price": []}), json.dumps({"unix_seconds": [1], "price": []})])
def test_energy_charts_bad_answers_are_source_errors(text):
    with pytest.raises(SourceError):
        parse_energy_charts(text)


def test_awattar_hourly_entries():
    prices = parse_awattar(awattar_json(START, 2))
    assert prices[START] == 9.0
    assert prices[START + SLOT * 7] == 9.1


@pytest.mark.parametrize("text", ["nope", json.dumps({"data": []}), json.dumps({"data": [{"start_timestamp": 0}]})])
def test_awattar_bad_answers_are_source_errors(text):
    with pytest.raises(SourceError):
        parse_awattar(text)


def test_entsoe_hourly_period_and_a03_gaps_are_carried_forward():
    # position 3 is omitted: ENTSO-E means "same price as before"
    xml = entsoe_xml([("2026-12-14T23:00Z", "2026-12-15T03:00Z", HOUR, {1: 100.0, 2: 80.0, 4: 60.0})])
    prices = parse_entsoe(xml)
    hours = [prices[START + SLOT * 4 * i] for i in range(4)]
    assert hours == [10.0, 8.0, 8.0, 6.0]
    assert len(prices) == 16


def test_entsoe_finer_resolution_wins_over_coarser():
    xml = entsoe_xml([
        ("2026-12-14T23:00Z", "2026-12-15T00:00Z", HOUR, {1: 100.0}),
        ("2026-12-14T23:00Z", "2026-12-15T00:00Z", "PT15M", {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0}),
    ])  # fmt: skip
    prices = parse_entsoe(xml)
    assert [prices[START + SLOT * i] for i in range(4)] == [1.0, 2.0, 3.0, 4.0]


def test_entsoe_acknowledgement_is_a_source_error_with_the_reason():
    ack = '<Acknowledgement_MarketDocument xmlns="x"><Reason><code>999</code><text>No matching data found</text></Reason></Acknowledgement_MarketDocument>'
    with pytest.raises(SourceError, match="No matching data"):
        parse_entsoe(ack)


def test_entsoe_broken_documents_are_source_errors():
    with pytest.raises(SourceError):
        parse_entsoe("<broken")
    unsupported = entsoe_xml([("2026-12-14T23:00Z", "2026-12-15T00:00Z", "PT30M", {1: 1.0})])
    with pytest.raises(SourceError):
        parse_entsoe(unsupported)
    no_first_price = entsoe_xml([("2026-12-14T23:00Z", "2026-12-15T01:00Z", HOUR, {2: 1.0})])
    with pytest.raises(SourceError):
        parse_entsoe(no_first_price)


def test_requests_use_the_right_zone_and_dates():
    web = FakeWeb(
        entsoe=entsoe_xml([("2026-12-14T23:00Z", "2026-12-15T00:00Z", HOUR, {1: 1.0})]),
        energy_charts=energy_charts_json(START, 1),
        awattar=awattar_json(START, 1),
    )
    start, end = utc("2026-12-14T23:00"), utc("2026-12-16T23:00")
    fetch_entsoe("DE-LU", start, end, "secret", web, 5)
    fetch_energy_charts("AT", start, end, web, 5)
    fetch_awattar("DE-LU", start, end, web, 5)
    entsoe, charts, awattar = (call[1] for call in web.calls)
    assert (entsoe["in_Domain"], entsoe["periodStart"], entsoe["periodEnd"]) == ("10Y1001A1001A82H", "202612142300", "202612162300")
    assert (charts["bzn"], charts["start"], charts["end"]) == ("AT", "2026-12-14", "2026-12-16")
    assert awattar["start"] == str(int(start.timestamp() * 1000))
    assert web.hosts() == ["web-api.tp.entsoe.eu", "api.energy-charts.info", "api.awattar.de"]


def test_zones_and_labels():
    assert [zone_for_land(land) for land in ("AT", "DE", "CH")] == ["AT", "DE-LU", "CH"]
    with pytest.raises(EdbertError) as err:
        zone_for_land("FR")
    assert err.value.code == ErrorCode.MARKET_ZONE_UNKNOWN
    assert source_label("energy-charts")["license"] == "CC BY 4.0"
    assert source_label("other")["name"] == "other"


def test_token_is_removed_from_error_text():
    text = "boom https://x/api?a=1&securityToken=abc-123&b=2 failed"
    assert redact(text) == "boom https://x/api?a=1&securityToken=REDACTED&b=2 failed"
