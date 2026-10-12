# Edbert

[English](README.md) · **Deutsch** · *Die englische Fassung ist maßgeblich.*

**Edbert** ist ein Tarif-Editor und Preisdienst für Smart-Home-Systeme. Du beschreibst deinen Stromtarif einmal (fest, börsengebunden oder zeitvariabel mit Fenstern, Wochentagen, Feiertagen) und Edbert liefert die daraus berechneten Preise als Zeitreihe an dein Smart-Home-Backend: als Home-Assistant-Sensor oder per MQTT.

> **Status: Entwurf.** Dieses Repository enthält bisher Konzept, Formatbeschreibung und Beispiele. Es gibt noch keinen lauffähigen Code. Siehe [Roadmap](#roadmap).

## Wozu?

Viele Tarife lassen sich nicht in einem Feld „ct/kWh“ beschreiben:

- Nachttarife und Wochenendpreise (HT/NT), Sommer-Mittagsfenster
- Börsenpreis mit Aufschlägen, Deckel und Boden
- zeitvariable Netzentgelte (§14a Modul 3: Hoch-, Standard- und Niedertarif)
- Einspeisung mit „keine Vergütung bei negativem Preis“
- Feiertage, die wie ein Sonntag zählen

Edbert bildet das mit wenigen Bausteinen ab, **ohne dass du JSON von Hand schreiben musst**, und zeigt dir den Preisverlauf sofort an, bevor du ihn verwendest.

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

Nicht Ziel: Tarife vergleichen oder vermitteln, Rechnungen erstellen, Geräte steuern. Edbert liefert nur Preise.

## Verhältnis zu Earnie

Edbert ist ein eigenständiges Werkzeug und wird auch von [Earnie](https://github.com/JochenTCC/Earnie) genutzt, einem Optimierer für Heimspeicher, PV und Verbraucher. Du brauchst Earnie nicht, um Edbert zu verwenden.

## Katalog und Beiträge

Edbert hat einen gepflegten Katalog von Tarifen (DE/AT/CH). Du kannst jederzeit eigene Tarife anlegen. Der Zugang zum **Community-Katalog und seinen Updates** gilt für Nutzer,

- die selbst einen Tarif beigetragen haben (zeitlich begrenzt), oder
- die einmalig eine kleine Gebühr zahlen.

Später ist ein Jahresabo für automatische Katalog-Updates geplant. Die Software selbst funktioniert immer, auch ohne Katalogzugang.

Gesammelt werden nur Tarife, die **nicht auf eine Person zugeschnitten** sind, und nur **ohne Personenbezug** (keine Postleitzahl, kein Name, keine Zählernummer, keine Freitexte, keine Verbrauchsdaten). Der Upload erfolgt freiwillig, mit Vorschau des genauen Inhalts. Das ist die geplante Funktionsweise, noch kein verbindliches Angebot. Details: [CONTRIBUTING.md](CONTRIBUTING.md) (englisch) und [catalog/README.md](catalog/README.md) (englisch).

## Lizenz

Der Code steht unter der [PolyForm Noncommercial License 1.0.0](LICENSE): Quellcode einsehbar, Nutzung für private, wissenschaftliche, gemeinnützige und andere **nicht-kommerzielle** Zwecke erlaubt, gewerbliche Nutzung nur mit gesonderter Lizenz. Das ist keine Open-Source-Lizenz im Sinne der OSI („Source-Available“).

[LICENSE](LICENSE) und [NOTICE](NOTICE) gelten für den Code. Für den Tarifkatalog und für Tarifbeiträge gelten **gesonderte Bedingungen** sowie eine Datenschutzerklärung. Diese rechtlichen Texte werden **je Land in der Landessprache** verfasst (Deutschland und Österreich: Deutsch, Schweiz: Deutsch) und **erst nach rechtlicher Prüfung** hier veröffentlicht; bis dahin gibt es weder Katalogzugang noch Upload.

## Roadmap

| Schritt | Inhalt |
|---|---|
| T1 | Regel-Engine, Tariffelder, `user_tariffs.json`, Feiertage, Mehrsprachigkeit (Grundlage) |
| T2 | Netzentgelt-Regeln und `tariff_price_series` (die eine Schnittstelle zur Preisreihe) |
| T3 | Editor und Import (Vorlage, JSON-Datei) |
| T4 | Beitragsweg und signierter Katalogzugang |
| später | Preisblatt-Assistent, Ausgabe für evcc/EMHASS/Predbat, Preise je Zähler |

Das Format ist in [docs/spec/tariff-format.md](docs/spec/tariff-format.md) (englisch) beschrieben, Beispiele liegen unter [examples/](examples/). Bedienungsanleitungen: [docs/user/de/](docs/user/de/).
