"""Time windows, seasons and real-world shaped fixtures (VKW Strom Duo window, Octopus Go shape)."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import at, make

from edibert.tariff import evaluate, price_cent

STANDARD = {"id": "t", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0, "vat_percent": 20}


def slot_series(day: str, ctx):
    start = datetime.fromisoformat(day).replace(tzinfo=ctx.tz)
    return [start + timedelta(minutes=15 * i) for i in range(96)]


def test_octopus_go_shape_cheap_window_00_to_05(ctx_plain):
    tariff = make(STANDARD, rules=[
        {"id": "go", "time": {"from": "00:00", "to": "05:00"}, "effect": {"mode": "absolute_cent", "value": 22.0}}
    ])  # fmt: skip
    assert price_cent(tariff, at("2026-10-12 04:45"), ctx_plain) == 22.0
    assert price_cent(tariff, at("2026-10-12 05:00"), ctx_plain) == 30.0
    assert price_cent(tariff, at("2026-10-12 00:00"), ctx_plain) == 22.0


def test_vkw_strom_duo_window_averages_to_the_catalog_monthly_mean(ctx_plain):
    # Earnie catalog 'at_vkw_strom_duo': 9.40 ct net, summer window 10-16 at 8.40 ct net.
    # The catalog models the Apr-Sep mean (9.15) as a monthly table; the real window must average to it.
    tariff = make(
        {"id": "duo", "type": "fixed_cent", "supplier_id": "vkw", "fix_cent_kwh": 9.40,
         "prices_include_vat": False, "vat_percent": 20.0},
        rules=[{"id": "summer", "months": [4, 5, 6, 7, 8, 9], "time": {"from": "10:00", "to": "16:00"},
                "effect": {"mode": "absolute_cent", "value": 8.40}}],
    )  # fmt: skip
    nets = [evaluate(tariff, s, ctx_plain).after_limits_cent for s in slot_series("2026-07-15", ctx_plain)]
    assert sum(nets) / len(nets) == pytest.approx(9.15)
    winter = [evaluate(tariff, s, ctx_plain).after_limits_cent for s in slot_series("2026-12-15", ctx_plain)]
    assert set(winter) == {9.40}


def test_ht_nt_with_quarter_hour_boundaries(ctx_plain):
    # shape of a published grid-operator table: high tariff 17:15-19:15, low tariff 00:00-07:00
    tariff = make(STANDARD, rules=[
        {"id": "ht", "time": {"from": "17:15", "to": "19:15"}, "effect": {"mode": "absolute_cent", "value": 17.0}},
        {"id": "nt", "time": {"from": "00:00", "to": "07:00"}, "effect": {"mode": "absolute_cent", "value": 3.0}},
    ])  # fmt: skip
    assert price_cent(tariff, at("2026-10-12 17:00"), ctx_plain) == 30.0
    assert price_cent(tariff, at("2026-10-12 17:15"), ctx_plain) == 17.0
    assert price_cent(tariff, at("2026-10-12 19:00"), ctx_plain) == 17.0
    assert price_cent(tariff, at("2026-10-12 19:15"), ctx_plain) == 30.0
    assert price_cent(tariff, at("2026-10-12 06:45"), ctx_plain) == 3.0


def test_two_windows_with_the_same_effect(ctx_plain):
    rules = [
        {"id": f"ht{n}", "time": {"from": a, "to": b}, "effect": {"mode": "absolute_cent", "value": 12.0}}
        for n, (a, b) in enumerate((("18:00", "21:00"), ("23:00", "06:00")))
    ]
    tariff = make(STANDARD, rules=rules)
    assert [price_cent(tariff, at(f"2026-10-12 {t}"), ctx_plain) for t in ("19:00", "22:00", "23:30", "03:00")] == [
        12.0, 30.0, 12.0, 12.0,
    ]  # fmt: skip


def test_window_over_midnight_uses_local_time_across_dst(ctx_plain):
    tariff = make(STANDARD, rules=[
        {"id": "night", "time": {"from": "22:00", "to": "06:00"}, "effect": {"mode": "absolute_cent", "value": 20.0}}
    ])  # fmt: skip
    utc = UTC
    assert price_cent(tariff, datetime(2026, 10, 12, 20, 30, tzinfo=utc), ctx_plain) == 20.0  # 22:30 CEST
    assert price_cent(tariff, datetime(2026, 10, 12, 19, 30, tzinfo=utc), ctx_plain) == 30.0  # 21:30 CEST
    assert price_cent(tariff, datetime(2026, 10, 25, 21, 30, tzinfo=utc), ctx_plain) == 20.0  # 22:30 CET


def test_effects_add_and_percent(ctx_plain):
    add = make(STANDARD, rules=[{"id": "a", "effect": {"mode": "add_cent", "value": 2.5}}])
    pct = make(STANDARD, rules=[{"id": "p", "effect": {"mode": "percent_off", "value": 20}}])
    assert price_cent(add, at("2026-10-12 12:00"), ctx_plain) == 32.5
    assert price_cent(pct, at("2026-10-12 12:00"), ctx_plain) == 24.0


def test_validity_window_of_a_rule(ctx_plain):
    tariff = make(STANDARD, rules=[
        {"id": "promo", "valid_from": "2026-11-01", "valid_to": "2026-11-30", "effect": {"mode": "add_cent", "value": -5}}
    ])  # fmt: skip
    assert price_cent(tariff, at("2026-10-31 12:00"), ctx_plain) == 30.0
    assert price_cent(tariff, at("2026-11-30 23:45"), ctx_plain) == 25.0
    assert price_cent(tariff, at("2026-12-01 00:00"), ctx_plain) == 30.0


def test_monthly_table_is_strict_beyond_the_fallback(ctx_plain):
    from edibert.errors import EdibertError, ErrorCode

    tariff = make({"id": "m", "type": "monthly_table", "supplier_id": "s", "vat_percent": 20,
                   "monthly_rates": [{"year": 2026, "month": 10, "tariff_cent_kwh": 9.0}]})  # fmt: skip
    assert price_cent(tariff, at("2026-10-12 12:00"), ctx_plain) == 9.0
    december = at("2026-12-02 12:00")  # neither 2025-12 nor 2026-11: no second step back
    with pytest.raises(EdibertError) as err:
        price_cent(tariff, december, ctx_plain)
    assert err.value.code == ErrorCode.PRICE_MISSING
