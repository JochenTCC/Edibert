<!-- source: docs/user/en/cli.md @ 0.1.e -->
# Kommandozeile

Mit `--lang de` vor dem Befehl erscheint die Ausgabe auf Deutsch.

## Preis eines Zeitabschnitts

```bash
python -m edbert price --tariff examples/spot_evening_surcharge_cap.json \
    --at 2026-12-15T18:00 --tz Europe/Vienna --epex 10
```

Gibt Basispreis, angewendete Regel, Netzentgelt und Endpreis aus. Tarife mit Regeln für bestimmte Tage brauchen `--land` und `--region`, weil Feiertage den Preis ändern können. Ein Börsentarif braucht `--epex` (ct/kWh).

## Preisreihe

```bash
python -m edbert series --tariff examples/spot_evening_surcharge_cap.json \
    --from 2026-12-15T00:00 --to 2026-12-16T00:00 --tz Europe/Vienna \
    --market-csv market.csv --resolution 60
```

`--resolution` ist 15, 30 oder 60 Minuten. Die Börsenpreisdatei hat eine Zeile je Viertelstunde: `timestamp,cent_kwh`. Fehlt ein Preis, bricht der Befehl mit einem Fehler ab. `--format json` gibt die ganze Reihe aus. `--has smart_meter` (wiederholbar) nennt die Ausstattung des Hauses und schaltet die Prüfung der Voraussetzungen ein.

## Netzentgelt

Mit `--grid-fee house_grid.json` (das Objekt `netznutzung`, siehe `examples/grid_fee_modul3_example.json`) wird ein Netzentgelt eingerechnet. Mit `--grid-catalog grid_fees.json` lässt sich ein Katalog-Netzbereich verwenden.

## Veröffentlichen

```bash
python -m edbert publish --data-dir edbert_data [--once] [--dry-run] [--catalog tariffs.json] [--config publish.json]
```

Veröffentlicht die Tarife aus `publish.json` an einen MQTT-Broker, siehe [Veröffentlichen](publishing.md). Exit-Code 1 heißt: Mindestens ein Tarif ging offline (zum Beispiel, weil keine Börsenpreise verfügbar waren).

## Schema

`python -m edbert schema` gibt das JSON-Schema eines Tarifs aus, für Editoren und Werkzeuge.
