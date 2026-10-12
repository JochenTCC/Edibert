"""Optional price forecast beyond the known Day-Ahead prices.

A forecaster only supplies market prices; the tariff rules are applied to them as for real prices and
the result is marked ``forecast``. Three methods, chosen in ``publish.json``:

* ``mirror`` (built in, free): the price of the same time of day on an earlier day, up to 7 days back,
  as in Earnie (``missing_price_strategy: mirror``).
* ``hold`` (built in, free): the last known price stays constant.
* ``plugin``: a model from an installed package (entry-point group ``edbert.forecasters``). The free
  edition ships none. It needs a key: Edbert insists that one is given and hands it to the factory
  (``factory(key=...)``); checking it is the job of the plug-in, so the free edition holds no validation.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
from typing import Protocol
from zoneinfo import ZoneInfo

from edbert.errors import EdbertError, ErrorCode
from edbert.market.sources import SLOT, Prices

ENTRY_POINT_GROUP = "edbert.forecasters"
FORECAST_KEY_ENV = "EDBERT_FORECAST_KEY"
MAX_MIRROR_LOOKBACK_DAYS = 7
METHOD_MIRROR = "mirror"
METHOD_HOLD = "hold"
METHOD_PLUGIN = "plugin"
METHODS = (METHOD_MIRROR, METHOD_HOLD, METHOD_PLUGIN)


class Forecaster(Protocol):
    """``forecast`` returns cent/kWh per 15-minute slot start (UTC) for ``[start, end)``."""

    def forecast(self, known: Mapping[datetime, float], start: datetime, end: datetime) -> Prices: ...


def available_forecasters() -> dict[str, str]:
    """Registered forecasters by name."""
    return {point.name: point.value for point in entry_points(group=ENTRY_POINT_GROUP)}


def load_forecaster(name: str, key: str) -> Forecaster:
    """The forecaster registered as ``name``; a missing plug-in or key is an error, never a silent skip."""
    for point in entry_points(group=ENTRY_POINT_GROUP):
        if point.name == name:
            if not key.strip():
                raise EdbertError(ErrorCode.FORECAST_KEY_MISSING, "A key is needed to use the forecast.", env=FORECAST_KEY_ENV)
            return point.load()(key=key.strip())
    raise EdbertError(ErrorCode.FORECASTER_UNAVAILABLE, f"No forecaster '{name}' is installed.", name=name)


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


def build_forecaster(method: str, name: str, key: str, tz: ZoneInfo, loader=load_forecaster) -> Forecaster:
    """The forecaster for a ``publish.json`` method. Only ``plugin`` needs a name and a key."""
    if method == METHOD_MIRROR:
        return MirrorForecaster(tz)
    if method == METHOD_HOLD:
        return HoldLastForecaster()
    return loader(name, key)
