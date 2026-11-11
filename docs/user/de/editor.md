<!-- source: docs/user/en/editor.md @ 0.1.c2 -->
# Der Tarif-Editor

Die Übersicht listet deine Tarife, den Katalog und geladene Vorlagen; dort wählst du Tarife aus, um sie zu öffnen, zu kopieren, zu löschen oder zu vergleichen. Klicke auf **Neuer Bezugstarif** (Preis, den du zahlst) oder **Neuer Einspeisetarif** (Vergütung, die du bekommst), um einen Tarif in der Ansicht Bearbeiten anzulegen. Das Formular hat vier Schritte. Alles, was du änderst, wird sofort geprüft, und die Vorschau rechts aktualisiert sich.

## Übersicht und Bearbeiten

Die Seite hat zwei Ansichten, oben umschaltbar: **Übersicht** und **Bearbeiten**. Daneben stehen **Neuer Bezugstarif** und **Neuer Einspeisetarif**; beide öffnen das Formular in der Ansicht Bearbeiten. Die Seite startet in der Übersicht.

### Die Tariftabellen

Die Übersicht hat einen Reiter **Bezug** und einen Reiter **Einspeisung**. Jeder listet alle vorhandenen Tarife: deine eigenen (Herkunft **Eigener**), die Tarife der Katalogdatei (**Katalog**; von einem Tarif mit mehreren Gültigkeitsversionen nur die heute gültige) und, sobald geladen, Vorlagen der Tarifdatenbank (**Vorlage**). Der Reitertitel zählt sie.

Die Parameter stehen als Spalten: Anbieter, Herkunft, Preisart (Festpreis, Börsenpreis mit Abrechnungsintervall, Monatspreise), Basispreis bzw. Vergütung, Auf- oder Abschläge auf den Börsenpreis, Grundgebühr und Prüfstatus. **Alle Spalten zeigen** ergänzt Land, Regionen, Anzahl der Zeitregeln, Unter- und Obergrenze, Voraussetzungen, Gültigkeit und letzte Prüfung. Ein Klick auf den Spaltenkopf sortiert.

- **Preise** über den Reitern rechnet alle Preisspalten auf eine Basis um: **brutto** (Standard) oder **netto**. Tarife speichern ihre Preise mit oder ohne Mehrwertsteuer; die Tabelle rechnet mit dem Steuersatz des jeweiligen Tarifs um. Das ist eine Umrechnung der Parameter, keine Kostenrechnung.
- Ein Börsentarif hat keinen festen Basispreis; die Zelle bleibt leer, die Preisart sagt, dass es ein Börsenpreis ist.
- Eine Monatstabelle zeigt den Wert des laufenden Monats; der Monat steht im Spaltenkopf. Fehlt einem Tarif der Wert für diesen Monat, bleibt die Zelle leer und eine Zeile unter der Tabelle nennt den Tarif. Ein anderer Monat wird nicht ersatzweise gezeigt.

Filter über jeder Tabelle (jeder Reiter hat seine eigenen): **Land** (startet mit dem Land des Hauses; ein Tarif ohne Land erscheint immer), **Preisart**, **Herkunft**, eine Suche in Bezeichnung und Anbieter und **Nur meine Region**. Mit **Nur meine Region** wird ein Tarif, den es nur in einigen Bundesländern oder Kantonen gibt, ausgeblendet, wenn das Haus in keinem davon liegt; ist in den Hauseinstellungen kein Bundesland / Kanton gesetzt, wird nichts ausgeblendet. Die Filter behalten ihre Werte, während du in der Ansicht Bearbeiten bist.

### Auswählen und handeln

Hake Zeilen in der Tabelle an, um sie auszuwählen. Die Zeile unter der Tabelle nennt die ausgewählten Tarife; eine Auswahl, die die Filter ausblenden, bleibt ausgewählt und wird mitgezählt. Die Aktionen:

| Aktion | Auswahl | Was passiert |
|---|---|---|
| **Öffnen** | genau ein eigener Tarif | öffnet ihn in der Ansicht Bearbeiten |
| **Als Vorlage kopieren** | ein Katalogtarif oder eine Vorlage | öffnet eine ungespeicherte Kopie mit neuer ID (`user_...`) und dem Namen um „(Kopie)“ ergänzt in der Ansicht Bearbeiten |
| **Als Vorlage kopieren** | mehrere Katalogtarife oder Vorlagen | speichert die Kopien sofort als eigene Tarife; keine wird geöffnet, eine Meldung nennt die Anzahl |
| **Löschen** | ein oder mehrere eigene Tarife | löscht sie; zur Rückfrage einer einbettenden Anwendung siehe [Speichern](#speichern) |

Eine Aktion, die nicht zur Auswahl passt, ist ausgegraut; fährst du mit der Maus darüber, steht dort warum. Der Vergleich ist keine Aktion: Er erscheint unter der Tabelle, sobald du einen Tarif auswählst.

### Vergleichen

Der Vergleich erscheint unter der Tabelle, sobald ein bis drei Tarife ausgewählt sind, und folgt der Auswahl. Bei einem Tarif zeigt er dessen Parameter und seine Preiskurve.

- **Parameter:** die ausgewählten Tarife als Spalten, die Parameter als Zeilen, auf derselben Brutto- oder Netto-Basis wie die Tabelle. Eine mit **≠** markierte Zeile unterscheidet sich zwischen den Tarifen; **Nur Unterschiede** blendet die anderen aus.
- **Preiskurve eines Tages:** eine Kurve je Tarif in einem Diagramm, für den gewählten **Monat** und die **Tagesart** (Werktag, Samstag, Sonntag, Feiertag). Gerechnet wird wie in der Vorschau des Formulars: mit Land, Region und Netzentgelt des Hauses, Börsentarife mit einer Beispiel-Börsenkurve (ein Hinweis sagt das; es ist keine Prognose). Hat ein Tarif für den gewählten Tag keine Kurve, sagt eine Meldung warum: beim Haus fehlt das Bundesland / der Kanton für den Feiertagskalender, im Monat gibt es keinen Feiertag oder der Tarif hat an dem Tag keinen Preis (zum Beispiel keinen Monatswert).
- Verglichen werden höchstens drei Tarife. Sind mehr ausgewählt (etwa zum Kopieren oder Löschen), wird nichts gezeichnet und ein Hinweis sagt das; Edibert wählt nie selbst drei aus.

Der Vergleich zeigt Preise, keine Kosten. Ein Vergleich der Jahreskosten aus deinen Zählerdaten ist getrennt geplant.

### Vorlagen der Tarifdatenbank (ungeprüft)

Vorlagen sind Tarife, die andere Nutzer geteilt haben und die noch niemand geprüft hat. Öffne unter den Tabellen **Vorlage kopieren (ungeprüft)**, schalte sie mit **Ungeprüfte Vorlagen der Tarifdatenbank anzeigen** ein, wähle das Land (zwei Buchstaben) und die Richtung, suche optional einen Anbieter, dann **Vorlagen laden**. Die Vorlagen erscheinen in der Tabelle dieser Richtung mit der Herkunft **Vorlage**; die Spalte **Prüfstatus** zeigt ihre Vertrauensstufe. Du kannst sie kopieren und vergleichen, nicht öffnen oder löschen. Kennt die Datenbank eine geprüfte Version einer Vorlage, nennt ein Hinweis über den Aktionen sie: kopiere dann besser diese aus dem Katalog. Schaltest du die Vorlagen aus, verschwinden sie aus der Tabelle. Vergleiche eine kopierte Vorlage mit deinem Vertrag oder dem Preisblatt des Anbieters, bevor du dich darauf verlässt. Braucht den Server der Tarifdatenbank (nicht mit `EDIBERT_EXCHANGE_OFF=1`).

**JSON importieren** unter den Tabellen fügt Tarife ein oder lädt sie hoch, siehe [Import und Kopieren](import.md).

**Ungespeicherte Änderungen.** Solange der offene Tarif vom gespeicherten Stand abweicht, zeigt der Editor **Nicht gespeichert**, und der Umschalter **Bearbeiten** trägt einen Punkt. Ein kopierter Tarif gilt als nicht gespeichert, bis du ihn speicherst. Der Wechsel zwischen den Ansichten behält deine Änderungen. Öffnest du einen anderen Tarif, legst einen neuen an oder kopierst einen, fragt der Editor vorher: **Speichern**, **Verwerfen** oder **Abbrechen**. Das Verlassen der ganzen Seite (eine andere Seite der einbettenden Anwendung, Browser-Tab schließen) kann der Editor nicht abfangen; vorher speichern.

## Mit der Tarifdatenbank teilen

Unter der Übersicht listet **Mit der Tarifdatenbank teilen** deine gespeicherten Tarife. Jeder hat ein Kästchen; solange es angehakt ist, zeigt der Kasten darunter genau, was gesendet würde. Gesendet werden nur Preisdaten: Art, Preise, Zeitfenster (ohne ihre Namen), Gebühren, Mehrwertsteuer, Land, Lieferant und Produktname, Quelle und Prüfdatum. Deine Notizen, der Bedingungstext, Kommentare und die eigene ID des Tarifs werden nie gesendet. Ein Tarif mit **Dieser Tarif ist persönlich** wird nie geteilt und hat kein Kästchen; ebenso ein Tarif mit einem Fehler oder ohne **Land** (die Datenbank ordnet jeden Tarif seinem Land zu). In beiden Fällen nennt die Zeile den Grund. <!-- Hinweis einfügen, dass getelte Tarife jedem in der Community helfen - auch dem Nutzer selbst -->

Ob die Tarife zu Beginn angehakt sind, hängt vom Programm ab: Das eigenständige Edibert hakt sie an (du wählst ab, was du nicht teilen willst), Earnie lässt sie leer (du wählst aus, was du teilen willst). **Ausgewählte Tarife senden** sendet die angehakten. Die Meldung danach zählt angenommene, schon bekannte und abgelehnte Tarife und nennt jeden abgelehnten Tarif mit dem Grund, den die Datenbank angegeben hat.

Ein Tarif, den die Datenbank annimmt (oder schon hat), wird mit seinem Datenbank-Eintrag verknüpft; das Formular zeigt danach, woher er stammt. Ist der Austausch abgeschaltet (`EDIBERT_EXCHANGE_OFF=1`) oder sendet das einbettende Programm nicht, ist Teilen aus: Der Abschnitt sagt das, und der Sende-Knopf bleibt gesperrt. Du kannst trotzdem prüfen, was gesendet würde; nichts verlässt deinen Computer.

## Katalogpaket und Datenbankstatus

Im eigenständigen Editor steht in der Seitenleiste **Katalogpaket importieren**. Ein Paket kommt aus einer Datei oder vom Server: **Neuestes Katalogpaket laden** lädt den Katalog der Tarifdatenbank; er ist kostenlos, braucht keinen Schlüssel und enthält nur geprüfte und vom Anbieter freigegebene Tarife. Das Paket wird geprüft (Signatur, Inhalt), und der Dialog zeigt, was es hinzufügt, ändert und entfernt. Selbst eingetragene Monatspreise werden nie ohne Rückfrage überschrieben: Entscheide je Monatspreis, dann **Paket importieren**. Ein geteilter Tarif erscheint im Katalog erst, wenn wir ihn geprüft haben und ein veröffentlichtes Paket ihn enthält.

Ein Tarif, der aus der Tarifdatenbank kopiert wurde (aus einem Katalog aus einem Paket oder als Vorlage), zeigt unter der Zeile „Kopiert aus …“, was die Datenbank über diese Version weiß: ihre **Vertrauensstufe** (vom Anbieter freigegeben, geprüft, verlässlich oder ungeprüft), das Prüfdatum, wie viele Installationen sie in den letzten 12 Monaten verwendet haben und ob ab einem Datum eine neuere Version gilt. **Prüfung überfällig** heißt: Die letzte Prüfung ist älter als ein Quartal plus 30 Tage. **Eine geprüfte Version dieses Tarifs ist verfügbar** erscheint, wenn wir die Version deiner Kopie oder eine neuere geprüft haben. Hat die Datenbank den Eintrag mit einem anderen zusammengeführt (derselbe Tarif zweimal geteilt), sagt der Editor das und bietet **Meine Kopie mit dem zusammengeführten Eintrag verknüpfen …** an; er ändert die Verknüpfung erst nach deiner Bestätigung, danach speicherst du den Tarif. Deine Preise bleiben, wie sie sind. **Tarifdatenbank fragen** fragt den Server sofort; läuft der Publisher mit der Status-Aufgabe (siehe [Veröffentlichen](publishing.md)), wird seine letzte Antwort ohne Rückfrage gezeigt. Eine Kopie mit geänderten Preisen ist eine Version, die die Datenbank nicht kennt, und zeigt keinen Status.

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

Feste Monatskosten des Stromanbieters: Grundpreis, Messentgelt, Sonstiges. Die Netz-Grundgebühr gehört zum Netzentgelt (siehe Erste Schritte, Netzentgelt), nicht zu einem Tarif. Gib sie so ein wie die Preise (netto oder brutto wie in Schritt 1). 0 lassen, wenn es keine gibt.

## Schritt 4: Erweitert

- **Niedrigster / höchster Preis** (Boden und Deckel). Ein niedrigster Preis von 0 bei einem Einspeisetarif heißt „nie negativ“.
- **Voraussetzungen des Tarifs** (z. B. ein Smart Meter). Edibert warnt, wenn dein Haus das nicht hat.
- **Feiertage zählen** wie ein Sonntag (Standard), wie ein normaler Tag oder nur für Zeilen, die Feiertage nennen. **Zusätzliche Tage** (z. B. 24. und 31. Dezember) können für diesen Tarif als Feiertag zählen.
- **Dieser Tarif ist persönlich**, wenn er Sonderkonditionen hat, die individuell nur für dich gelten. Persönliche Tarife werden nie geteilt.
- **Quelle**, **zuletzt geprüft** und **Bedingungen, die die Berechnung nicht abbilden kann** (z. B. „Bonus nur, wenn der Anbieter das Laden steuert“).

## Speichern

**Tarif speichern** schreibt den Tarif in `user_tariffs.json`. Der Knopf erscheint, sobald der Tarif gültig ist. Einen gespeicherten Tarif wählst du in der Übersicht aus und klickst **Öffnen**, um ihn zu ändern; **Löschen** entfernt ihn. Ist der Editor in eine andere Anwendung eingebettet und nutzt diese den Tarif noch (zum Beispiel in einem Szenario), fragt der Editor vorher nach und nennt, wo der Tarif verwendet wird; gelöscht wird erst mit **Trotzdem löschen**.
