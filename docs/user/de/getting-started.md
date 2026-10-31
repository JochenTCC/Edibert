<!-- source: docs/user/en/getting-started.md @ 0.1.c -->
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
| `house.json` | Haus-Einstellungen (Zeitzone, Standort, Netzentgelt) |

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

Das Netzentgelt des Netzbetreibers ist für alle Tarife gleich, egal welcher Stromanbieter. Du gibst es einmal in **Netzentgelt des Netzbetreibers** oben im Hauptfenster ein (optional): Basispreis in ct/kWh (netto) und Zeitfenster, z. B. die Hoch- und Niedertarifstufe nach §14a EnWG Modul 3. Es ist ein Nettopreis: Bei einem Nettotarif wird es vor der USt addiert, bei einem Bruttotarif bekommt es den USt-Satz des Tarifs und wird dann addiert. Mit **Netzentgelt speichern** bleibt es erhalten; es steht in `house.json`.

Den festen Jahresbetrag des Netzbetreibers gibst du nicht hier ein, sondern in jedem Tarif unter **Weitere Kosten** (Netz-Grundpreis pro Monat).
