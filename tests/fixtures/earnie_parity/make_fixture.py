"""Regenerate the Earnie parity fixtures of this folder with Earnie's own pricing engine.

Run from the root of an Earnie checkout that still has its engine (before Earnie P3b), with Earnie's venv:

    python <edibert>/tests/fixtures/earnie_parity/make_fixture.py

Writes next to this file:

* ``tariffs.json`` / ``grid_fees.json``: the tariffs and grid areas the fixtures use, copied from Earnie's
  ``share/config`` catalog, plus one placeholder tariff for the prior-month fallback (no catalog table hits it).
  Both engines price from these two files.
* ``expected_prices.json``: Earnie's committed P3a fixture (``tests/fixtures/edibert_parity``), copied as is
  after checking that the excerpt above reproduces it.
* ``monthly_fallback.json``: Earnie's prices on the edge months of the monthly tables (72-hour windows across a
  month change), the fallback Earnie took per month, or the error when Earnie cannot price the window.

Not a test module; pytest does not collect it. Earnie's code is only read and run, nothing is written there.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EARNIE = Path.cwd()
sys.path.insert(0, str(EARNIE))

from scripts import edibert_parity as harness

harness._use_fixture_config()

from data.tariff_pricing import FALLBACK_PRIOR_YEAR, lookup_monthly_cent

EXPORT_TABLES = (
    "at_oemag_gesetzlicher_marktpreis",
    "at_energie_ag_ober_sterreich_team_sonne_float",
    "at_evn_evn_sonnenstrom_garant_float",
    "at_wien_energie_optima_sonnenstrom_float",
    "de_tibber_tibber_einspeisung_monats_marktwert",
    "at_vkw_pv_flex",
    "monthly_sunny_web_recherche",
)
PLACEHOLDER = {
    "id": "parity_prior_month",
    "label": "Placeholder monthly table (prior-month fallback)",
    "type": "monthly_table",
    "land": "AT",
    "supplier_id": "placeholder",
    "prices_include_vat": False,
    "vat_percent": 0.0,
    "monthly_rates": [
        {"year": 2026, "month": 11, "tariff_cent_kwh": 7.5},
        {"year": 2026, "month": 12, "tariff_cent_kwh": 8.25},
    ],
}
AREAS = ("AT-VBG", "AT-WIEN")
Case = harness.Case
EXPORT_CASES = [Case("export", tid, "monthly_table", "DE" if tid.startswith("de_") else "AT", None) for tid in EXPORT_TABLES]
FALLBACK_CASES = {
    "export_tables_end_2026_09": (
        (datetime(2026, 9, 30), datetime(2026, 10, 3)),
        EXPORT_CASES,
    ),
    "export_tables_end_2026_10": (
        (datetime(2026, 10, 31), datetime(2026, 11, 3)),
        EXPORT_CASES,
    ),
    "vkw_duo_end_2027_03": (
        (datetime(2027, 3, 31), datetime(2027, 4, 3)),
        [Case("import", "at_vkw_strom_duo", "monthly_table", "AT", "AT-VBG"), Case("import", "at_vkw_strom_duo", "monthly_table", "AT", None)],
    ),
    "pv_flex_before_start": (
        (datetime(2025, 6, 29), datetime(2025, 7, 2)),
        [Case("export", "at_vkw_pv_flex", "monthly_table", "AT", None)],
    ),
    "export_tables_2027_10": (
        (datetime(2027, 9, 29), datetime(2027, 10, 2)),
        [Case("export", "at_oemag_gesetzlicher_marktpreis", "monthly_table", "AT", None)],
    ),
    "prior_month_year_boundary": (
        (datetime(2026, 12, 31), datetime(2027, 1, 2)),
        [Case("export", PLACEHOLDER["id"], "monthly_table", "AT", None)],
    ),
}


def _write(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def excerpt() -> tuple[Path, Path]:
    catalog = json.loads((EARNIE / "share" / "config" / "tariffs.json").read_text(encoding="utf-8"))
    grid = json.loads((EARNIE / "share" / "config" / "grid_fees.json").read_text(encoding="utf-8"))
    parity = {case.tariff_id for case in harness.FIXTURE_CASES}
    wanted = parity | set(EXPORT_TABLES) | {"at_vkw_strom_duo"}
    tariffs = {
        "tariff_format": catalog["tariff_format"],
        "catalog_as_of": catalog["catalog_as_of"],
        "import_tariffs": [t for t in catalog["import_tariffs"] if t["id"] in wanted],
        "export_tariffs": [t for t in catalog["export_tariffs"] if t["id"] in wanted] + [PLACEHOLDER],
    }
    areas = [a for a in grid["areas"] if a["id"] in AREAS]
    grid_fees = {
        "tariff_format": grid["tariff_format"],
        "rule_sets": {name: rules for name, rules in grid["rule_sets"].items() if any(a["rule_set"] == name for a in areas)},
        "areas": areas,
    }
    _write(HERE / "tariffs.json", tariffs)
    _write(HERE / "grid_fees.json", grid_fees)
    return HERE / "tariffs.json", HERE / "grid_fees.json"


def fallbacks(case: Case, slots: list[datetime], tariffs_path: Path) -> list[dict]:
    doc = json.loads(tariffs_path.read_text(encoding="utf-8"))
    tariff = next(t for t in doc[f"{case.direction}_tariffs"] if t["id"] == case.tariff_id)
    lookup = {(row["year"], row["month"]): row["tariff_cent_kwh"] for row in tariff["monthly_rates"]}
    result = []
    for year, month in sorted({(slot.year, slot.month) for slot in slots}):
        try:
            _cent, rule = lookup_monthly_cent(lookup, year, month)
        except ValueError:
            continue
        if rule:
            used = (year - 1, month) if rule == FALLBACK_PRIOR_YEAR else ((year - 1, 12) if month == 1 else (year, month - 1))
            result.append({"month": f"{year}-{month:02d}", "used_month": f"{used[0]}-{used[1]:02d}", "rule": rule})
    return result


def fallback_fixture(tariffs_path: Path, grid_path: Path) -> dict:
    windows = []
    for name, ((first, last), cases) in FALLBACK_CASES.items():
        slots = harness._window_slots(first, last)
        epex = harness._fixture_epex(len(slots))
        expected = []
        for case in cases:
            entry = {"direction": case.direction, "tariff_id": case.tariff_id, "land": case.land, "area_id": case.area_id}
            try:
                cents, grid = harness.earnie_prices(case, slots, epex, str(tariffs_path), str(grid_path))
                entry |= {"cent": cents, "grid_net_cent": grid, "fallbacks": fallbacks(case, slots, tariffs_path)}
            except ValueError as exc:
                entry |= {"error": str(exc)}
            expected.append(entry)
        windows.append({"name": name, "slots": [s.isoformat() for s in slots], "epex_cent": epex, "expected": expected})
    return {
        "comment": (
            "Earnie's prices (engine before Earnie P3b) on the edge months of monthly tables; generated by "
            "make_fixture.py from tariffs.json / grid_fees.json of this folder, netznutzung as Earnie writes it."
        ),
        "timezone": harness.TIMEZONE,
        "windows": windows,
    }


def main() -> None:
    tariffs_path, grid_path = excerpt()
    committed = EARNIE / "tests" / "fixtures" / "edibert_parity" / "expected_prices.json"
    if harness.build_fixture(str(tariffs_path), str(grid_path)) != json.loads(committed.read_text(encoding="utf-8")):
        raise SystemExit("The excerpt does not reproduce Earnie's committed fixture; regenerate it in Earnie first.")
    shutil.copyfile(committed, HERE / "expected_prices.json")
    _write(HERE / "monthly_fallback.json", fallback_fixture(tariffs_path, grid_path))
    print(f"written to {HERE}")


if __name__ == "__main__":
    main()
