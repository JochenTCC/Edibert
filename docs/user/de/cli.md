<!-- source: docs/user/en/cli.md @ 0.1.d2 -->
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

Ein Netzgebiet kann neben dem Arbeitspreis weitere Bestandteile je kWh und Fixbeträge je Jahr haben; `price` zeigt die Bestandteile des Netzentgelts und die Fixbeträge (netto, EUR pro Jahr) unter dem Preis des Zeitpunkts, nie darin.

Für Betreiber einer Tarifdatenbank: `python -m edibert grid check DATEI [--require-check]` prüft eine Katalog-Netzentgeltdatei wie beim Laden und listet jedes Netzgebiet mit Datenbank-ID, Version, Prüfung und den Fixbeträgen je Messart (`–`, wo ein Wert nicht abgebildet ist); `--require-check` schlägt bei einem Netzgebiet ohne Prüfung fehl.

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

## Tarifdatenbank

```bash
python -m edibert exchange fetch --out package.json [--catalog tariffs.json]
python -m edibert exchange templates --land AT --direction import [--supplier NAME] [--format json]
python -m edibert exchange status --data-dir edibert_data [--catalog tariffs.json]
python -m edibert exchange report --data-dir edibert_data [--catalog tariffs.json] [--no-delay]
```

`fetch` lädt das neueste Katalogpaket der Tarifdatenbank herunter; es ist kostenlos, braucht keinen Schlüssel und enthält nur geprüfte und vom Anbieter freigegebene Tarife. Mit `--catalog` wird nichts heruntergeladen, solange dein Katalog schon das neueste Paket enthält. Prüfe und importiere die Datei wie oben mit `package import`.

`templates` listet die ungeprüften Tarife, die andere Nutzer geteilt haben, für ein Land und eine Richtung (`import`, `export`, `grid`; `--grid-area` grenzt `grid` auf ein Netzgebiet ein). `--supplier` sucht in Anbieter und Bezeichnung (mindestens zwei Zeichen). Jede Zeile zeigt Datenbank-ID, Version, Bezeichnung, Anbieter, Vertrauensstufe und Installationen. Vorlagen werden nie als Katalog importiert: Kopiere eine im Editor (**Vorlage kopieren**) und gleiche sie mit dem Preisblatt ab.

`status` zeigt für die Tarife aus `publish.json` die Vertrauensstufe (vom Anbieter freigegeben, geprüft, verlässlich, ungeprüft), ob die Datenbank eine neuere oder eine geprüfte Version hat, ob der Eintrag mit einem anderen zusammengeführt wurde, ob die Version als verlässlich gilt und wie viele Installationen sie in den letzten zwölf Monaten genutzt haben. `report` meldet der Datenbank, welche dieser Tarifversionen du nutzt: eine Meldung pro Tarif, jede zu einem zufälligen Zeitpunkt in den nächsten 24 Stunden (`--no-delay` sendet sofort). Eine Meldung enthält nur die Datenbank-ID, die Version und einen Code, der für jeden Tarif anders ist; deine Tarife lassen sich so weder miteinander noch mit dir verknüpfen. Gemeldet werden nur Tarife, die du mit unveränderten Preisen aus der Datenbank übernommen hast, und Katalogtarife aus einem Paket.

Die Preise werden immer auf deinem Computer berechnet; der Server liefert nur Pakete und zählt die Nutzung. `EDIBERT_EXCHANGE_OFF=1` schaltet jeden Austausch ab, auch das Teilen im Editor.

## Veröffentlichen

```bash
python -m edibert publish --data-dir edibert_data [--once] [--dry-run] [--catalog tariffs.json] [--config publish.json]
```

Veröffentlicht die Tarife aus `publish.json` an einen MQTT-Broker, siehe [Veröffentlichen](publishing.md). Exit-Code 1 heißt: Mindestens ein Tarif ging offline (zum Beispiel, weil keine Börsenpreise verfügbar waren).

## Schema

`python -m edibert schema` gibt das JSON-Schema eines Tarifs aus, für Editoren und Werkzeuge.
