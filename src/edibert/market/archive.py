"""Day-ahead market prices for arbitrary ranges (simulation, backtesting) with a long-range cache.

Ported from Earnie (``data/live_price_cache.py``, the Energy-Charts part of ``data/data_loader.py``,
``data/backtesting_prices.py``) without pandas. Differences on purpose:

* Every key is a UTC slot start, from the request to the cache file. Earnie's loader groups naive local times,
  so the repeated autumn hour loses one of its two hours; here both keep their own four slots.
* One request and one cache file per UTC calendar month (``<cache_dir>/market_archive/<zone>/YYYY-MM.json``).
  A month is fetched again only while it is incomplete and could still change; a month that was asked
  after its prices were final keeps its gaps (reported, never filled).
* HTTP 429 from Energy-Charts is waited out (``Retry-After`` or a growing pause) and retried.
* Missing slots are reported (``MARKET_RANGE_INCOMPLETE``) and left out; nothing is carried over.

Only Energy-Charts is asked: it is free and covers the past back to 2015 for AT, DE-LU and CH.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from edibert._fields import invalid
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.market.cache import CacheEntry, read_cache, write_cache
from edibert.market.service import RETRY_MINUTES, last_day_ahead_date, window_slots
from edibert.market.sources import (
    SOURCE_ENERGY_CHARTS,
    ZONE_BY_LAND,
    HttpGet,
    Prices,
    RateLimited,
    SourceError,
    fetch_energy_charts,
    http_get,
    redact,
)

log = logging.getLogger(__name__)

ARCHIVE_DIR = "market_archive"
MAX_ATTEMPTS = 6  # requests per month when the source keeps answering HTTP 429
RATE_LIMIT_PAUSE_S = 60.0  # pause after the n-th 429 without Retry-After: n * this
SETTLED_AFTER = timedelta(days=2)  # Day-Ahead prices of a slot are final at most this long after it
_DAY = timedelta(days=1)


@dataclass(frozen=True)
class MarketRange:
    """Prices of one zone for ``[start, end)`` (UTC): cent/kWh per 15-minute slot start (UTC).

    ``missing`` lists the slots without a price (left out of ``prices``); ``notes`` holds the coded warnings
    (``MARKET_RANGE_INCOMPLETE``, ``MARKET_SOURCE_FAILED``, ``MARKET_CACHE_UNREADABLE``).
    """

    zone: str
    start: datetime
    end: datetime
    prices: Prices
    missing: tuple[datetime, ...]
    notes: tuple[EdibertWarning, ...]

    @property
    def complete(self) -> bool:
        return not self.missing


def _month_start(moment: datetime) -> datetime:
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(month: datetime) -> datetime:
    return month.replace(year=month.year + (month.month == 12), month=month.month % 12 + 1)


def _months(start: datetime, end: datetime) -> list[datetime]:
    months, month = [], _month_start(start)
    while month < end:
        months.append(month)
        month = _next_month(month)
    return months


def _utc(moment: datetime, name: str) -> datetime:
    """An aware time in UTC; a naive time has no defined instant here (no house time zone)."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise invalid(name, moment.isoformat())
    value = moment.astimezone(UTC)
    if value.second or value.microsecond or value.minute % 15:
        raise invalid(name, moment.isoformat())
    return value


class MarketArchive:
    """Day-ahead prices of one bidding zone for any range, cached per month under ``cache_dir``."""

    def __init__(
        self,
        zone: str,
        cache_dir: Path,
        *,
        get: HttpGet | None = None,
        timeout: float = 60,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
        retry_minutes: int = RETRY_MINUTES,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        if zone not in ZONE_BY_LAND.values():
            raise invalid("zone", zone)
        self.zone = zone
        self.dir = Path(cache_dir) / ARCHIVE_DIR / zone
        self.get = get or http_get
        self.timeout = timeout
        self.sleep = sleep
        self.clock = clock or (lambda: datetime.now(UTC))
        self.retry = timedelta(minutes=retry_minutes)
        self.max_attempts = max_attempts

    def prices(self, start: datetime, end: datetime) -> MarketRange:
        """Prices for ``[start, end)`` (aware times on 15-minute steps). Nothing at all is ``MARKET_DATA_UNAVAILABLE``."""
        first, last = _utc(start, "start"), _utc(end, "end")
        if last <= first:
            raise invalid("end", end.isoformat())
        notes: list[EdibertWarning] = []
        known: Prices = {}
        for month in _months(first, last):
            known.update(self._month(month, notes))
        slots = window_slots(first, last)
        prices = {slot: known[slot] for slot in slots if slot in known}
        if not prices:
            raise EdibertError(
                ErrorCode.MARKET_DATA_UNAVAILABLE,
                f"No market prices for zone '{self.zone}' from {first.isoformat()} to {last.isoformat()}.",
                zone=self.zone,
            )
        missing = tuple(slot for slot in slots if slot not in prices)
        if missing:
            notes.append(EdibertWarning(
                WarningCode.MARKET_RANGE_INCOMPLETE,
                f"Market prices for '{self.zone}' miss {len(missing)} slots from {missing[0].isoformat()} on.",
                {"zone": self.zone, "missing_from": missing[0].isoformat(), "missing_slots": len(missing)},
            ))  # fmt: skip
        return MarketRange(self.zone, first, last, prices, missing, tuple(notes))

    # -- one month ------------------------------------------------------------------------------

    def _path(self, month: datetime) -> Path:
        return self.dir / f"{month:%Y-%m}.json"

    def _month(self, month: datetime, notes: list[EdibertWarning]) -> Prices:
        end = _next_month(month)
        now = self.clock()
        cached = self._read(month, notes)
        if cached and self._settled(cached, month, end, now):
            return cached.prices
        if month > now + SETTLED_AFTER:  # no Day-Ahead price exists yet
            return cached.prices if cached else {}
        try:
            fresh = self._fetch(month, end)
        except SourceError as exc:
            reason = redact(str(exc))
            log.warning("Market source %s failed for %s %s: %s", SOURCE_ENERGY_CHARTS, self.zone, f"{month:%Y-%m}", reason)
            notes.append(EdibertWarning(
                WarningCode.MARKET_SOURCE_FAILED, f"{SOURCE_ENERGY_CHARTS}: {reason}", {"source": SOURCE_ENERGY_CHARTS, "reason": reason}
            ))  # fmt: skip
            return cached.prices if cached else {}
        merged = {**(cached.prices if cached else {}), **{slot: cent for slot, cent in fresh.items() if month <= slot < end}}
        write_cache(self._path(month), CacheEntry(self.zone, SOURCE_ENERGY_CHARTS, now, now, merged))
        return merged

    def _settled(self, cached: CacheEntry, month: datetime, end: datetime, now: datetime) -> bool:
        """No reason to ask again: complete, asked after the prices were final, or asked a moment ago."""
        if all(slot in cached.prices for slot in window_slots(month, end)):
            return True
        return cached.checked_at >= end + SETTLED_AFTER or now - cached.checked_at < self.retry

    def _read(self, month: datetime, notes: list[EdibertWarning]) -> CacheEntry | None:
        path = self._path(month)
        try:
            entry = read_cache(path)
            if entry is not None and entry.zone != self.zone:
                raise ValueError(f"cache '{path}' belongs to zone '{entry.zone}'")
            return entry
        except ValueError as exc:
            log.warning("%s", exc)
            notes.append(EdibertWarning(WarningCode.MARKET_CACHE_UNREADABLE, str(exc), {"path": str(path)}))
            return None

    def _fetch(self, month: datetime, end: datetime) -> Prices:
        """One Energy-Charts request for the month (one day of margin each side: its dates are local days)."""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fetch_energy_charts(self.zone, month - _DAY, end + _DAY, self.get, self.timeout)
            except RateLimited as exc:
                if attempt == self.max_attempts:
                    raise
                wait = exc.retry_after if exc.retry_after is not None else RATE_LIMIT_PAUSE_S * attempt
                log.warning("Energy-Charts answered 429 for %s %s; waiting %.0f s", self.zone, f"{month:%Y-%m}", wait)
                self.sleep(wait)
        raise AssertionError("unreachable")  # pragma: no cover


def market_range(zone: str, start: datetime, end: datetime, cache_dir: Path) -> MarketRange:
    """Day-ahead prices of ``zone`` for ``[start, end)``, cached under ``cache_dir`` (see :class:`MarketArchive`)."""
    return MarketArchive(zone, cache_dir).prices(start, end)


def known_at(prices: Mapping[datetime, float], moment: datetime, tz: ZoneInfo) -> Prices:
    """The prices a caller could know at ``moment`` (backtesting, as Earnie's ``build_market_data_as_of``).

    Day-Ahead prices of a day are published at 12:00 local time on the day before: up to that hour the
    known prices end with today, from it on with tomorrow. Keys are UTC slot starts, as in ``prices``.
    """
    if moment.tzinfo is None:
        raise invalid("moment", moment.isoformat())
    last_day = last_day_ahead_date(moment.astimezone(tz))
    return {slot: cent for slot, cent in prices.items() if slot.astimezone(tz).date() <= last_day}


__all__ = ["MarketArchive", "MarketRange", "known_at", "market_range"]
