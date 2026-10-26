"""The paho adapter (with a fake paho module), the dry-run link and the forecaster loader."""

from types import SimpleNamespace

import pytest
from market_helpers import utc

from edibert.errors import EdibertError, ErrorCode
from edibert.market.cache import CacheEntry, read_cache, write_cache
from edibert.publish import forecasters as forecast
from edibert.publish import mqtt
from edibert.publish.config import MqttSettings

SETTINGS = MqttSettings(host="broker", port=8883, tls=True, base_topic="edibert", client_id="cid")


class FakeInfo:
    def wait_for_publish(self, timeout):
        self.timeout = timeout


class FakeClient:
    def __init__(self, api, client_id, fail=False):
        self.api, self.client_id, self.fail = api, client_id, fail
        self.calls = []
        self.published = []

    def username_pw_set(self, user, password):
        self.calls.append(("auth", user, password))

    def tls_set(self):
        self.calls.append(("tls",))

    def will_set(self, topic, payload, qos, retain):
        self.calls.append(("will", topic, payload, qos, retain))

    def connect(self, host, port, keepalive):
        if self.fail:
            raise OSError("refused")
        self.calls.append(("connect", host, port, keepalive))

    def loop_start(self):
        self.calls.append(("loop_start",))

    def loop_stop(self):
        self.calls.append(("loop_stop",))

    def disconnect(self):
        self.calls.append(("disconnect",))

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        return FakeInfo()


def fake_paho(monkeypatch, fail=False):
    module = SimpleNamespace(CallbackAPIVersion=SimpleNamespace(VERSION2="v2"), Client=lambda api, client_id: FakeClient(api, client_id, fail))
    monkeypatch.setattr(mqtt, "importlib", SimpleNamespace(import_module=lambda name: module))


def test_paho_link_sets_will_credentials_tls_and_publishes_retained(monkeypatch):
    fake_paho(monkeypatch)
    link = mqtt.PahoLink(SETTINGS, "user", "secret")
    client = link.client
    assert ("auth", "user", "secret") in client.calls
    assert ("tls",) in client.calls
    assert ("will", "edibert/status", "offline", 1, True) in client.calls
    assert ("connect", "broker", 8883, 60) in client.calls
    link.publish("edibert/x", "1")
    assert client.published == [("edibert/x", "1", 1, True)]
    client.on_connect(client, None, None, 0, None)
    assert client.published[-1] == ("edibert/status", "online", 1, True)  # again after a reconnect
    link.close()
    assert client.published[-1] == ("edibert/status", "offline", 1, True)
    assert client.calls[-2:] == [("loop_stop",), ("disconnect",)]


def test_connection_failure_is_a_coded_error(monkeypatch):
    fake_paho(monkeypatch, fail=True)
    with pytest.raises(EdibertError) as err:
        mqtt.PahoLink(SETTINGS, None, None)
    assert err.value.code == ErrorCode.MQTT_CONNECTION_FAILED
    assert err.value.params == {"host": "broker", "port": 8883}


def test_missing_library_is_a_coded_error(monkeypatch):
    def refuse(name):
        raise ImportError(name)

    monkeypatch.setattr(mqtt, "importlib", SimpleNamespace(import_module=refuse))
    with pytest.raises(EdibertError) as err:
        mqtt.PahoLink(SETTINGS, None, None)
    assert err.value.code == ErrorCode.MQTT_LIBRARY_MISSING


def test_credentials_are_read_from_the_named_environment_variables(monkeypatch):
    fake_paho(monkeypatch)
    monkeypatch.setenv("MY_USER", "alice")
    monkeypatch.setenv("MY_PASS", "pw")
    settings = MqttSettings(host="b", username_env="MY_USER", password_env="MY_PASS")
    link = mqtt.connect(settings)
    assert ("auth", "alice", "pw") in link.client.calls


def test_dry_run_link_prints_and_shortens_long_payloads(capsys):
    link = mqtt.PrintLink()
    link.publish("t/a", "x" * 500)
    link.close()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("t/a  xxx")
    assert lines[0].endswith("...")
    assert lines[1].endswith("offline")


def test_forecaster_is_loaded_from_the_entry_point_group(monkeypatch):
    class Demo:
        def __init__(self, key):
            self.key = key

        def forecast(self, known, start, end):
            return {}

    point = SimpleNamespace(name="demo", value="pkg:Demo", load=lambda: Demo)
    monkeypatch.setattr(forecast, "entry_points", lambda group: [point] if group == "edibert.forecasters" else [])
    assert forecast.available_forecasters() == {"demo": "pkg:Demo"}
    assert forecast.load_forecaster("demo", " k-1 ").key == "k-1"  # the key is handed over, validation is the plug-in's job
    with pytest.raises(EdibertError) as err:
        forecast.load_forecaster("other", "k-1")
    assert err.value.code == ErrorCode.FORECASTER_UNAVAILABLE
    with pytest.raises(EdibertError) as err:
        forecast.load_forecaster("demo", "  ")
    assert err.value.code == ErrorCode.FORECAST_KEY_MISSING
    assert err.value.params == {"env": "EDIBERT_FORECAST_KEY"}


def test_cache_round_trip_and_damage(tmp_path):
    moment = utc("2026-12-15T09:00")
    entry = CacheEntry("AT", "awattar", moment, moment, {moment: 12.5})
    path = tmp_path / "c.json"
    assert read_cache(path) is None
    write_cache(path, entry)
    assert read_cache(path) == entry
    path.write_text('{"zone": "AT"}', encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable"):
        read_cache(path)
