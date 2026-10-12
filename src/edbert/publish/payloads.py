"""MQTT topics and JSON payloads. Prices are published in EUR/kWh (Nordpool/evcc style)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from edbert.market.service import MarketData
from edbert.market.sources import source_label
from edbert.series import PricePoint

UNIT = "EUR/kWh"
ONLINE = "online"
OFFLINE = "offline"
_DECIMALS = 5


def eur(cent: float) -> float:
    return round(cent / 100, _DECIMALS)


def tariff_key(direction: str, tariff_id: str) -> str:
    return f"{direction}/{tariff_id}"


def topic(base: str, direction: str, tariff_id: str, leaf: str) -> str:
    return f"{base}/{tariff_key(direction, tariff_id)}/{leaf}"


def bridge_status_topic(base: str) -> str:
    return f"{base}/status"


def discovery_topic(prefix: str, direction: str, tariff_id: str) -> str:
    return f"{prefix}/sensor/edbert_{direction}_{tariff_id}/config"


def interval(point: PricePoint) -> dict[str, Any]:
    return {"start": point.start.isoformat(), "end": point.end.isoformat(), "value": eur(point.cent)}


def _on(points: tuple[PricePoint, ...], day: date) -> list[PricePoint]:
    return [point for point in points if point.start.date() == day]


def market_block(data: MarketData | None) -> dict[str, Any] | None:
    if data is None:
        return None
    label = source_label(data.source)
    return {
        "zone": data.zone,
        "source": data.source,
        "fetched_at": data.fetched_at.isoformat(),
        "complete": data.complete,
        "attribution": f"{label['name']} {label['license']}".strip(),
    }


def current_point(points: tuple[PricePoint, ...], now: datetime) -> PricePoint | None:
    return next((point for point in points if point.start <= now < point.end), None)


def components(point: PricePoint | None) -> dict[str, float] | None:
    if point is None:
        return None
    return {"supplier": eur(point.supplier_cent), "grid": eur(point.grid_cent), "vat": eur(point.vat_cent)}


def attributes(
    *,
    tariff_id: str,
    label: str,
    direction: str,
    resolution_min: int,
    points: tuple[PricePoint, ...],
    forecast: tuple[PricePoint, ...],
    forecast_method: str | None,
    now: datetime,
    tomorrow_valid: bool,
    market: MarketData | None,
) -> dict[str, Any]:
    """Sensor attributes: today/tomorrow lists, the current components and day statistics."""
    today = _on(points, now.date())
    tomorrow = _on(points, now.date() + timedelta(days=1))
    current = current_point(points, now)
    upcoming = next((point for point in points if point.start >= (current.end if current else now)), None)
    values = [eur(point.cent) for point in today]
    return {
        "tariff_id": tariff_id,
        "label": label,
        "direction": direction,
        "unit": UNIT,
        "resolution_min": resolution_min,
        "current_cent_kwh": current.cent if current else None,
        "components": components(current),
        "quality": current.quality if current else None,
        "next": eur(upcoming.cent) if upcoming else None,
        "average_today": round(sum(values) / len(values), _DECIMALS) if values else None,
        "min_today": min(values) if values else None,
        "max_today": max(values) if values else None,
        "raw_today": [interval(point) for point in today],
        "raw_tomorrow": [interval(point) for point in tomorrow] if tomorrow_valid else [],
        "tomorrow_valid": tomorrow_valid,
        "forecast": [interval(point) for point in forecast],
        "forecast_method": forecast_method,
        "market": market_block(market),
        "updated": now.isoformat(),
    }


def state_payload(point: PricePoint | None) -> str:
    return "" if point is None else str(eur(point.cent))


def discovery_payload(*, base: str, direction: str, tariff_id: str, label: str) -> dict[str, Any]:
    """Home Assistant MQTT discovery for one price sensor."""
    return {
        "name": label,
        "unique_id": f"edbert_{direction}_{tariff_id}",
        "state_topic": topic(base, direction, tariff_id, "state"),
        "json_attributes_topic": topic(base, direction, tariff_id, "attributes"),
        "availability": [
            {"topic": bridge_status_topic(base)},
            {"topic": topic(base, direction, tariff_id, "availability")},
        ],
        "availability_mode": "all",
        "unit_of_measurement": UNIT,
        "suggested_display_precision": 4,
        "icon": "mdi:flash",
        "device": {"identifiers": ["edbert"], "name": "Edbert", "manufacturer": "Edbert"},
    }


def encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
