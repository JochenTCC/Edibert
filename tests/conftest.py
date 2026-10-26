import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from edibert.context import PricingContext
from edibert.gridfee import (
    USER,
    GridFee,
    flat_user_grid_area,
    parse_grid_fee_catalog,
    parse_grid_fee_config,
    resolve_grid_fee,
)
from edibert.tariff import EXPORT, IMPORT, Tariff, parse_tariff

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def make(raw: dict, direction: str = IMPORT, **changes) -> Tariff:
    """Parse a copy of ``raw`` with top-level ``changes`` applied."""
    data = copy.deepcopy(raw)
    data.update(changes)
    return parse_tariff(data, direction)


def at(text: str) -> datetime:
    """Naive local time, e.g. ``at("2026-10-12 23:30")``."""
    return datetime.fromisoformat(text)


def flat_grid_fee(cent: float) -> GridFee:
    """A grid fee with one flat work price: a user grid area without rules, selected by ``area_id``."""
    document = {"tariff_format": 1, "areas": [flat_user_grid_area("user_flat", cent)]}
    return resolve_grid_fee(parse_grid_fee_config({"area_id": "user_flat"}), parse_grid_fee_catalog(document, USER))


@pytest.fixture
def ctx_de() -> PricingContext:
    return PricingContext("Europe/Berlin", "DE", "BY")


@pytest.fixture
def ctx_at() -> PricingContext:
    return PricingContext("Europe/Vienna", "AT", "8")


@pytest.fixture
def ctx_plain() -> PricingContext:
    return PricingContext("Europe/Vienna")


__all__ = ["EXPORT", "IMPORT", "at", "flat_grid_fee", "load_example", "make"]
