"""MQTT connection. ``paho-mqtt`` is optional (extra ``mqtt``); the publisher only needs ``MqttLink``."""

from __future__ import annotations

import importlib
import os
from typing import Protocol

from edibert.errors import EdibertError, ErrorCode
from edibert.publish.config import MqttSettings
from edibert.publish.payloads import OFFLINE, ONLINE, bridge_status_topic

CONNECT_TIMEOUT_S = 15
PREVIEW_CHARS = 200


class MqttLink(Protocol):
    def publish(self, topic: str, payload: str, *, retain: bool = True) -> None: ...

    def close(self) -> None:
        """Say ``offline`` on the bridge status topic and disconnect."""
        ...


class PahoLink:
    """Retained publishing over paho-mqtt 2.x with an ``offline`` last will."""

    def __init__(self, settings: MqttSettings, username: str | None, password: str | None) -> None:
        try:
            mqtt = importlib.import_module("paho.mqtt.client")
        except ImportError as exc:
            raise EdibertError(ErrorCode.MQTT_LIBRARY_MISSING, "Install the extra: pip install 'edibert[mqtt]'.") from exc
        self.status_topic = bridge_status_topic(settings.base_topic)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=settings.client_id)
        if username:
            self.client.username_pw_set(username, password)
        if settings.tls:
            self.client.tls_set()
        self.client.will_set(self.status_topic, OFFLINE, qos=1, retain=True)
        self.client.on_connect = self._on_connect
        try:
            self.client.connect(settings.host, settings.port, keepalive=60)
        except OSError as exc:
            raise EdibertError(
                ErrorCode.MQTT_CONNECTION_FAILED,
                f"Cannot connect to MQTT broker {settings.host}:{settings.port}: {exc}",
                host=settings.host,
                port=settings.port,
            ) from exc
        self.client.loop_start()

    def _on_connect(self, client, _userdata, _flags, _reason, _properties) -> None:
        client.publish(self.status_topic, ONLINE, qos=1, retain=True)  # also after every reconnect

    def publish(self, topic: str, payload: str, *, retain: bool = True) -> None:
        info = self.client.publish(topic, payload, qos=1, retain=retain)
        info.wait_for_publish(CONNECT_TIMEOUT_S)

    def close(self) -> None:
        self.publish(self.status_topic, OFFLINE)
        self.client.loop_stop()
        self.client.disconnect()


class PrintLink:
    """Dry run: shows what would be published."""

    def publish(self, topic: str, payload: str, *, retain: bool = True) -> None:
        shown = payload if len(payload) <= PREVIEW_CHARS else payload[:PREVIEW_CHARS] + "..."
        print(f"{topic}  {shown}")

    def close(self) -> None:
        self.publish("(bridge)", OFFLINE)


def connect(settings: MqttSettings) -> MqttLink:
    """User name and password come from the environment variables named in the settings."""
    username = os.environ.get(settings.username_env, "") if settings.username_env else None
    password = os.environ.get(settings.password_env, "") if settings.password_env else None
    return PahoLink(settings, username or None, password or None)
