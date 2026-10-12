import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from edbert.context import PricingContext
from edbert.tariff import EXPORT, IMPORT, Tariff, parse_tariff

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


@pytest.fixture
def ctx_de() -> PricingContext:
    return PricingContext("Europe/Berlin", "DE", "BY")


@pytest.fixture
def ctx_at() -> PricingContext:
    return PricingContext("Europe/Vienna", "AT", "8")


@pytest.fixture
def ctx_plain() -> PricingContext:
    return PricingContext("Europe/Vienna")


__all__ = ["EXPORT", "IMPORT", "at", "load_example", "make"]
