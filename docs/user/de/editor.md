<!-- source: docs/user/en/editor.md @ 0.1.d -->
# Der Tarif-Editor

Klicke auf **Neuer Bezugstarif** (Preis, den du zahlst) oder **Neuer Einspeisetarif** (Vergütung, die du bekommst). Das Formular hat vier Schritte. Alles, was du änderst, wird sofort geprüft, und die Vorschau rechts aktualisiert sich.

## Tarifliste, Katalog und Import

Die Zeile über dem Formular enthält drei Werkzeuge:

- **Meine Tarife:** deine gespeicherten Tarife und die Knöpfe für einen neuen Tarif. Börsentarife zeigen ihr Abrechnungsintervall (viertelstündlich oder stündlich).
- **Katalogtarif kopieren:** nach **Land** (startet mit dem Land des Hauses), **Richtung** und **Art** filtern, dann einen Tarif als Vorlage für einen eigenen kopieren. Die Liste ist nach Namen sortiert; ohne Richtungsfilter kommen erst alle Bezugstarife, dann alle Einspeisetarife. Ein Katalogtarif, den es nur in einigen Bundesländern oder Kantonen gibt, erscheint nur, wenn das Haus in einem davon liegt; ist in den Hauseinstellungen kein Bundesland / Kanton gesetzt, erscheint er auch. Die Liste zeigt die lokale Katalogdatei; Tarife der Tarifdatenbank (auch geteilte) kommen über ein Katalogpaket dorthin, siehe unten.
- **JSON importieren:** Tarife einfügen oder hochladen.

**Ungespeicherte Änderungen.** Solange der offene Tarif vom gespeicherten Stand abweicht, zeigt der Editor **Nicht gespeichert**. Ein kopierter Katalogtarif gilt als nicht gespeichert, bis du ihn speicherst. Öffnest du einen anderen Tarif, legst einen neuen an oder kopierst einen, fragt der Editor vorher: **Speichern**, **Verwerfen** oder **Abbrechen**. Das Verlassen der ganzen Seite (eine andere Seite der einbettenden Anwendung, Browser-Tab schließen) kann der Editor nicht abfangen; vorher speichern.

## Mit dem freien Katalog teilen

Unter der Werkzeugzeile listet **Mit dem freien Katalog teilen** deine gespeicherten Tarife. Jeder hat ein Kästchen; solange es angehakt ist, zeigt der Kasten darunter genau, was gesendet würde. Gesendet werden nur Preisdaten: Art, Preise, Zeitfenster (ohne ihre Namen), Gebühren, Mehrwertsteuer, Land, Lieferant und Produktname, Quelle und Prüfdatum. Deine Notizen, der Bedingungstext, Kommentare und die eigene ID des Tarifs werden nie gesendet. Ein Tarif mit **Dieser Tarif ist persönlich** wird nie geteilt und hat kein Kästchen; ebenso ein Tarif mit einem Fehler oder ohne **Land** (die Datenbank ordnet jeden Tarif seinem Land zu). In beiden Fällen nennt die Zeile den Grund. <!-- Hinweis einfügen, dass getelte Tarife jedem in der Community helfen - auch dem Nutzer selbst -->

Ob die Tarife zu Beginn angehakt sind, hängt vom Programm ab: Das eigenständige Edibert hakt sie an (du wählst ab, was du nicht teilen willst), Earnie lässt sie leer (du wählst aus, was du teilen willst). **Ausgewählte Tarife senden** sendet die angehakten. Die Meldung danach zählt angenommene, schon bekannte und abgelehnte Tarife und nennt jeden abgelehnten Tarif mit dem Grund, den die Datenbank angegeben hat.

Ein Tarif, den die Datenbank annimmt (oder schon hat), wird mit seinem Datenbank-Eintrag verknüpft; das Formular zeigt danach, woher er stammt. Ist der Austausch abgeschaltet (`EDIBERT_EXCHANGE_OFF=1`) oder sendet das einbettende Programm nicht, ist Teilen aus: Der Abschnitt sagt das, und der Sende-Knopf bleibt gesperrt. Du kannst trotzdem prüfen, was gesendet würde; nichts verlässt deinen Computer.

## Katalogpaket und Datenbankstatus

Im eigenständigen Editor steht in der Seitenleiste **Katalogpaket importieren**. Ein Paket kommt aus einer Datei oder vom Server: **Neuestes Paket der Tarifdatenbank „…“ laden** lädt die geprüfte Datenbank, wenn ein Zugangsschlüssel gesetzt ist (`EDIBERT_ACCESS_KEY`), sonst die freie. Ein Katalog aus der geprüften Datenbank wird nie durch ein freies Paket ersetzt; ohne Schlüssel sagt der Abschnitt das. In beiden Fällen wird das Paket geprüft (Signatur, Inhalt), und der Dialog zeigt, was es hinzufügt, ändert und entfernt. Selbst eingetragene Monatspreise werden nie ohne Rückfrage überschrieben: Entscheide je Monatspreis, dann **Paket importieren**. Ein geteilter Tarif erscheint im Katalog, sobald ein veröffentlichtes Paket ihn enthält.

Ein Tarif, der aus einem Katalog aus einem Paket kopiert wurde, zeigt unter der Zeile „Kopiert aus …“, was die Tarifdatenbank über diese Version weiß: ob sie als **verlässlich** gilt, wie viele Installationen sie in den letzten 12 Monaten verwendet haben und ob ab einem Datum eine neuere Version gilt. **Tarifdatenbank fragen** fragt den Server sofort; läuft der Publisher mit der Status-Aufgabe (siehe [Veröffentlichen](publishing.md)), wird seine letzte Antwort ohne Rückfrage gezeigt. Eine Kopie mit geänderten Preisen ist eine Version, die die Datenbank nicht kennt, und zeigt keinen Status.

## Schritt 1: Basispreis

- **Name des Tarifs** und **Lieferant.** Der Name ist Pflicht. Dein Tarif bekommt eine ID wie `user_mein_tarif`.
- **Land des Tarifs.** Ein neuer Tarif startet mit dem Land des Hauses; du kannst es ändern oder auf „–“ lassen. Tariflisten (etwa in Earnie) filtern nach diesem Land.
- **Bundesländer / Kantone.** Nur ausfüllen, wenn der Tarif nur in einem Teil des Landes angeboten wird (etwa von einem regionalen Versorger). Leer heißt: ganzes Land.
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
- **Dieser Tarif ist persönlich**, wenn er Sonderkonditionen hat, die individuell nur für dich gelten. Persönliche Tarife werden nie geteilt.
- **Quelle**, **zuletzt geprüft** und **Bedingungen, die die Berechnung nicht abbilden kann** (z. B. „Bonus nur, wenn der Anbieter das Laden steuert“).

## Speichern

**Tarif speichern** schreibt den Tarif in `user_tariffs.json`. Der Knopf erscheint, sobald der Tarif gültig ist. Einen gespeicherten Tarif öffnest du unter **Meine Tarife**; **Diesen Tarif löschen** entfernt ihn. Ist der Editor in eine andere Anwendung eingebettet und nutzt diese den Tarif noch (zum Beispiel in einem Szenario), fragt der Editor vorher nach und nennt, wo der Tarif verwendet wird; gelöscht wird erst mit **Trotzdem löschen**.
