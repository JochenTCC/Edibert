<!-- source: docs/user/en/publishing.md @ 0.1.e -->
# Preise über MQTT veröffentlichen

Edbert kann die Preise deiner Tarife an einen MQTT-Broker senden. Home Assistant findet die Sensoren selbst (MQTT-Discovery); andere Systeme lesen die Topics direkt.

```bash
pip install -e ".[mqtt]"
python -m edbert publish --data-dir edbert_data
```

Der Befehl läuft, bis du ihn mit Strg+C beendest. Er veröffentlicht beim Start und danach jede Viertelstunde, damit der aktuelle Preis immer stimmt. `--once` veröffentlicht einmal und beendet, `--dry-run` zeigt die Topics an, statt sie zu senden (ohne Broker).

## Was im Datenordner liegen muss

Der Ordner ist derselbe wie beim Editor (`--data-dir`):

| Datei | Inhalt |
|---|---|
| `user_tariffs.json` | deine Tarife, vom Editor geschrieben |
| `house.json` | Zeitzone, Land, Region und Netzentgelt, vom Editor geschrieben |
| `publish.json` | welche Tarife wohin veröffentlicht werden (einmal selbst anlegen) |

```json
{
  "mqtt": {
    "host": "192.168.1.20",
    "port": 1883,
    "username_env": "EDBERT_MQTT_USER",
    "password_env": "EDBERT_MQTT_PASSWORD",
    "tls": false,
    "base_topic": "edbert",
    "discovery_prefix": "homeassistant"
  },
  "tariffs": [
    { "id": "user_my_spot" },
    { "id": "user_my_feed_in", "direction": "export" }
  ],
  "resolution_min": 15
}
```

* `username_env` und `password_env` sind die **Namen von Umgebungsvariablen**. Benutzername und Passwort stehen nie in einer Datei.
* `direction` ist `import` (Standard) oder `export` (Einspeisung).
* `resolution_min` ist 15, 30 oder 60 Minuten.
* Im Block `mqtt` ist nur `host` Pflicht.

## Börsenpreise

Tarife, die vom Börsenpreis abhängen (Börsentarife oder Regeln mit Börsenpreis-Bedingung), brauchen die Day-Ahead-Preise. Edbert holt sie auf demselben Weg wie Earnie:

1. der lokale Zwischenspeicher (`market_<zone>.json` im Datenordner),
2. ENTSO-E Transparency, wenn die Umgebungsvariable `ENTSOE_API_TOKEN` gesetzt ist (kostenloser Token von entsoe.eu),
3. Energy-Charts (kostenlos, ohne Token),
4. aWATTar (nur Österreich und Deutschland).

Die Day-Ahead-Preise für morgen erscheinen gegen 12:00 Uhr MEZ. Ab dann erwartet Edbert sie; bis sie da sind, wird nur heute veröffentlicht und `tomorrow_valid` ist `false`. Fällt eine Quelle aus, wird die nächste versucht. Hat keine Quelle alle Preise, wird die beste Teilantwort veröffentlicht und die Lücke gemeldet; fehlen die Preise von heute, gehen die Börsentarife **offline** (es wird kein Preis erfunden). Tarife ohne Börsenpreis (fest, Zeitfenster) sind nie betroffen.

Die Daten von Energy-Charts.info (Fraunhofer ISE) stehen unter CC BY 4.0; Edbert nennt die Quelle in den Sensor-Attributen.

## Topics

Für einen Tarif `<id>` mit Richtung `<dir>` (`import` oder `export`):

| Topic | Inhalt |
|---|---|
| `edbert/<dir>/<id>/state` | aktueller Preis in EUR/kWh (retained) |
| `edbert/<dir>/<id>/attributes` | JSON, siehe unten (retained) |
| `edbert/<dir>/<id>/availability` | `online` oder `offline` (retained) |
| `edbert/status` | `online`, solange Edbert läuft, `offline` beim Beenden oder bei Verbindungsverlust |
| `homeassistant/sensor/edbert_<dir>_<id>/config` | Home-Assistant-Discovery |

Attribute (Auszug): `current_cent_kwh`, `components` (Lieferant, Netz, USt in EUR/kWh), `next`, `average_today`, `min_today`, `max_today`, `raw_today` und `raw_tomorrow` (Listen aus `{start, end, value}` in EUR/kWh, das von Nordpool und evcc bekannte Format), `tomorrow_valid`, `forecast`, `market` (Zone, Quelle, Zeitpunkt des Abrufs, Quellenangabe) und `updated`.

## Prognose (optional)

Die Day-Ahead-Preise enden mit dem nächsten Tag. Wenn du Preise weiter voraus willst (etwa um Batterie oder Wärmepumpe über mehrere Tage zu planen), ergänze in `publish.json` einen Abschnitt `forecast`. Prognosepreise laufen wie echte Preise durch deinen Tarif, werden aber nur im Attribut `forecast` (mit `forecast_method`) veröffentlicht, nie in `raw_today` oder `raw_tomorrow`.

```json
"forecast": { "method": "mirror", "hours": 48 }
```

| `method` | Was passiert | Braucht |
|---|---|---|
| `mirror` (Standard) | nimmt den Preis der gleichen Uhrzeit von einem früheren Tag, bis zu 7 Tage zurück (wie in Earnie) | nichts |
| `hold` | hält den letzten bekannten Preis konstant | nichts |
| `plugin` | ein Prognosemodell aus einem installierten Paket, mit `"name": "my_forecaster"` | das Paket und einen **Schlüssel** in der Umgebungsvariable `EDBERT_FORECAST_KEY` |

`hours` bestimmt, wie weit die Prognose reicht (1 bis 72, Standard 48). Sie endet, wo sich kein Preis ableiten lässt, und zwar zu einer vollen Stunde. Für `mirror` behält Edbert die letzten 7 Tage an Preisen im Zwischenspeicher; nach dem ersten Start dauert es also etwa einen Tag, bis weit genug zurückgeschaut werden kann.

Die freie Edbert-Version enthält kein Plug-in; der Schlüssel schaltet es frei. Fehlt das Plug-in oder der Schlüssel, bricht Edbert mit einem Fehler ab und weist darauf hin, den Schlüssel zu setzen oder `mirror` bzw. `hold` zu wählen. Fällt ein Plug-in im laufenden Betrieb aus, werden nur die exakten Preise veröffentlicht und eine Warnung angezeigt.
