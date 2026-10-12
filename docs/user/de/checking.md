<!-- source: docs/user/en/checking.md @ 0.1.c -->
# Einen Tarif prüfen

Die rechte Hälfte des Editors zeigt, was dein Tarif tut.

## Fehler und Hinweise

- **Rote Meldung:** das erste Problem, das Edbert gefunden hat, in einfachen Worten. Der Tarif lässt sich erst speichern, wenn es behoben ist.
- **Gelbe Hinweise** halten dich nicht auf:
  - *Ein Zeitfenster greift nie:* eine frühere Zeile trifft zuerst zu. Nach oben schieben oder das Fenster ändern.
  - *Ein Zeitfenster trifft nie zu:* Monate, Tage und Gültigkeit prüfen.
  - *Ungewöhnlicher Preis:* Einheit (Cent, nicht Euro) und netto/brutto prüfen.
  - *Börsentarif mit Bruttopreisen.*
  - *Der Tarif setzt etwas voraus, das dem Haus fehlt.*
  - *Ein Fenster beginnt oder endet nicht zur vollen Stunde* bei einem stündlich abgerechneten Tarif.

## Preisverlauf

Das Diagramm zeigt den Preis je Stunde für einen typischen Werktag, Samstag, Sonntag und, wenn eine Region eingestellt ist, einen Feiertag des gewählten Monats. Bei Börsentarifen nutzt das Diagramm eine **Beispiel-Preiskurve**. Sie ist ausgedacht, um die Form zu zeigen, und keine Prognose.

## Preis zu einem Zeitpunkt

Wähle Datum und Uhrzeit. Edbert zeigt Basispreis, angewendete Regel, Netzentgelt und Endpreis, genau wie die Berechnung.

## Mit einer Rechnung prüfen

1. **Mit einer Rechnung prüfen** öffnen und den Monat wählen.
2. Die kWh dieses Monats je Preisband (Basispreis und jedes Zeitfenster) eintragen, dazu den Rechnungsbetrag inklusive USt. Bei Börsentarifen außerdem den durchschnittlichen Börsenpreis des Monats.
3. Edbert rechnet den Betrag mit deinem Tarif nach, addiert die festen Monatskosten und zeigt die Abweichung.

Eine Abweichung bis 2 % ist normal (Rundung). Eine größere heißt meist: netto/brutto vertauscht, ein Zeitfenster vergessen, eine Gebühr oder das Netzentgelt fehlt.
