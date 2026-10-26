"""Forecaster choice of the product: the free methods plus plug-ins loaded with a key.

``plugin`` loads a model from an installed package (entry-point group ``edbert.forecasters``). The free
edition ships none. It needs a key: Edbert insists that one is given and hands it to the factory
(``factory(key=...)``); checking it is the job of the plug-in, so the free edition holds no validation.
The key guards only these plug-ins; a forecaster object handed to the library directly needs none.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points
from zoneinfo import ZoneInfo

from edbert.errors import EdbertError, ErrorCode
from edbert.market.forecast import BUILTIN_METHODS, Forecaster, builtin_forecaster

ENTRY_POINT_GROUP = "edbert.forecasters"
FORECAST_KEY_ENV = "EDBERT_FORECAST_KEY"
METHOD_PLUGIN = "plugin"
METHODS = (*BUILTIN_METHODS, METHOD_PLUGIN)


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


def build_forecaster(
    method: str, name: str, key: str, tz: ZoneInfo, loader: Callable[[str, str], Forecaster] = load_forecaster
) -> Forecaster:
    """The forecaster for a ``publish.json`` method. Only ``plugin`` needs a name and a key."""
    if method == METHOD_PLUGIN:
        return loader(name, key)
    return builtin_forecaster(method, tz)
