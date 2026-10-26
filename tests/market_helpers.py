"""Builders for fake market-source answers."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from edibert.market.sources import (
    AWATTAR_URLS,
    ENERGY_CHARTS_URL,
    ENTSOE_URL,
    SourceError,
)

ENTSOE_NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def energy_charts_json(start: datetime, hours: int, price=lambda index: 100.0 + index, step_min: int = 60) -> str:
    count = hours * 60 // step_min
    stamps = [int((start + timedelta(minutes=step_min * index)).timestamp()) for index in range(count)]
    return json.dumps({"unix_seconds": stamps, "price": [price(index) for index in range(count)], "license_info": "CC BY 4.0"})


def awattar_json(start: datetime, hours: int, price=lambda index: 90.0 + index) -> str:
    entries = []
    for index in range(hours):
        begin = start + timedelta(hours=index)
        entries.append({
            "start_timestamp": int(begin.timestamp() * 1000),
            "end_timestamp": int((begin + timedelta(hours=1)).timestamp() * 1000),
            "marketprice": price(index),
            "unit": "Eur/MWh",
        })  # fmt: skip
    return json.dumps({"object": "list", "data": entries})


def entsoe_xml(periods: list[tuple[str, str, str, dict[int, float]]]) -> str:
    """``periods``: (start, end, resolution, {position: EUR/MWh}) as ENTSO-E writes them (A03)."""
    series = ""
    for start, end, resolution, points in periods:
        body = "".join(f"<Point><position>{pos}</position><price.amount>{value}</price.amount></Point>" for pos, value in points.items())
        series += (
            f"<TimeSeries><curveType>A03</curveType><Period><timeInterval><start>{start}</start><end>{end}</end></timeInterval>"
            f"<resolution>{resolution}</resolution>{body}</Period></TimeSeries>"
        )
    return f'<Publication_MarketDocument xmlns="{ENTSOE_NS}">{series}</Publication_MarketDocument>'


class FakeWeb:
    """Answers per source; records the requests. A value that is an exception is raised."""

    def __init__(self, **answers):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, params, timeout):
        self.calls.append((url, dict(params)))
        if url == ENTSOE_URL:
            key = "entsoe"
        elif url == ENERGY_CHARTS_URL:
            key = "energy_charts"
        elif url in AWATTAR_URLS.values():
            key = "awattar"
        else:
            raise AssertionError(url)
        answer = self.answers.get(key, SourceError("no answer prepared"))
        if isinstance(answer, Exception):
            raise answer
        return answer(params) if callable(answer) else answer

    def hosts(self) -> list[str]:
        return [urlparse(url).hostname for url, _ in self.calls]
