<!-- source: docs/user/en/publishing.md @ 0.1.e -->
# Preise über MQTT veröffentlichen

Edibert kann die Preise deiner Tarife an einen MQTT-Broker senden. Home Assistant findet die Sensoren selbst (MQTT-Discovery); andere Systeme lesen die Topics direkt.

```bash
pip install -e ".[mqtt]"
python -m edibert publish --data-dir edibert_data
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
    "username_env": "EDIBERT_MQTT_USER",
    "password_env": "EDIBERT_MQTT_PASSWORD",
    "tls": false,
    "base_topic": "edibert",
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

Tarife, die vom Börsenpreis abhängen (Börsentarife oder Regeln mit Börsenpreis-Bedingung), brauchen die Day-Ahead-Preise. Edibert holt sie auf demselben Weg wie Earnie:

1. der lokale Zwischenspeicher (`market_<zone>.json` im Datenordner),
2. ENTSO-E Transparency, wenn die Umgebungsvariable `ENTSOE_API_TOKEN` gesetzt ist (kostenloser Token von entsoe.eu),
3. Energy-Charts (kostenlos, ohne Token),
4. aWATTar (nur Österreich und Deutschland).

Die Day-Ahead-Preise für morgen erscheinen gegen 12:00 Uhr MEZ. Ab dann erwartet Edibert sie; bis sie da sind, wird nur heute veröffentlicht und `tomorrow_valid` ist `false`. Fällt eine Quelle aus, wird die nächste versucht. Hat keine Quelle alle Preise, wird die beste Teilantwort veröffentlicht und die Lücke gemeldet; fehlen die Preise von heute, gehen die Börsentarife **offline** (es wird kein Preis erfunden). Tarife ohne Börsenpreis (fest, Zeitfenster) sind nie betroffen.

Die Daten von Energy-Charts.info (Fraunhofer ISE) stehen unter CC BY 4.0; Edibert nennt die Quelle in den Sensor-Attributen.

## Topics

Für einen Tarif `<id>` mit Richtung `<dir>` (`import` oder `export`):

| Topic | Inhalt |
|---|---|
| `edibert/<dir>/<id>/state` | aktueller Preis in EUR/kWh (retained) |
| `edibert/<dir>/<id>/attributes` | JSON, siehe unten (retained) |
| `edibert/<dir>/<id>/availability` | `online` oder `offline` (retained) |
| `edibert/status` | `online`, solange Edibert läuft, `offline` beim Beenden oder bei Verbindungsverlust |
| `homeassistant/sensor/edibert_<dir>_<id>/config` | Home-Assistant-Discovery |

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
| `plugin` | ein Prognosemodell aus einem installierten Paket, mit `"name": "my_forecaster"` | das Paket und einen **Schlüssel** in der Umgebungsvariable `EDIBERT_FORECAST_KEY` |

`hours` bestimmt, wie weit die Prognose reicht (1 bis 72, Standard 48). Sie endet, wo sich kein Preis ableiten lässt, und zwar zu einer vollen Stunde. Für `mirror` behält Edibert die letzten 7 Tage an Preisen im Zwischenspeicher; nach dem ersten Start dauert es also etwa einen Tag, bis weit genug zurückgeschaut werden kann.

Die freie Edibert-Version enthält kein Plug-in; der Schlüssel schaltet es frei. Fehlt das Plug-in oder der Schlüssel, bricht Edibert mit einem Fehler ab und weist darauf hin, den Schlüssel zu setzen oder `mirror` bzw. `hold` zu wählen. Fällt ein Plug-in im laufenden Betrieb aus, werden nur die exakten Preise veröffentlicht und eine Warnung angezeigt.

## Tarifdatenbank (optional)

Der Publisher kann mit dem Server der Tarifdatenbank sprechen (siehe [CLI](cli.md), Abschnitt exchange): melden, welche Katalogtarife du verwendest, fragen, ob es eine neuere Version gibt, und deinen Katalog aktuell halten. Es wird nichts gesendet, solange du diesen Block nicht in `publish.json` einträgst:

```json
"exchange": { "report_use": true, "status": true, "packages": true }
```

| Aufgabe | Was passiert |
|---|---|
| `report_use` | einmal am Tag je Tarif aus der Datenbank eine Meldung zu einer zufälligen Zeit mit Datenbank-ID, Version und einem Pseudonym, das auf deinem Rechner berechnet wird (keine Installations-ID, das Pseudonym ist für jeden Tarif anders) |
| `status` | fragt einmal am Tag nach Prüfstatus und neuester Version dieser Tarife und ob sie als verlässlich gelten |
| `packages` | lädt einmal pro Woche (oder bevor das aktuelle Paket abläuft) das Katalogpaket und importiert es; braucht `--catalog` |

Alle drei müssen genannt sein, `true` oder `false`. `EDIBERT_EXCHANGE_OFF=1` schaltet alles ab. Das Katalogpaket der Tarifdatenbank ist kostenlos, braucht keinen Schlüssel und enthält nur geprüfte und vom Anbieter freigegebene Tarife.

Ein Paket wird nur dann automatisch importiert, wenn dabei nichts verloren geht: Würde es selbst eingetragene Monatspreise ändern oder enthält es einen Tarif nicht mehr, den du veröffentlichst, wird es nicht importiert, und eine Warnung sagt warum. Importiere es dann im Editor (Seitenleiste, *Katalogpaket importieren*) und entscheide dort. Ein Ausfall des Servers berührt die Preise nie; die Aufgabe wird eine Stunde später erneut versucht.

Die Attribute jedes Tarifs bekommen einen Block `catalog` mit Datenbank-ID und Version, Prüfstatus und -datum (`check_state`, `checked_at`), `reliable`, der Vertrauensstufe `trust_level` (`released_by_supplier`, `checked`, `reliable`, `unchecked`) und `check_overdue` (die letzte Prüfung ist älter als ein Quartal plus 30 Tage). Ein Katalogtarif aus einem importierten Paket zeigt seinen Prüfstatus auch ohne `status`. Mit `status` sagt der Block außerdem, wie viele Installationen ihn in den letzten 12 Monaten verwendet haben, ob es eine neuere Version gibt (`newer_version`, `newer_valid_from`), ob es eine andere geprüfte Version gibt (`checked_version_available`) und ob der Eintrag mit einem anderen zusammengeführt wurde (`merged_into`). Was sich die Aufgaben merken, steht in `exchange_state.json` im Datenordner.
