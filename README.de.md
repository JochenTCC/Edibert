# Edibert

[English](README.md) · **Deutsch** · *Die englische Fassung ist maßgeblich.*

*Früher Edbert (umbenannt am 2026-10-26).*

**Edibert** ist ein Tarif-Editor und Preisdienst für Smart-Home-Systeme. Du beschreibst deinen Stromtarif einmal (fest, börsengebunden oder zeitvariabel mit Fenstern, Wochentagen, Feiertagen) und Edibert liefert die daraus berechneten Preise als Zeitreihe an dein Smart-Home-Backend: als Home-Assistant-Sensor oder per MQTT.

> **Status: Entwurf.** Die Regel-Engine (`0.1.a`), die Preisreihe mit Netzentgelt (`0.1.b`) der Tarif-Editor im Browser (`0.1.c`) und die MQTT-Ausgabe mit Home-Assistant-Discovery (`0.1.e`) funktionieren. Eine native Home-Assistant-Integration gibt es noch nicht. Siehe [Roadmap](#roadmap).

## Der Tarif-Editor

```bash
pip install -e ".[ui]"
python -m edibert ui --data-dir edibert_data
```

`http://localhost:8501` öffnen. Vier Schritte (Basispreis, Zeitfenster, weitere Kosten, erweitert), Preisverlauf live, Preis zu einem Zeitpunkt, Prüfung gegen eine echte Rechnung, Katalogtarif kopieren, JSON importieren. Deutsch und Englisch. Siehe die [Bedienungsanleitung](docs/user/de/index.md).

## Über MQTT veröffentlichen

```bash
pip install -e ".[mqtt]"
python -m edibert publish --data-dir edibert_data
```

Sendet die Preise der in `publish.json` genannten Tarife (aktueller Preis, heute, morgen, optional Prognose) als retained MQTT-Topics mit Home-Assistant-Discovery. Die Börsenpreise kommen über dieselbe Kette wie in Earnie (ENTSO-E mit Token, Energy-Charts, aWATTar). Siehe [Veröffentlichen](docs/user/de/publishing.md).

## Ausprobieren

```bash
pip install -e ".[dev]"
python -m edibert --lang de price --tariff examples/spot_evening_surcharge_cap.json     --at 2026-12-15T18:00 --tz Europe/Vienna --epex 10
python -m edibert --lang de price --tariff examples/fixed_day_night.json     --at 2026-12-25T12:00 --tz Europe/Berlin --land DE --region BY
python -m pytest
```

Der erste Befehl zeigt den Preis eines Zeitabschnitts mit allen Schritten (Basispreis, angewendete Regel, Boden/Deckel, USt). Tarife mit Wochentagsregeln brauchen `--land` und `--region`, weil Feiertage das Ergebnis ändern können; ohne diese Angaben bricht der Befehl mit einem Fehler ab, statt zu raten. `python -m edibert schema` gibt das JSON-Schema eines Tarifs aus.

```bash
python -m edibert --lang de series --tariff examples/spot_evening_surcharge_cap.json \
    --grid-fee examples/netznutzung_modul3_example.json \
    --user-grid-fees examples/grid_fee_modul3_example.json \
    --from 2026-12-15T00:00 --to 2026-12-16T00:00 --tz Europe/Vienna \
    --market-csv tests/fixtures/market_2026-12-15.csv --resolution 60
```

`series` gibt Preise über einen Zeitraum aus (15, 30 oder 60 Minuten), berechnet aus Day-Ahead-Preisen in einer CSV (`timestamp,cent_kwh` je Viertelstunde), auf Wunsch mit Netzentgelt. Fehlt ein Börsenpreis, bricht der Befehl mit einem Fehler ab. Warnungen gehen nach stderr.

## Wozu?

Viele Tarife lassen sich nicht in einem Feld „ct/kWh“ beschreiben:

- Nachttarife und Wochenendpreise (HT/NT), Sommer-Mittagsfenster
- Börsenpreis mit Aufschlägen, Deckel und Boden
- zeitvariable Netzentgelte (§14a Modul 3: Hoch-, Standard- und Niedertarif)
- Einspeisung mit „keine Vergütung bei negativem Preis“
- Feiertage, die wie ein Sonntag zählen

Edibert bildet das mit wenigen Bausteinen ab, **ohne dass du JSON von Hand schreiben musst**, und zeigt dir den Preisverlauf sofort an, bevor du ihn verwendest.

## Geplante Funktionen

| Funktion | Beschreibung |
|---|---|
| Tarif-Editor | Geführtes Formular in vier Schritten, Vorschau des Preisverlaufs, Warnung bei Regeln, die nie greifen, Kontrollrechnung gegen eine echte Rechnung |
| Mehrsprachig | Oberfläche und Bedienungsanleitung in Deutsch und Englisch |
| Regel-Engine | Basispreis + Zeitregeln (Monate, Wochentage, Uhrzeit, Feiertage), Deckel/Boden, USt, Netzentgelt |
| Preisreihe | Berechnete Preise für einen wählbaren Zeithorizont (15, 30 oder 60 Minuten), für Bezug **und** Einspeisung |
| Ausgabe | Home-Assistant-Sensoren (`raw_today`, `raw_tomorrow`, `forecast`) und MQTT (retained, mit HA-Discovery) |
| Import | Katalogtarif als Vorlage, JSON-Datei, Preisreihe (CSV), später Assistent für Preisblätter |
| Feiertage | Aus der Bibliothek [`holidays`](https://github.com/vacanza/holidays) (DE/AT/CH nach Bundesland bzw. Kanton), ohne Internet |

Nicht Ziel: Tarife vergleichen oder vermitteln, Rechnungen erstellen, Geräte steuern. Edibert liefert nur Preise.

## Verhältnis zu Earnie

Edibert ist ein eigenständiges Werkzeug und wird auch von [Earnie](https://github.com/JochenTCC/Earnie) genutzt, einem Optimierer für Heimspeicher, PV und Verbraucher. Du brauchst Earnie nicht, um Edibert zu verwenden.

## Katalog und Beiträge

Du kannst jederzeit eigene Tarife anlegen; die Software funktioniert auch ganz ohne Katalog. Dazu gibt es zwei Tarifdatenbanken (DE/AT/CH):

- **Freie Datenbank:** von Nutzern geteilte Tarife, ungeprüft. Eine Tarifversion wird durch Nutzung `reliable` (verlässlich): mindestens zwei Installationen haben sie innerhalb von 12 Monaten verwendet (wer sie geteilt hat, zählt mit). Sie ist für alle kostenlos.
- **Geprüfte Datenbank:** nur Tarife, die wir geprüft haben und aktuell halten. Sie gibt es im Abo.

Beide kommen als **signierte Katalogpakete**, die Edibert vor dem Import ohne Internet prüft. Ein Import überschreibt Monatspreise, die du selbst eingetragen hast, nie ohne Rückfrage. Einen Tarif zu teilen hilft anderen mit demselben Tarif; es bringt keinen Zugang und keine Belohnung, und einen Beitragsweg über GitHub-Issues gibt es nicht.

Geteilt werden nur Tarife, die **nicht auf eine Person zugeschnitten** sind, und nur **ohne Personenbezug** (keine Postleitzahl, kein Name, keine Zählernummer, keine Freitexte, keine Verbrauchsdaten). Das Teilen ist freiwillig, mit Vorschau des genauen Inhalts, und jeder Tarif lässt sich weglassen. Das ist die geplante Funktionsweise, noch kein verbindliches Angebot. Details: [CONTRIBUTING.md](CONTRIBUTING.md) (englisch) und [catalog/README.md](catalog/README.md) (englisch).

## Lizenz

Der Code steht unter der [PolyForm Noncommercial License 1.0.0](LICENSE): Quellcode einsehbar, Nutzung für private, wissenschaftliche, gemeinnützige und andere **nicht-kommerzielle** Zwecke erlaubt, gewerbliche Nutzung nur mit gesonderter Lizenz. Das ist keine Open-Source-Lizenz im Sinne der OSI („Source-Available“).

[LICENSE](LICENSE) und [NOTICE](NOTICE) gelten für den Code. Für den Tarifkatalog und für Tarifbeiträge gelten **gesonderte Bedingungen** sowie eine Datenschutzerklärung. Diese rechtlichen Texte werden **je Land in der Landessprache** verfasst (Deutschland und Österreich: Deutsch, Schweiz: Deutsch) und **erst nach rechtlicher Prüfung** hier veröffentlicht; bis dahin gibt es weder Katalogzugang noch Upload.

## Roadmap

| Schritt | Inhalt |
|---|---|
| T1 | Regel-Engine, Tariffelder, `user_tariffs.json`, Feiertage, Mehrsprachigkeit (Grundlage) |
| T2 | Netzentgelt-Regeln und `tariff_price_series` (die eine Schnittstelle zur Preisreihe) |
| T3 | Editor und Import (Vorlage, JSON-Datei) |
| T3b | MQTT-Ausgabe, Börsenpreis-Kette, Prognose (Spiegeln, Halten, Plug-in mit Schlüssel) |
| T4 | Tarifdatenbanken: Teilen, freie und geprüfte Datenbank, signierte Katalogpakete |
| später | Preisblatt-Assistent, Ausgabe für evcc/EMHASS/Predbat, Preise je Zähler |

Das Format ist in [docs/spec/tariff-format.md](docs/spec/tariff-format.md) (englisch) beschrieben, Beispiele liegen unter [examples/](examples/). Bedienungsanleitungen: [docs/user/de/](docs/user/de/).
