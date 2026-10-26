"""Day-ahead price sources: ENTSO-E (token), Energy-Charts (free), aWATTar (free).

Every parser returns ``{slot_start_utc: cent_per_kwh}`` with one entry per 15-minute slot
(coarser source steps are expanded). HTTP goes through an injectable ``HttpGet`` so tests need no network.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from edibert.errors import EdibertError, ErrorCode

SLOT = timedelta(minutes=15)
SOURCE_ENTSOE = "entsoe"
SOURCE_ENERGY_CHARTS = "energy-charts"
SOURCE_AWATTAR = "awattar"

ENTSOE_URL = "https://web-api.tp.entsoe.eu/api"
ENERGY_CHARTS_URL = "https://api.energy-charts.info/price"
# aWATTar has no Swiss service, so Switzerland has no third source.
AWATTAR_URLS = {"AT": "https://api.awattar.at/v1/marketdata", "DE-LU": "https://api.awattar.de/v1/marketdata"}
USER_AGENT = "Edibert (tariff price service)"

# land -> bidding zone (the zone names of Energy-Charts)
ZONE_BY_LAND = {"AT": "AT", "DE": "DE-LU", "CH": "CH"}
ENTSOE_EIC = {"AT": "10YAT-APG------L", "DE-LU": "10Y1001A1001A82H", "CH": "10YCH-SWISSGRIDZ"}

_ENTSOE_NS = {"p": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
_ENTSOE_STEP_MIN = {"PT15M": 15, "PT60M": 60}
_ENTSOE_STAMP = "%Y-%m-%dT%H:%MZ"

HttpGet = Callable[[str, Mapping[str, str], float], str]
Prices = dict[datetime, float]


class SourceError(Exception):
    """A source answered with something unusable. The chain notes it and tries the next source."""


def http_get(url: str, params: Mapping[str, str], timeout: float) -> str:
    """GET ``url`` with ``params`` and return the body text."""
    full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/xml"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise SourceError(redact(str(exc))) from exc


def redact(text: str) -> str:
    """Remove a security token from a message that may contain a request URL."""
    return re.sub(r"securityToken=[^&\s'\"]*", "securityToken=REDACTED", text)


def zone_for_land(land: str) -> str:
    zone = ZONE_BY_LAND.get(land)
    if zone is None:
        raise EdibertError(ErrorCode.MARKET_ZONE_UNKNOWN, f"No market zone for country '{land}'.", land=land)
    return zone


def _expand(table: Prices, start: datetime, step: timedelta, cent: float) -> None:
    for offset in range(int(step / SLOT)):
        table[start + SLOT * offset] = cent


def _step_for(timestamps: list[datetime], index: int, last_step: timedelta) -> timedelta:
    if index + 1 < len(timestamps):
        step = timestamps[index + 1] - timestamps[index]
        if step > timedelta(0):
            return step
    return last_step


def parse_energy_charts(text: str) -> Prices:
    """Energy-Charts ``/price``: ``unix_seconds`` and ``price`` (EUR/MWh); hourly or quarter-hourly."""
    try:
        data = json.loads(text)
        seconds, values = data["unix_seconds"], data["price"]
        if not seconds or len(seconds) != len(values):
            raise ValueError("no price data")
        stamps = [datetime.fromtimestamp(int(value), UTC) for value in seconds]
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceError(f"unexpected Energy-Charts answer: {exc}") from exc
    table: Prices = {}
    step = SLOT
    for index, stamp in enumerate(stamps):
        step = _step_for(stamps, index, step)
        if values[index] is not None:  # the API uses null for slots without a price
            _expand(table, stamp, step, float(values[index]) / 10)
    if not table:
        raise SourceError("Energy-Charts returned no price")
    return table


def parse_awattar(text: str) -> Prices:
    """aWATTar ``/marketdata``: ``data`` entries with millisecond timestamps and EUR/MWh."""
    try:
        entries = json.loads(text)["data"]
        table: Prices = {}
        for entry in entries:
            start = datetime.fromtimestamp(int(entry["start_timestamp"]) / 1000, UTC)
            end = datetime.fromtimestamp(int(entry["end_timestamp"]) / 1000, UTC)
            _expand(table, start, max(end - start, SLOT), float(entry["marketprice"]) / 10)
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceError(f"unexpected aWATTar answer: {exc}") from exc
    if not table:
        raise SourceError("aWATTar returned no price")
    return table


def _entsoe_text(node: ET.Element, path: str) -> str:
    child = node.find(path, _ENTSOE_NS)
    return (child.text or "").strip() if child is not None else ""


def _entsoe_period(period: ET.Element, table: Prices) -> None:
    resolution = _entsoe_text(period, "p:resolution")
    step_min = _ENTSOE_STEP_MIN.get(resolution)
    if step_min is None:
        raise SourceError(f"unsupported ENTSO-E resolution '{resolution}'")
    start = datetime.strptime(_entsoe_text(period, "p:timeInterval/p:start"), _ENTSOE_STAMP).replace(tzinfo=UTC)
    end = datetime.strptime(_entsoe_text(period, "p:timeInterval/p:end"), _ENTSOE_STAMP).replace(tzinfo=UTC)
    count = int((end - start) / timedelta(minutes=step_min))
    given = {int(_entsoe_text(point, "p:position")): float(_entsoe_text(point, "p:price.amount")) for point in period.findall("p:Point", _ENTSOE_NS)}
    # Curve type A03 omits a point when the price equals the previous one: carry it forward.
    current: float | None = None
    for position in range(1, count + 1):
        current = given.get(position, current)
        if current is None:
            raise SourceError("ENTSO-E period starts without a price")
        _expand(table, start + timedelta(minutes=step_min * (position - 1)), timedelta(minutes=step_min), current / 10)


def parse_entsoe(text: str) -> Prices:
    """ENTSO-E A44 ``Publication_MarketDocument``; finer resolutions win over coarser ones."""
    try:
        root = ET.fromstring(text)
        if "Acknowledgement" in root.tag:
            reason = next((node.text for node in root.iter() if node.tag.endswith("}text") and node.text), root.tag)
            raise SourceError(f"ENTSO-E: {reason}")
        periods = [period for series in root.findall("p:TimeSeries", _ENTSOE_NS) for period in series.findall("p:Period", _ENTSOE_NS)]
        table: Prices = {}
        for period in sorted(periods, key=lambda item: _entsoe_text(item, "p:resolution") == "PT15M"):
            _entsoe_period(period, table)
    except (ET.ParseError, ValueError) as exc:
        raise SourceError(f"unexpected ENTSO-E answer: {exc}") from exc
    if not table:
        raise SourceError("ENTSO-E returned no price")
    return table


def _utc_stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%d%H%M")


def fetch_entsoe(zone: str, start: datetime, end: datetime, token: str, get: HttpGet, timeout: float) -> Prices:
    eic = ENTSOE_EIC[zone]
    params = {
        "documentType": "A44", "contract_MarketAgreement.type": "A01", "in_Domain": eic, "out_Domain": eic,
        "periodStart": _utc_stamp(start), "periodEnd": _utc_stamp(end), "securityToken": token,
    }  # fmt: skip
    return parse_entsoe(get(ENTSOE_URL, params, timeout))


def fetch_energy_charts(zone: str, start: datetime, end: datetime, get: HttpGet, timeout: float) -> Prices:
    params = {"bzn": zone, "start": start.astimezone(UTC).strftime("%Y-%m-%d"), "end": end.astimezone(UTC).strftime("%Y-%m-%d")}
    return parse_energy_charts(get(ENERGY_CHARTS_URL, params, timeout))


def fetch_awattar(zone: str, start: datetime, end: datetime, get: HttpGet, timeout: float) -> Prices:
    params = {"start": str(int(start.timestamp() * 1000)), "end": str(int(end.timestamp() * 1000))}
    return parse_awattar(get(AWATTAR_URLS[zone], params, timeout))


def source_label(source: str) -> dict[str, Any]:
    """Name and licence note of a source, for attributes and docs."""
    return {
        SOURCE_ENTSOE: {"name": "ENTSO-E Transparency Platform", "license": "ENTSO-E terms of use"},
        SOURCE_ENERGY_CHARTS: {"name": "Energy-Charts.info (Fraunhofer ISE)", "license": "CC BY 4.0"},
        SOURCE_AWATTAR: {"name": "aWATTar", "license": "aWATTar terms of use"},
    }.get(source, {"name": source, "license": ""})
