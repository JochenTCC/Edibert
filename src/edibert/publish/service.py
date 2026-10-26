"""Publishing cycle: market data -> tariff price series -> retained MQTT topics."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import time as day_time
from pathlib import Path
from zoneinfo import ZoneInfo

from edibert.editor.house import HouseSettings, load_house
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.market.forecast import Forecaster
from edibert.market.service import MarketData, MarketService, window_slots
from edibert.market.sources import HttpGet, http_get, zone_for_land
from edibert.publish import payloads
from edibert.publish.config import (
    CONFIG_NAME,
    MqttSettings,
    PublishConfig,
    TariffRef,
    load_publish_config,
)
from edibert.publish.forecasters import (
    FORECAST_KEY_ENV,
    build_forecaster,
    load_forecaster,
)
from edibert.publish.mqtt import MqttLink, connect
from edibert.series import PricePoint, tariff_price_series
from edibert.store import TariffSet, load_tariffs
from edibert.tariff import IMPORT, Tariff

log = logging.getLogger(__name__)

_QUARTER = timedelta(minutes=15)
_WAKE_DELAY_S = 2
_SLOTS_PER_HOUR = 4
ENTSOE_TOKEN_ENV = "ENTSOE_API_TOKEN"


@dataclass
class CycleReport:
    published: list[str] = field(default_factory=list)
    offline: list[tuple[str, EdibertError]] = field(default_factory=list)
    notes: list[EdibertWarning] = field(default_factory=list)


def _midnight(day, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, day_time(0), tzinfo=tz)


class Publisher:
    def __init__(
        self,
        config: PublishConfig,
        tariffs: TariffSet,
        house: HouseSettings,
        link: MqttLink,
        market: MarketService,
        forecaster: Forecaster | None = None,
    ) -> None:
        self.config = config
        self.house = house
        self.link = link
        self.market = market
        self.forecaster = forecaster
        self.tz = ZoneInfo(house.timezone)
        self.ctx = house.context()
        self.items: list[tuple[TariffRef, Tariff]] = [(ref, tariffs.get(ref.direction, ref.id)) for ref in config.tariffs]

    # -- topics ---------------------------------------------------------------------------------

    def announce(self) -> None:
        """Home Assistant discovery for every configured tariff, and the bridge status."""
        base, prefix = self.config.mqtt.base_topic, self.config.mqtt.discovery_prefix
        for ref, tariff in self.items:
            body = payloads.discovery_payload(base=base, direction=ref.direction, tariff_id=ref.id, label=tariff.label)
            self.link.publish(payloads.discovery_topic(prefix, ref.direction, ref.id), payloads.encode(body))
        self.link.publish(payloads.bridge_status_topic(base), payloads.ONLINE)

    def _put(self, ref: TariffRef, leaf: str, payload: str) -> None:
        self.link.publish(payloads.topic(self.config.mqtt.base_topic, ref.direction, ref.id, leaf), payload)

    # -- one cycle ------------------------------------------------------------------------------

    def run_cycle(self, now: datetime) -> CycleReport:
        """Publish the current state of every tariff. A tariff without data goes ``offline``, never to a guess."""
        report = CycleReport()
        local = now.astimezone(self.tz)
        data = self._market_data(local, report)
        for ref, tariff in self.items:
            try:
                self._publish_tariff(ref, tariff, local, data, report)
            except EdibertError as err:
                log.warning("Tariff %s is offline: %s", ref.id, err)
                report.offline.append((ref.id, err))
                self._put(ref, "availability", payloads.OFFLINE)
        return report

    def _market_data(self, local: datetime, report: CycleReport) -> MarketData | None:
        if not any(tariff.uses_market_price for _, tariff in self.items):
            return None
        try:
            data = self.market.load(self.tz, local)
        except EdibertError as err:
            log.warning("No market data: %s", err)
            report.offline.append(("market", err))
            return None
        report.notes.extend(data.notes)
        return data

    def _publish_tariff(self, ref: TariffRef, tariff: Tariff, local: datetime, data: MarketData | None, report: CycleReport) -> None:
        points, tomorrow_valid = self._points(tariff, local, data)
        forecast = self._forecast(tariff, data, points, report)
        body = payloads.attributes(
            tariff_id=ref.id, label=tariff.label, direction=ref.direction, resolution_min=self.config.resolution_min,
            points=points, forecast=forecast, now=local, tomorrow_valid=tomorrow_valid, market=data,
            forecast_method=self._forecast_label() if forecast else None,
        )  # fmt: skip
        self._put(ref, "state", payloads.state_payload(payloads.current_point(points, local)))
        self._put(ref, "attributes", payloads.encode(body))
        self._put(ref, "availability", payloads.ONLINE)
        report.published.append(ref.id)
        log.info("Published %s: %s ct/kWh", ref.id, body["current_cent_kwh"])

    def _forecast_label(self) -> str | None:
        settings = self.config.forecast
        return (settings.name or settings.method) if settings else None

    def _slots_known(self, data: MarketData, start: datetime, end: datetime) -> bool:
        return all(slot in data.prices for slot in window_slots(start, end))

    def _points(self, tariff: Tariff, local: datetime, data: MarketData | None) -> tuple[tuple[PricePoint, ...], bool]:
        day0 = _midnight(local.date(), self.tz)
        day1 = _midnight(local.date() + timedelta(days=1), self.tz)
        day2 = _midnight(local.date() + timedelta(days=2), self.tz)
        end, tomorrow_valid = day2, True
        if tariff.uses_market_price:
            if data is None or not self._slots_known(data, day0, day1):
                raise EdibertError(ErrorCode.MARKET_DATA_UNAVAILABLE, "Today's market prices are missing.", zone=data.zone if data else "")
            tomorrow_valid = self._slots_known(data, day1, day2)
            end = day2 if tomorrow_valid else day1
        series = tariff_price_series(
            tariff, self.ctx, day0, end,
            resolution_min=self.config.resolution_min,
            market=data.prices if data else None,
            grid_fee=self.house.grid_fee() if tariff.direction == IMPORT else None,
            capabilities=set(self.house.capabilities),
        )  # fmt: skip
        return series.points, tomorrow_valid

    def _forecast(self, tariff: Tariff, data: MarketData | None, points: tuple[PricePoint, ...], report: CycleReport) -> tuple[PricePoint, ...]:
        settings = self.config.forecast
        if self.forecaster is None or settings is None or data is None or not tariff.uses_market_price or not points:
            return ()
        start = points[-1].end
        label = settings.name or settings.method
        try:
            extra = self.forecaster.forecast(data.prices, start.astimezone(UTC), (start + timedelta(hours=settings.hours)).astimezone(UTC))
            end = _covered_end(extra, start.astimezone(UTC), start.astimezone(UTC) + timedelta(hours=settings.hours))
            if end <= start.astimezone(UTC):
                return ()
            series = tariff_price_series(
                tariff, self.ctx, start, end,
                resolution_min=self.config.resolution_min,
                market={**data.prices, **extra},
                forecast_from=start,
                grid_fee=self.house.grid_fee() if tariff.direction == IMPORT else None,
                capabilities=set(self.house.capabilities),
            )  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - a plug-in must never take the exact prices down with it
            log.warning("Forecaster '%s' failed: %s", label, exc)
            report.notes.append(EdibertWarning(WarningCode.FORECAST_FAILED, f"{label}: {exc}", {"name": label, "reason": str(exc)}))
            return ()
        return series.points

    # -- loop -----------------------------------------------------------------------------------

    def run_forever(self, clock: Callable[[], datetime] | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        """Publish at start and at every quarter-hour. Ctrl+C says ``offline`` and returns."""
        now_fn = clock or (lambda: datetime.now(UTC))
        self.announce()
        try:
            while True:
                self.run_cycle(now_fn())
                sleep(seconds_to_next_quarter(now_fn()))
        except KeyboardInterrupt:
            log.info("Stopping.")
        finally:
            self.link.close()


def _covered_end(prices: Mapping[datetime, float], start: datetime, end: datetime) -> datetime:
    """End of the gap-free part of ``[start, end)``, cut to whole hours so every tariff can use it."""
    count, slot = 0, start
    while slot < end and slot in prices:
        count += 1
        slot += _QUARTER
    return start + _QUARTER * (count - count % _SLOTS_PER_HOUR)


def seconds_to_next_quarter(now: datetime) -> float:
    """Seconds until the next quarter-hour boundary (plus a small delay)."""
    base = now.astimezone(UTC).replace(second=0, microsecond=0, minute=now.astimezone(UTC).minute // 15 * 15)
    return max(1.0, (base + _QUARTER - now).total_seconds() + _WAKE_DELAY_S)


def build_publisher(
    data_dir: Path,
    *,
    catalog: Path | None = None,
    config_path: Path | None = None,
    link_factory: Callable[[MqttSettings], MqttLink] = connect,
    get: HttpGet = http_get,
    env: Mapping[str, str] | None = None,
    forecaster_loader: Callable[[str, str], Forecaster] = load_forecaster,
) -> Publisher:
    """Wire a publisher from the files in ``data_dir``. The ENTSO-E token is read from ``ENTSOE_API_TOKEN``, the forecast key from ``EDIBERT_FORECAST_KEY``."""
    environment = os.environ if env is None else env
    config = load_publish_config(config_path or data_dir / CONFIG_NAME)
    house = load_house(data_dir / "house.json")
    tariffs = load_tariffs(catalog, data_dir / "user_tariffs.json")
    market = MarketService(zone_for_land(house.land), data_dir, entsoe_token=environment.get(ENTSOE_TOKEN_ENV, ""), get=get)
    settings = config.forecast
    key = environment.get(FORECAST_KEY_ENV, "")
    forecaster = build_forecaster(settings.method, settings.name, key, ZoneInfo(house.timezone), forecaster_loader) if settings else None
    return Publisher(config, tariffs, house, link_factory(config.mqtt), market, forecaster)
