"""Monthly-table fallback as in Earnie: exact month, same month of the previous year, previous month."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import EXPORT, at, flat_grid_fee, make

from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.i18n import Translator
from edibert.series import tariff_price_series
from edibert.tariff import FALLBACK_PRIOR_MONTH, FALLBACK_PRIOR_YEAR, evaluate


def table(*rows: tuple[int, int, float], direction: str = "import"):
    raw = {
        "id": "m", "type": "monthly_table", "supplier_id": "s", "vat_percent": 20, "prices_include_vat": False,
        "monthly_rates": [{"year": y, "month": m, "tariff_cent_kwh": c} for y, m, c in rows],
    }  # fmt: skip
    return make(raw, direction)


def fallback_of(result):
    assert len(result.warnings) == 1
    note = result.warnings[0]
    assert note.code == WarningCode.MONTH_RATE_FALLBACK
    return dict(note.params)


def test_exact_month_has_no_warning(ctx_plain):
    result = evaluate(table((2026, 10, 10.0), (2025, 10, 7.0)), at("2026-10-12 12:00"), ctx_plain)
    assert result.base_cent == 10.0
    assert result.warnings == ()


def test_prior_year_wins_over_prior_month(ctx_plain):
    tariff = table((2025, 11, 7.0), (2026, 10, 10.0))
    result = evaluate(tariff, at("2026-11-03 12:00"), ctx_plain)
    assert result.base_cent == 7.0
    assert result.cent == 8.4  # the fallback rate goes through VAT like any rate
    assert fallback_of(result) == {
        "tariff_id": "m", "direction": "import", "month": "2026-11", "used_month": "2025-11", "rule": FALLBACK_PRIOR_YEAR,
    }  # fmt: skip


def test_prior_month(ctx_plain):
    result = evaluate(table((2026, 10, 10.0)), at("2026-11-03 12:00"), ctx_plain)
    assert result.base_cent == 10.0
    assert fallback_of(result)["rule"] == FALLBACK_PRIOR_MONTH
    assert fallback_of(result)["used_month"] == "2026-10"


def test_prior_month_crosses_the_year_boundary(ctx_plain):
    """Earnie's ``previous_calendar_month``: January looks at December of the year before."""
    result = evaluate(table((2026, 12, 11.0)), at("2027-01-15 12:00"), ctx_plain)
    assert result.base_cent == 11.0
    assert fallback_of(result) == {
        "tariff_id": "m", "direction": "import", "month": "2027-01", "used_month": "2026-12", "rule": FALLBACK_PRIOR_MONTH,
    }  # fmt: skip


@pytest.mark.parametrize(
    "when",
    [
        "2025-03-10 12:00",  # before the table starts (Earnie fails too)
        "2025-06-30 23:45",  # the month right before the start: no step forward
        "2026-11-01 00:00",  # two months after the end: no fallback of a fallback
    ],
)
def test_missing_after_all_three_steps_is_an_error(ctx_plain, when):
    tariff = table((2025, 7, 5.0), (2025, 8, 5.0), (2026, 9, 6.0))
    with pytest.raises(EdibertError) as err:
        evaluate(tariff, at(when), ctx_plain)
    assert err.value.code == ErrorCode.PRICE_MISSING
    assert err.value.params["tariff_id"] == "m"


def test_export_table_uses_the_same_order(ctx_plain):
    tariff = table((2025, 10, 4.0), (2026, 9, 6.0), direction=EXPORT)
    result = evaluate(tariff, at("2026-10-01 00:00"), ctx_plain)
    assert result.base_cent == 4.0
    assert fallback_of(result)["direction"] == "export"
    assert fallback_of(result)["rule"] == FALLBACK_PRIOR_YEAR


def test_series_reports_each_fallback_month_once(ctx_plain):
    """A 72-hour window from 30 September reaches October: one warning, September stays exact."""
    tariff = table((2025, 10, 4.0), (2026, 9, 6.0), direction=EXPORT)
    series = tariff_price_series(tariff, ctx_plain, at("2026-09-30 00:00"), at("2026-10-03 00:00"), resolution_min=60)
    assert len(series.points) == 72
    assert [p.cent for p in series.points[:24]] == [7.2] * 24  # net + 20 % VAT
    assert [p.cent for p in series.points[24:]] == [4.8] * 48
    fallbacks = [w for w in series.warnings if w.code == WarningCode.MONTH_RATE_FALLBACK]
    assert [dict(w.params) for w in fallbacks] == [
        {"tariff_id": "m", "direction": "export", "month": "2026-10", "used_month": "2025-10", "rule": FALLBACK_PRIOR_YEAR}
    ]


def test_series_month_change_uses_local_time(ctx_plain):
    """The month of a slot is the local month: 31 Oct 23:00 UTC is already November in Vienna."""
    tariff = table((2026, 10, 10.0), (2026, 11, 20.0))
    start = datetime(2026, 10, 31, 22, 0, tzinfo=UTC)
    series = tariff_price_series(tariff, ctx_plain, start, start + timedelta(hours=2), resolution_min=60)
    assert [p.cent for p in series.points] == [12.0, 24.0]
    assert series.warnings == ()


def test_series_with_grid_fee_and_two_fallback_months(ctx_plain):
    tariff = table((2026, 10, 10.0), (2025, 12, 8.0))
    series = tariff_price_series(
        tariff, ctx_plain, at("2026-11-30 22:00"), at("2026-12-01 02:00"), resolution_min=60, grid_fee=flat_grid_fee(5.0)
    )
    assert [p.cent for p in series.points] == [18.0, 18.0, 15.6, 15.6]
    months = [(w.params["month"], w.params["rule"]) for w in series.warnings if w.code == WarningCode.MONTH_RATE_FALLBACK]
    assert months == [("2026-11", FALLBACK_PRIOR_MONTH), ("2026-12", FALLBACK_PRIOR_YEAR)]


def test_series_fails_when_one_month_cannot_be_priced(ctx_plain):
    tariff = table((2026, 9, 6.0))
    with pytest.raises(EdibertError) as err:
        tariff_price_series(tariff, ctx_plain, at("2026-10-31 12:00"), at("2026-11-01 12:00"))
    assert err.value.code == ErrorCode.PRICE_MISSING


@pytest.mark.parametrize("language", ["en", "de"])
def test_warning_text(ctx_plain, language):
    note = evaluate(table((2026, 10, 10.0)), at("2026-11-03 12:00"), ctx_plain).warnings[0]
    text = Translator(language).t(f"warning.{note.code}", **note.params)
    assert "2026-11" in text
    assert "2026-10" in text


def test_a_month_listed_twice_is_an_error():
    """The later row used to win silently; a duplicate month now fails to load."""
    with pytest.raises(EdibertError) as err:
        table((2026, 10, 10.0), (2026, 11, 11.0), (2026, 10, 12.0))
    assert err.value.code == ErrorCode.MONTH_RATE_DUPLICATE
    assert err.value.params == {"field": "m.monthly_rates[2]", "month": "2026-10"}


def test_the_same_month_in_another_year_is_no_duplicate():
    assert table((2025, 10, 7.0), (2026, 10, 10.0)).monthly_rates == {(2025, 10): 7.0, (2026, 10): 10.0}


@pytest.mark.parametrize("key", ["year", "month"])
def test_an_empty_year_or_month_is_a_missing_field(key):
    raw = {"id": "m", "type": "monthly_table", "supplier_id": "s", "vat_percent": 20,
           "monthly_rates": [{"year": 2026, "month": 10, "tariff_cent_kwh": 10.0} | {key: None}]}  # fmt: skip
    with pytest.raises(EdibertError) as err:
        make(raw, "import")
    assert (err.value.code, err.value.params) == (ErrorCode.FIELD_MISSING, {"field": f"m.monthly_rates[0].{key}"})
