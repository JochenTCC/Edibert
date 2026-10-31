<!-- source: docs/user/en/getting-started.md @ 0.1.d2 -->
# Erste Schritte

## Installation

Edibert braucht Python 3.11 oder neuer.

```bash
pip install -e ".[ui]"
```

`[ui]` ergänzt Streamlit, das den Editor zeichnet. Ohne diesen Zusatz funktioniert die Kommandozeile weiterhin.

## Den Editor starten

```bash
python -m edibert ui --data-dir edibert_data
```

Danach `http://localhost:8501` im Browser öffnen. Mit `--lang de` vor `ui` startet er auf Deutsch, mit `--port 8601` auf einem anderen Port, und mit `--catalog tariffs.json` kannst du Tarife aus einer Katalogdatei kopieren.

```bash
python -m edibert --lang de ui --data-dir edibert_data --catalog tariffs.json
```

## Wo deine Daten liegen

Alles bleibt auf deinem Rechner im Datenordner (Standard `edibert_data`):

| Datei | Inhalt |
|---|---|
| `user_tariffs.json` | deine Tarife |
| `house.json` | Haus-Einstellungen (Zeitzone, Standort, Messart, gewähltes Netzgebiet) |
| `user_grid_fees.json` | deine eigenen Netzentgelt-Werte (Netzgebiet `user_house`) |

Es wird nichts irgendwohin gesendet. Einen Upload gibt es noch nicht.

## Sprache

In der Seitenleiste gibt es die Auswahl **Sprache** (Englisch oder Deutsch). Deine Eingaben bleiben beim Wechsel erhalten.

## Haus-Einstellungen

Öffne einmal **Haus-Einstellungen** in der Seitenleiste, bevor du dich auf die Vorschau verlässt:

- **Zeitzone** (z. B. `Europe/Vienna`). Alle Zeiten sind Ortszeit des Hauses.
- **Land** und **Bundesland / Kanton.** Die Region ist nötig, sobald ein Tarif Regeln für bestimmte Tage hat, weil Feiertage den Preis ändern können. Ohne Region bricht Edibert mit einer klaren Meldung ab, statt zu raten.
- **Ausstattung des Hauses**: Smart Meter, Viertelstundenzähler, separater Zähler, steuerbare Verbrauchseinrichtung. Ein Tarif, der etwas verlangt, das dem Haus fehlt, bekommt einen Hinweis.

Mit **Haus-Einstellungen speichern** bleiben sie erhalten.

## Netzentgelt

Das Netzentgelt des Netzbetreibers ist für alle Tarife gleich, egal welcher Stromanbieter. Du legst es einmal in **Netzentgelt des Netzbetreibers** oben im Hauptfenster fest (optional). Wähle dein **Netzgebiet**: Edibert bietet die Katalog-Netzgebiete deines Landes und Bundeslandes an (aus einem importierten Katalogpaket). Passt keines, sagt Edibert das; dann wählst du **Eigene Werte** und trägst die Werte aus dem Preisblatt deines Netzbetreibers ein:

- den **Arbeitspreis** in ct/kWh (netto) und seine Zeitfenster, z. B. den Sommer-Nieder-Arbeitspreis (SNAP) oder die Stufen nach §14a EnWG Modul 3; Zeitfenster ändern nur den Arbeitspreis,
- **weitere Bestandteile je kWh**, z. B. das Netzverlustentgelt,
- **Fixbeträge je Jahr** in EUR pro Jahr, z. B. die Netz-Grundpauschale; sie werden nie auf den Preis je kWh aufgeschlagen.

**Als eigene Werte übernehmen** nimmt ein Katalog-Netzgebiet (oder ein geteiltes Netzgebiet, nachdem du sie eingeschaltet hast) als Ausgangspunkt deiner eigenen Werte; Edibert zeigt dann, ob deine Werte noch dem Datenbankeintrag entsprechen. Die **Messart des Netzanschlusses** (Haus-Einstellungen) wählt die Werte aus: Haushalte haben meist nicht gemessene Leistung. Hat ein Netzgebiet für deine Messart keinen Wert, sagt Edibert das, statt 0 zu verwenden.

Alle Netzpreise sind netto: Bei einem Nettotarif werden sie vor der USt addiert, bei einem Bruttotarif bekommen sie den USt-Satz des Tarifs. Mit **Netzentgelt speichern** bleibt die Wahl erhalten: `house.json` speichert das gewählte Netzgebiet, deine eigenen Werte stehen in `user_grid_fees.json`.

Vor Version 0.1.12 stand die Netz-Grundgebühr in jedem Tarif (Netz-Grundpreis pro Monat) und das eigene Netzentgelt in `house.json`. Beim ersten Start fragt Edibert nach der Migration: Das eigene Netzentgelt wandert nach `user_grid_fees.json`, und die monatliche Netz-Grundgebühr deiner Tarife wird ein Fixbetrag je Jahr deines eigenen Netzgebiets (netto, mal zwölf). Haben deine Tarife unterschiedliche Werte oder nutzt dein Haus ein Katalog-Netzgebiet, hält die Migration an und sagt es dir; trage die Grundgebühr dann selbst in deinen eigenen Werten ein und entferne sie aus den Tarifen.
