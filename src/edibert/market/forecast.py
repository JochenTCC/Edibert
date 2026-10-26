"""Price forecast beyond the known Day-Ahead prices: the forecaster interface and the free methods.

A forecaster only supplies market prices; the tariff rules are applied to them as for real prices and
the result is marked ``forecast``. The library takes a forecaster *object*: a caller such as Earnie
hands in its own model directly, no key involved. Built in (free):

* ``mirror``: the price of the same time of day on an earlier day, up to 7 days back, as in Earnie
  (``missing_price_strategy: mirror``).
* ``hold``: the last known price stays constant.

Plug-ins from installed packages and their key belong to the product layer
(:mod:`edibert.publish.forecasters`), never to the library.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from edibert._fields import invalid
from edibert.market.sources import SLOT, Prices

MAX_MIRROR_LOOKBACK_DAYS = 7
METHOD_MIRROR = "mirror"
METHOD_HOLD = "hold"
BUILTIN_METHODS = (METHOD_MIRROR, METHOD_HOLD)


class Forecaster(Protocol):
    """``forecast`` returns cent/kWh per 15-minute slot start (UTC) for ``[start, end)``."""

    def forecast(self, known: Mapping[datetime, float], start: datetime, end: datetime) -> Prices: ...


def _slots(start: datetime, end: datetime) -> Iterator[datetime]:
    slot = start
    while slot < end:
        yield slot
        slot += SLOT


class HoldLastForecaster:
    """The last known price stays constant."""

    def forecast(self, known: Mapping[datetime, float], start: datetime, end: datetime) -> Prices:
        earlier = [slot for slot in known if slot < start]
        if not earlier:
            return {}
        price = known[max(earlier)]
        return {slot: price for slot in _slots(start, end)}


class MirrorForecaster:
    """The price of the same local time of day on the nearest earlier day that has one (up to 7 days back)."""

    def __init__(self, tz: ZoneInfo) -> None:
        self.tz = tz

    def forecast(self, known: Mapping[datetime, float], start: datetime, end: datetime) -> Prices:
        result: Prices = {}
        for slot in _slots(start, end):
            wall = slot.astimezone(self.tz).replace(tzinfo=None)
            for days in range(1, MAX_MIRROR_LOOKBACK_DAYS + 1):
                earlier = (wall - timedelta(days=days)).replace(tzinfo=self.tz).astimezone(UTC)
                if earlier in known:
                    result[slot] = known[earlier]
                    break
        return result  # slots without a mirror source are left out, never guessed


def builtin_forecaster(method: str, tz: ZoneInfo) -> Forecaster:
    """The free forecaster for ``mirror`` or ``hold``; any other method is an error."""
    if method == METHOD_MIRROR:
        return MirrorForecaster(tz)
    if method == METHOD_HOLD:
        return HoldLastForecaster()
    raise invalid("forecast.method", method)
