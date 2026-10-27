<!-- source: docs/user/en/editor.md @ 0.1.c -->
# Der Tarif-Editor

Klicke auf **Neuer Bezugstarif** (Preis, den du zahlst) oder **Neuer Einspeisetarif** (Vergütung, die du bekommst). Das Formular hat vier Schritte. Alles, was du änderst, wird sofort geprüft, und die Vorschau rechts aktualisiert sich.

## Schritt 1: Basispreis

- **Name des Tarifs** und **Lieferant.** Der Name ist Pflicht. Dein Tarif bekommt eine ID wie `user_mein_tarif`.
- **Land des Tarifs.** Ein neuer Tarif startet mit dem Land des Hauses; du kannst es ändern oder auf „–“ lassen. Tariflisten (etwa in Earnie) filtern nach diesem Land.
- **Wie wird der Preis gebildet?**
  - **Festpreis:** ein Preis in ct/kWh.
  - **Börsenpreis + Aufschlag:** der Day-Ahead-Börsenpreis plus ein Prozentsatz und ein fester Betrag. Bei Einspeisetarifen: Börsenpreis minus ein Anteil und ein fester Betrag. Du wählst, ob viertelstündlich oder stündlich abgerechnet wird (Mittel der vier Viertelstunden).
  - **Monatspreise:** ein Preis je Monat. Fehlt ein Monat, nimmt Edibert denselben Monat des Vorjahres, sonst den Vormonat, und zeigt eine Warnung; gibt es keinen von beiden, bricht die Berechnung ab. Neue Monate rechtzeitig eintragen.
- **Preise enthalten USt** und der **USt**-Satz. Börsentarife nennen normalerweise Nettopreise zuzüglich USt.

## Schritt 2: Zeitfenster

Nutze diesen Schritt, wenn sich der Preis zu bestimmten Zeiten ändert. Jede Zeile ist ein **Zeitfenster**:

- **Ganztägig**, oder **Von** und **Bis** (das Ende zählt nicht mehr dazu; Fenster dürfen über Mitternacht gehen, z. B. 22:00 bis 06:00).
- **Tage:** leer lassen für jeden Tag, oder Wochentage und **Feiertag** wählen.
- **Monate:** leer lassen für jeden Monat.
- **Was ändert sich:** *Preis beträgt …* ersetzt den Preis, *Auf-/Abschlag* addiert oder subtrahiert ct/kWh, *Rabatt (%)* senkt ihn um einen Prozentsatz.

**Die erste passende Zeile gilt.** Mit den Pfeilen änderst du die Reihenfolge. Beispiel: Steht eine Nachtzeile vor einer Wochenendzeile, gilt am Samstagabend der Nachtpreis.

**Schnellvorlagen** fügen die üblichen Zeilen mit einem Vorschlagswert ein, den du korrigieren solltest: Nachttarif, Wochenende, Sommer-Mittagsfenster, Hoch-/Niedertarif. Bei Börsentarifen sind die Zeilen Aufschläge (Wert 0).

## Schritt 3: Weitere Kosten

Feste Monatskosten: Grundpreis, Messentgelt, Netz-Grundpreis, Sonstiges. Gib sie so ein wie die Preise (netto oder brutto wie in Schritt 1). 0 lassen, wenn es keine gibt.

## Schritt 4: Erweitert

- **Niedrigster / höchster Preis** (Boden und Deckel). Ein niedrigster Preis von 0 bei einem Einspeisetarif heißt „nie negativ“.
- **Voraussetzungen des Tarifs** (z. B. ein Smart Meter). Edibert warnt, wenn dein Haus das nicht hat.
- **Feiertage zählen** wie ein Sonntag (Standard), wie ein normaler Tag oder nur für Zeilen, die Feiertage nennen. **Zusätzliche Tage** (z. B. 24. und 31. Dezember) können für diesen Tarif als Feiertag zählen.
- **Dieser Tarif ist persönlich**, wenn er Sonderkonditionen hat. Persönliche Tarife werden nie geteilt.
- **Quelle**, **zuletzt geprüft** und **Bedingungen, die die Berechnung nicht abbilden kann** (z. B. „Bonus nur, wenn der Anbieter das Laden steuert“).

## Speichern

**Tarif speichern** schreibt den Tarif in `user_tariffs.json`. Der Knopf erscheint, sobald der Tarif gültig ist. Einen gespeicherten Tarif öffnest du unter **Meine Tarife**; **Diesen Tarif löschen** entfernt ihn. Ist der Editor in eine andere Anwendung eingebettet und nutzt diese den Tarif noch (zum Beispiel in einem Szenario), fragt der Editor vorher nach und nennt, wo der Tarif verwendet wird; gelöscht wird erst mit **Trotzdem löschen**.
