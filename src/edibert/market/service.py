"""Day-ahead price chain: cache -> ENTSO-E (token) -> Energy-Charts -> aWATTar.

Same order and same freshness idea as Earnie: the Day-Ahead auction is published around 12:00 CET, so
from 12:00 on tomorrow's prices are expected. A cache is current when it covers every slot of today
and, after the publish hour, of tomorrow. Nothing is invented; if no source delivers everything, the
best partial answer is used and the missing part is reported.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.market.cache import CacheEntry, cache_path, read_cache, write_cache
from edibert.market.sources import (
    AWATTAR_URLS,
    ENTSOE_EIC,
    SLOT,
    SOURCE_AWATTAR,
    SOURCE_ENERGY_CHARTS,
    SOURCE_ENTSOE,
    HttpGet,
    Prices,
    SourceError,
    fetch_awattar,
    fetch_energy_charts,
    fetch_entsoe,
    http_get,
    redact,
)

log = logging.getLogger(__name__)

DAY_AHEAD_PUBLISH_HOUR = 12
HISTORY_DAYS = 7  # kept in the cache for the mirror forecast
RETRY_MINUTES = 10
SOURCE_CACHE = "cache"


@dataclass(frozen=True)
class MarketData:
    zone: str
    prices: Prices  # cent/kWh per 15-minute slot start (UTC)
    source: str
    fetched_at: datetime
    complete: bool  # covers every slot that is expected right now
    notes: tuple[EdibertWarning, ...] = ()


def last_day_ahead_date(now_local: datetime) -> date:
    """The latest day whose Day-Ahead prices exist: tomorrow from the publish hour on, else today."""
    return now_local.date() + timedelta(days=1 if now_local.hour >= DAY_AHEAD_PUBLISH_HOUR else 0)


def expected_window(now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Start of today and end of the last Day-Ahead day, both local and aware."""
    local = now.astimezone(tz)
    start = datetime.combine(local.date(), time(0), tzinfo=tz)
    end = datetime.combine(last_day_ahead_date(local) + timedelta(days=1), time(0), tzinfo=tz)
    return start, end


def window_slots(start: datetime, end: datetime) -> list[datetime]:
    """The 15-minute slot starts (UTC) of ``[start, end)``; a DST day has 92 or 100 of them."""
    first, last = start.astimezone(UTC), end.astimezone(UTC)
    return [first + SLOT * index for index in range(int((last - first) / SLOT))]


def _missing(prices: Prices, slots: list[datetime]) -> list[datetime]:
    return [slot for slot in slots if slot not in prices]


class MarketService:
    """Gets day-ahead prices for one bidding zone and keeps the cache."""

    def __init__(
        self,
        zone: str,
        data_dir: Path,
        *,
        entsoe_token: str = "",
        get: HttpGet = http_get,
        timeout: float = 30,
        retry_minutes: int = RETRY_MINUTES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.zone = zone
        self.path = cache_path(data_dir, zone)
        self.token = entsoe_token.strip()
        self.get = get
        self.timeout = timeout
        self.retry = timedelta(minutes=retry_minutes)
        self.clock = clock or (lambda: datetime.now(UTC))

    def load(self, tz: ZoneInfo, now: datetime | None = None) -> MarketData:
        """Prices covering today and, once published, tomorrow. See the module description."""
        moment = now or self.clock()
        start, end = expected_window(moment, tz)
        slots = window_slots(start, end)
        notes: list[EdibertWarning] = []
        cached = self._read(notes)
        if cached and not _missing(cached.prices, slots):
            return MarketData(self.zone, cached.prices, cached.source, cached.fetched_at, True, tuple(notes))
        if cached and moment - cached.checked_at < self.retry:
            return self._partial(cached.prices, cached.source, cached.fetched_at, slots, tz, notes)
        candidates = self._fetch_all(start, end, slots, notes)
        for source, prices in candidates:
            if not _missing(prices, slots):
                merged = self._save(source, prices, cached, moment, moment, start)
                return MarketData(self.zone, merged, source, moment, True, tuple(notes))
        pool = [(source, prices, moment) for source, prices in candidates]
        if cached:
            pool.append((cached.source, cached.prices, cached.fetched_at))
        if not pool:
            raise EdibertError(ErrorCode.MARKET_DATA_UNAVAILABLE, f"No market prices for zone '{self.zone}'.", zone=self.zone)
        best_source, best, fetched = max(pool, key=lambda item: len(slots) - len(_missing(item[1], slots)))
        merged = self._save(best_source, best, cached, fetched, moment, start)
        return self._partial(merged, best_source, fetched, slots, tz, notes)

    def _read(self, notes: list[EdibertWarning]) -> CacheEntry | None:
        try:
            return read_cache(self.path)
        except ValueError as exc:
            log.warning("%s", exc)
            notes.append(EdibertWarning(WarningCode.MARKET_CACHE_UNREADABLE, str(exc), {"path": str(self.path)}))
            return None

    def _save(self, source: str, prices: Prices, old: CacheEntry | None, fetched: datetime, checked: datetime, today: datetime) -> Prices:
        """Write the prices plus the cached history of the last days; returns what was written."""
        floor = today.astimezone(UTC) - timedelta(days=HISTORY_DAYS)
        merged = {slot: cent for slot, cent in {**(old.prices if old else {}), **prices}.items() if slot >= floor}
        write_cache(self.path, CacheEntry(self.zone, source, fetched, checked, merged))
        return merged

    def _partial(self, prices: Prices, source: str, fetched: datetime, slots: list[datetime], tz: ZoneInfo, notes: list[EdibertWarning]) -> MarketData:
        first_missing = _missing(prices, slots)[0].astimezone(tz).isoformat()
        notes.append(EdibertWarning(
            WarningCode.MARKET_DATA_INCOMPLETE,
            f"Market data for '{self.zone}' ends before {first_missing}.",
            {"zone": self.zone, "missing_from": first_missing},
        ))  # fmt: skip
        return MarketData(self.zone, prices, source, fetched, False, tuple(notes))

    def _fetch_all(self, start: datetime, end: datetime, slots: list[datetime], notes: list[EdibertWarning]) -> list[tuple[str, Prices]]:
        """Ask the sources in order and stop at the first one that covers everything."""
        attempts: list[tuple[str, Callable[[], Prices]]] = []
        if self.token and self.zone in ENTSOE_EIC:
            attempts.append((SOURCE_ENTSOE, lambda: fetch_entsoe(self.zone, start, end, self.token, self.get, self.timeout)))
        attempts.append((SOURCE_ENERGY_CHARTS, lambda: fetch_energy_charts(self.zone, start, end, self.get, self.timeout)))
        if self.zone in AWATTAR_URLS:
            attempts.append((SOURCE_AWATTAR, lambda: fetch_awattar(self.zone, start, end, self.get, self.timeout)))
        results: list[tuple[str, Prices]] = []
        for source, fetch in attempts:
            try:
                prices = fetch()
            except SourceError as exc:
                reason = redact(str(exc))
                log.warning("Market source %s failed for %s: %s", source, self.zone, reason)
                notes.append(EdibertWarning(WarningCode.MARKET_SOURCE_FAILED, f"{source}: {reason}", {"source": source, "reason": reason}))
                continue
            results.append((source, prices))
            if not _missing(prices, slots):
                break
        return results
