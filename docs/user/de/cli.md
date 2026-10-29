<!-- source: docs/user/en/cli.md @ 0.1.e -->
# Kommandozeile

Mit `--lang de` vor dem Befehl erscheint die Ausgabe auf Deutsch.

## Preis eines Zeitabschnitts

```bash
python -m edibert price --tariff examples/spot_evening_surcharge_cap.json \
    --at 2026-12-15T18:00 --tz Europe/Vienna --epex 10
```

Gibt Basispreis, angewendete Regel, Netzentgelt und Endpreis aus. Tarife mit Regeln für bestimmte Tage brauchen `--land` und `--region`, weil Feiertage den Preis ändern können. Ein Börsentarif braucht `--epex` (ct/kWh).

## Preisreihe

```bash
python -m edibert series --tariff examples/spot_evening_surcharge_cap.json \
    --from 2026-12-15T00:00 --to 2026-12-16T00:00 --tz Europe/Vienna \
    --market-csv market.csv --resolution 60
```

`--resolution` ist 15, 30 oder 60 Minuten. Die Börsenpreisdatei hat eine Zeile je Viertelstunde: `timestamp,cent_kwh`. Fehlt ein Preis, bricht der Befehl mit einem Fehler ab. `--format json` gibt die ganze Reihe aus. `--has smart_meter` (wiederholbar) nennt die Ausstattung des Hauses und schaltet die Prüfung der Voraussetzungen ein.

## Netzentgelt

Mit `--grid-fee house_grid.json` wird ein Netzentgelt eingerechnet. Die Datei enthält das Objekt `netznutzung` des Hausprofils, das per `area_id` einen Netzbereich auswählt (siehe `examples/netznutzung_modul3_example.json`). Der Bereich kommt aus `--grid-catalog grid_fees.json` (Katalog-Netzbereiche) oder `--user-grid-fees user_grid_fees.json` (eigene Netzbereiche, IDs beginnen mit `user_`, siehe `examples/grid_fee_modul3_example.json`); beide Angaben sind kombinierbar. Ein unbekannter Netzbereich bricht den Befehl mit einem Fehler ab.

## Leistungspreis

```bash
python -m edibert capacity --grid-fee house_grid.json --user-grid-fees examples/grid_fee_capacity_example.json --tz Europe/Vienna --month 2027-01 --peak-so-far 4.2 --as-of 2027-01-14T18:00 --power 12
```

Für Netzbereiche mit Leistungspreis (ein Monatspreis je kW der höchsten Viertelstunde des Monats). Der Befehl zeigt den Leistungspreis des Monats `--month` (`JJJJ-MM`): mit `--power` den Monatsbetrag für diese Spitze, dazu eine Tabelle, was jede höhere Spitze zusätzlich kosten würde. `--peak-so-far` ist die bisher höchste gemessene Viertelstunde des Monats in kW und braucht `--as-of`, den Zeitpunkt dieses Werts; ohne sie zeigt die Tabelle die vollen Monatsbeträge. `--step 2 --max 16` ergänzt Zeilen alle 2 kW bis 16 kW. `--format json` gibt die Tabelle als JSON aus. Die Beträge sind netto. Ein Monat ohne passenden Eintrag im Netzbereich bricht den Befehl mit einem Fehler ab; für einen Monat vor dem Start des Leistungspreises meldet der Befehl, dass es keinen gibt.

## Katalogpaket

```bash
python -m edibert package verify package.json
python -m edibert package import package.json --catalog tariffs.json --grid-catalog grid_fees.json [--dry-run]
```

Ein Katalogpaket ist eine signierte Datei aus der Tarif-Datenbank, die die Katalogdateien `tariffs.json` und `grid_fees.json` ersetzt. Deine eigenen Tarife (`user_tariffs.json`) und Netzbereiche bleiben unverändert. `verify` prüft Signatur und Inhalt und zeigt das Paket an; ein verändertes oder beschädigtes Paket wird abgelehnt. Ein Paket nach seinem Gültigkeitsdatum funktioniert weiter, mit dem Hinweis, dass es keine Updates mehr bekommt.

`import` listet zuerst, was sich ändert (neue, geänderte und entfernte Einträge). Hast du selbst Monatswerte eingetragen, die das Paket nicht oder mit einem anderen Wert hat, steht jeder als Konflikt in der Liste, zum Beispiel `import/at_example/2026-11`, und der Import bricht ab, bis du entscheidest: `--keep-local KEY` behält deinen Wert, `--take-package KEY` übernimmt den aus dem Paket (beide wiederholbar). `--dry-run` zeigt nur die Liste. Schlägt das Schreiben fehl, bleiben die alten Katalogdateien erhalten.

## Veröffentlichen

```bash
python -m edibert publish --data-dir edibert_data [--once] [--dry-run] [--catalog tariffs.json] [--config publish.json]
```

Veröffentlicht die Tarife aus `publish.json` an einen MQTT-Broker, siehe [Veröffentlichen](publishing.md). Exit-Code 1 heißt: Mindestens ein Tarif ging offline (zum Beispiel, weil keine Börsenpreise verfügbar waren).

## Schema

`python -m edibert schema` gibt das JSON-Schema eines Tarifs aus, für Editoren und Werkzeuge.
