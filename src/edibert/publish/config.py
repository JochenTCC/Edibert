"""``publish.json``: which tariffs go to which MQTT broker. Passwords are never stored here."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edibert._fields import (
    as_dict,
    check_known,
    get_bool,
    get_number,
    get_str,
    invalid,
    missing,
)
from edibert.errors import EdibertError, ErrorCode
from edibert.market.forecast import METHOD_MIRROR
from edibert.publish.forecasters import METHOD_PLUGIN, METHODS
from edibert.series import RESOLUTIONS
from edibert.tariff import EXPORT, IMPORT

CONFIG_NAME = "publish.json"
DEFAULT_BASE_TOPIC = "edibert"
DEFAULT_DISCOVERY_PREFIX = "homeassistant"
MAX_FORECAST_HOURS = 72
_ROOT_FIELDS = ("tariffs", "mqtt", "resolution_min", "forecast", "$schema")
_MQTT_FIELDS = ("host", "port", "username_env", "password_env", "tls", "base_topic", "discovery_prefix", "client_id")
_TARIFF_FIELDS = ("id", "direction")
_FORECAST_FIELDS = ("method", "name", "hours")


@dataclass(frozen=True)
class MqttSettings:
    host: str
    port: int = 1883
    username_env: str | None = None  # name of an environment variable, not the user name itself
    password_env: str | None = None
    tls: bool = False
    base_topic: str = DEFAULT_BASE_TOPIC
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX
    client_id: str = "edibert"


@dataclass(frozen=True)
class TariffRef:
    id: str
    direction: str = IMPORT


@dataclass(frozen=True)
class ForecastSettings:
    method: str = METHOD_MIRROR
    name: str = ""  # only for the method "plugin"
    hours: int = 48


@dataclass(frozen=True)
class PublishConfig:
    mqtt: MqttSettings
    tariffs: tuple[TariffRef, ...] = field(default_factory=tuple)
    resolution_min: int = 15
    forecast: ForecastSettings | None = None


def _parse_mqtt(raw: object) -> MqttSettings:
    data = as_dict(raw, "mqtt")
    check_known(data, _MQTT_FIELDS, "mqtt")
    port = get_number(data, "port", "mqtt", minimum=1, maximum=65535)
    return MqttSettings(
        host=get_str(data, "host", "mqtt", required=True) or "",
        port=int(port) if port is not None else 1883,
        username_env=get_str(data, "username_env", "mqtt"),
        password_env=get_str(data, "password_env", "mqtt"),
        tls=get_bool(data, "tls", "mqtt", False),
        base_topic=(get_str(data, "base_topic", "mqtt") or DEFAULT_BASE_TOPIC).strip("/"),
        discovery_prefix=(get_str(data, "discovery_prefix", "mqtt") or DEFAULT_DISCOVERY_PREFIX).strip("/"),
        client_id=get_str(data, "client_id", "mqtt") or "edibert",
    )


def _parse_tariffs(raw: object) -> tuple[TariffRef, ...]:
    if not isinstance(raw, list) or not raw:
        raise invalid("tariffs", raw) if raw is not None else missing("tariffs")
    refs: list[TariffRef] = []
    for index, item in enumerate(raw):
        where = f"tariffs[{index}]"
        data = as_dict(item, where)
        check_known(data, _TARIFF_FIELDS, where)
        direction = get_str(data, "direction", where) or IMPORT
        if direction not in (IMPORT, EXPORT):
            raise invalid(f"{where}.direction", direction)
        ref = TariffRef(get_str(data, "id", where, required=True) or "", direction)
        if ref in refs:
            raise invalid(f"{where}.id", ref.id)
        refs.append(ref)
    return tuple(refs)


def _parse_forecast(raw: object) -> ForecastSettings | None:
    if raw is None:
        return None
    data = as_dict(raw, "forecast")
    check_known(data, _FORECAST_FIELDS, "forecast")
    hours = get_number(data, "hours", "forecast", minimum=1, maximum=MAX_FORECAST_HOURS)
    method = get_str(data, "method", "forecast") or METHOD_MIRROR
    if method not in METHODS:
        raise invalid("forecast.method", method)
    name = get_str(data, "name", "forecast", required=method == METHOD_PLUGIN)
    if name and method != METHOD_PLUGIN:
        raise invalid("forecast.name", name)  # a name only makes sense for a plug-in
    return ForecastSettings(method, name or "", int(hours) if hours is not None else 48)


def parse_publish_config(raw: object) -> PublishConfig:
    data = as_dict(raw, "publish")
    check_known(data, _ROOT_FIELDS, "publish")
    if "mqtt" not in data:
        raise missing("mqtt")
    resolution = get_number(data, "resolution_min", "publish")
    if resolution is not None and int(resolution) not in RESOLUTIONS:
        raise invalid("resolution_min", resolution)
    return PublishConfig(
        mqtt=_parse_mqtt(data["mqtt"]),
        tariffs=_parse_tariffs(data.get("tariffs")),
        resolution_min=int(resolution) if resolution is not None else 15,
        forecast=_parse_forecast(data.get("forecast")),
    )


def load_publish_config(path: Path) -> PublishConfig:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc
    return parse_publish_config(raw)
