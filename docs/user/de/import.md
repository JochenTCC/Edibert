<!-- source: docs/user/en/import.md @ 0.1.c2 -->
# Import und Kopieren

## Einen Katalogtarif oder eine Vorlage kopieren

Wenn du den Editor mit `--catalog tariffs.json` gestartet hast, stehen die Katalogtarife in der Übersicht (siehe [Der Tarif-Editor](editor.md)). Wähle einen aus und klicke auf **Als Vorlage kopieren**: Du erhältst einen eigenen, änderbaren Tarif mit neuer ID (`user_...`) und dem Namen um „(Kopie)“ ergänzt, geöffnet in der Ansicht Bearbeiten und noch nicht gespeichert. Wählst du mehrere aus und klickst **Als Vorlage kopieren**, werden alle Kopien sofort gespeichert, ohne sie zu öffnen. Vorlagen der Tarifdatenbank kopierst du genauso, sobald sie geladen sind. Der Katalog selbst bleibt unverändert. Typisch: einen Tarif nehmen, der fast deiner ist, und den Preis ändern.

## JSON importieren

Öffne unter den Tabellen der Übersicht **JSON importieren** und füge das Tarif-JSON ein oder lade eine `.json`-Datei hoch. Edibert prüft jeden Tarif und sagt dir, was es gefunden hat:

- *gültig:* bereit zum Hinzufügen.
- *umbenannt:* eigene Tarif-IDs müssen mit `user_` beginnen, eine andere ID wird deshalb umbenannt.
- *existiert bereits:* **Vorhandenen Tarif ersetzen** anhaken, wenn du ihn überschreiben willst.
- eine Fehlermeldung in einfachen Worten, wenn etwas nicht stimmt.

Die Datei kann einen Tarif enthalten oder ein Dokument mit `import_tariffs` und `export_tariffs`. Mit **Geprüfte Tarife hinzufügen** werden sie gespeichert. Vorher wird nichts gespeichert.
