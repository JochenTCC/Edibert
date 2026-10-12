from conftest import EXAMPLES

from edbert.cli import main


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
