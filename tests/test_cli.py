from pathlib import Path

from conftest import EXAMPLES

from edbert.cli import main

MARKET = Path(__file__).resolve().parent / "fixtures" / "market_2026-12-15.csv"


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_price_command_german_decimal_comma(capsys):
    code, out, _ = run(
        capsys, "--lang", "de", "price", "--tariff", str(EXAMPLES / "spot_evening_surcharge_cap.json"),
        "--at", "2026-12-15T18:00", "--tz", "Europe/Vienna", "--epex", "10",
    )  # fmt: skip
    assert code == 0
    assert "Angewendete Regel: evening" in out
    assert "Preis inkl. 20,00 % USt: 16,56 ct/kWh" in out


def test_price_command_english_with_region(capsys):
    code, out, _ = run(
        capsys, "price", "--tariff", str(EXAMPLES / "fixed_day_night.json"),
        "--at", "2026-12-25T12:00", "--tz", "Europe/Berlin", "--land", "DE", "--region", "BY",
    )  # fmt: skip
    assert code == 0
    assert "Rule applied: weekend" in out
    assert "Price: 27.00 ct/kWh" in out


def test_missing_region_is_reported_in_the_chosen_language(capsys):
    code, out, err = run(
        capsys, "--lang", "de", "price", "--tariff", str(EXAMPLES / "fixed_day_night.json"),
        "--at", "2026-12-25T12:00", "--tz", "Europe/Berlin",
    )  # fmt: skip
    assert code == 2
    assert out == ""
    assert "Region" in err


def test_bad_time_is_reported(capsys):
    code, _, err = run(
        capsys, "price", "--tariff", str(EXAMPLES / "fixed_day_night.json"), "--at", "tomorrow", "--tz", "Europe/Berlin"
    )  # fmt: skip
    assert code == 2
    assert "--at" in err


def test_price_with_grid_fee_shows_grid_lines(capsys):
    code, out, _ = run(
        capsys, "--lang", "de", "price", "--tariff", str(EXAMPLES / "spot_evening_surcharge_cap.json"),
        "--grid-fee", str(EXAMPLES / "grid_fee_modul3_example.json"),
        "--at", "2026-12-15T16:00", "--tz", "Europe/Vienna", "--epex", "10",
    )  # fmt: skip
    assert code == 0
    assert "Netzentgelt: 14,92 ct/kWh" in out
    assert "Angewendete Netzregel: ht" in out
    assert "Preis inkl. 20,00 % USt: 32,064 ct/kWh" in out  # (11.8 + 14.92) * 1.2


def test_series_with_market_csv_table_and_json(capsys, tmp_path):
    market = tmp_path / "market.csv"
    market.write_text(
        "timestamp,cent_kwh\n" + "\n".join(f"2026-12-15T{h:02d}:{m:02d},10" for h in (0, 1) for m in (0, 15, 30, 45)),
        encoding="utf-8",
    )
    common = ["series", "--tariff", str(EXAMPLES / "spot_evening_surcharge_cap.json"), "--from", "2026-12-15T00:00",
              "--to", "2026-12-15T02:00", "--tz", "Europe/Vienna", "--market-csv", str(market)]  # fmt: skip
    code, out, _ = run(capsys, "--lang", "de", *common, "--resolution", "60")
    assert code == 0
    assert "Preisreihe: user_example_spot_plus, 60 min, 2 Werte" in out
    assert "2026-12-15 00:00  14,16 ct/kWh  [exact]" in out
    code, out, _ = run(capsys, *common, "--resolution", "60", "--format", "json")
    assert code == 0
    assert '"resolution_min": 60' in out


def test_series_reports_a_missing_market_price(capsys):
    code, out, err = run(
        capsys, "--lang", "de", "series", "--tariff", str(EXAMPLES / "spot_evening_surcharge_cap.json"),
        "--from", "2026-12-15T00:00", "--to", "2026-12-15T01:00", "--tz", "Europe/Vienna",
    )  # fmt: skip
    assert code == 2
    assert out == ""
    assert "Kein Preis" in err


def test_series_warns_about_unmet_requirements(capsys):
    code, out, err = run(
        capsys, "--lang", "de", "series", "--tariff", str(EXAMPLES / "spot_evening_surcharge_cap.json"),
        "--from", "2026-12-15T00:00", "--to", "2026-12-15T01:00", "--tz", "Europe/Vienna",
        "--market-csv", str(MARKET), "--has", "quarter_hour_meter",
    )  # fmt: skip
    assert code == 0
    assert "Preisreihe" in out
    assert "Smart Meter" in err


def test_series_without_capabilities_does_not_check_requirements(capsys):
    code, _, err = run(
        capsys, "series", "--tariff", str(EXAMPLES / "spot_evening_surcharge_cap.json"),
        "--from", "2026-12-15T00:00", "--to", "2026-12-15T01:00", "--tz", "Europe/Vienna",
        "--market-csv", str(MARKET),
    )  # fmt: skip
    assert code == 0
    assert err == ""
