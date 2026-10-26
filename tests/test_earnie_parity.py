"""Compatibility with Earnie: Edibert prices the committed Earnie fixtures (``tests/fixtures/earnie_parity``).

``expected_prices.json`` is Earnie's P3a fixture (9 catalog tariffs x 4 windows: DST spring and autumn, month
change with SNAP start, SNAP day); ``monthly_fallback.json`` holds Earnie's prices on the edge months of monthly
tables (72-hour windows across a month change). Both come from Earnie's engine, see ``make_fixture.py``.
Tolerance as in Earnie's harness: absolute ``1e-4`` ct per slot, no relative tolerance.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from edibert import api

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "earnie_parity"
TOLERANCE = 1e-4
# Triaged deviation T1 (Earnie docs/dev/edibert-integration.md, P3a triage): on the autumn DST night Earnie
# groups the hourly mean by wall-clock hour and averages both 02:00 hours (eight quarter-hours) for hourly
# settled spot tariffs. Edibert prices each real hour; that is correct and stays.
DST_REPEATED_HOUR = {
    ("dst_autumn_2025", "import", "awattar_at"),
    ("dst_autumn_2025", "export", "dynamic_epex"),
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


TARIFFS = api.load_tariffs(FIXTURES / "tariffs.json")
GRID_FEES = api.load_grid_fees(FIXTURES / "grid_fees.json")


def _params(name: str) -> list:
    document = _load(name)
    return [
        pytest.param(window, expected, id=f"{window['name']}-{expected['direction']}-{expected['tariff_id']}-{expected['area_id']}")
        for window in document["windows"]
        for expected in window["expected"]
    ]


def _series(window: dict, expected: dict) -> tuple[list[datetime], api.PriceSeries]:
    """Edibert's series for one fixture case, ``netznutzung`` as Earnie writes it into a house profile."""
    slots = [datetime.fromisoformat(slot) for slot in window["slots"]]
    tariff = TARIFFS.get(expected["direction"], expected["tariff_id"])
    grid_fee = None
    if expected["area_id"]:
        config = api.parse_grid_fee_config({
            "area_id": expected["area_id"], "power_metering": "unmetered_power",
            "quarter_hour_meter": True, "include_status": ["verordnet"],
        })  # fmt: skip
        grid_fee = api.resolve_grid_fee(config, GRID_FEES)
    ctx = api.pricing_context("Europe/Vienna", expected["land"])
    market = dict(zip(slots, window["epex_cent"], strict=True)) if tariff.uses_market_price else None
    series = api.tariff_price_series(tariff, ctx, slots[0], slots[-1] + timedelta(minutes=15), market=market, grid_fee=grid_fee)
    return slots, series


def _assert_grid(series: api.PriceSeries, expected: dict) -> None:
    if expected["grid_net_cent"] is not None:
        assert [p.grid_cent for p in series.points] == pytest.approx(expected["grid_net_cent"], abs=TOLERANCE)


@pytest.mark.parametrize(("window", "expected"), _params("expected_prices.json"))
def test_matches_earnie_fixture(window, expected):
    slots, series = _series(window, expected)
    cents = [p.cent for p in series.points]
    assert len(cents) == len(expected["cent"])
    if (window["name"], expected["direction"], expected["tariff_id"]) in DST_REPEATED_HOUR:
        repeated = [slot.hour == 2 for slot in slots]  # 02:00 CEST and 02:00 CET
        assert sum(repeated) == 8
        hours = [cents[i : i + 4] for i in range(0, len(cents), 4)]
        assert all(len(set(hour)) == 1 for hour in hours)  # one price per real hour
        assert hours[2][0] != hours[3][0]  # the two 02:00 hours are priced apart
        assert expected["cent"][8:16] == [expected["cent"][8]] * 8  # Earnie: one shared mean
        markets = [p.market_cent for p in series.points]
        assert markets[8] == pytest.approx(sum(window["epex_cent"][8:12]) / 4, abs=TOLERANCE)  # 02:00 CEST alone
        assert markets[12] == pytest.approx(sum(window["epex_cent"][12:16]) / 4, abs=TOLERANCE)  # 02:00 CET alone
        others = [(c, e) for c, e, r in zip(cents, expected["cent"], repeated, strict=True) if not r]
        assert [c for c, _ in others] == pytest.approx([e for _, e in others], abs=TOLERANCE)
    else:
        assert cents == pytest.approx(expected["cent"], abs=TOLERANCE)
    _assert_grid(series, expected)
    assert {p.method for p in series.points} == {api.METHOD_EXACT}


def test_fixture_covers_dst_snap_and_t1():
    windows = {window["name"]: window for window in _load("expected_prices.json")["windows"]}
    assert len(windows["dst_spring_2026"]["slots"]) == 12  # 23-hour day: 00:00-04:00 is 3 h
    assert len(windows["dst_autumn_2025"]["slots"]) == 20  # 25-hour day: 00:00-04:00 is 5 h
    tariffs = {(e["direction"], e["tariff_id"]) for e in windows["dst_autumn_2025"]["expected"]}
    assert {(d, t) for _, d, t in DST_REPEATED_HOUR} <= tariffs
    hourly = {(d, t) for d, t in tariffs if TARIFFS.get(d, t).is_spot and TARIFFS.get(d, t).settlement_mtu == "60min"}
    assert hourly == {(d, t) for _, d, t in DST_REPEATED_HOUR}  # T1 covers every hourly settled tariff here


@pytest.mark.parametrize(("window", "expected"), _params("monthly_fallback.json"))
def test_monthly_fallback_matches_earnie(window, expected):
    if "error" in expected:  # Earnie cannot price the window either
        with pytest.raises(api.EdibertError) as err:
            _series(window, expected)
        assert err.value.code == api.ErrorCode.PRICE_MISSING
        assert err.value.params["tariff_id"] == expected["tariff_id"]
        return
    _slots, series = _series(window, expected)
    assert [p.cent for p in series.points] == pytest.approx(expected["cent"], abs=TOLERANCE)
    _assert_grid(series, expected)
    fallbacks = [dict(w.params) for w in series.warnings if w.code == api.WarningCode.MONTH_RATE_FALLBACK]
    common = {"tariff_id": expected["tariff_id"], "direction": expected["direction"]}
    assert fallbacks == [common | item for item in expected["fallbacks"]]


def test_fallback_fixture_covers_the_catalog_edge_months():
    windows = {window["name"]: window for window in _load("monthly_fallback.json")["windows"]}
    rules = {
        item["rule"]
        for window in windows.values()
        for expected in window["expected"]
        for item in expected.get("fallbacks", [])
    }
    assert rules == {api.FALLBACK_PRIOR_YEAR, api.FALLBACK_PRIOR_MONTH}
    assert all(len(window["slots"]) == 288 for name, window in windows.items() if name != "prior_month_year_boundary")
    errors = {e["tariff_id"] for window in windows.values() for e in window["expected"] if "error" in e}
    assert errors == {"at_vkw_pv_flex", "at_oemag_gesetzlicher_marktpreis"}  # before the start / no second step back
