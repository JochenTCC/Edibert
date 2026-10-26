<!-- source: docs/user/en/import.md @ 0.1.c -->
# Import und Kopieren

## Einen Katalogtarif kopieren

Wenn du den Editor mit `--catalog tariffs.json` gestartet hast, öffne in der Seitenleiste **Katalogtarif kopieren**, wähle einen Tarif und klicke auf **Als Vorlage kopieren**. Du erhältst einen eigenen, änderbaren Tarif mit neuer ID (`user_...`) und dem Namen um „(Kopie)“ ergänzt. Der Katalog selbst bleibt unverändert. Typisch: einen Tarif nehmen, der fast deiner ist, und den Preis ändern.

## JSON importieren

Öffne in der Seitenleiste **JSON importieren** und füge das Tarif-JSON ein oder lade eine `.json`-Datei hoch. Edibert prüft jeden Tarif und sagt dir, was es gefunden hat:

- *gültig:* bereit zum Hinzufügen.
- *umbenannt:* eigene Tarif-IDs müssen mit `user_` beginnen, eine andere ID wird deshalb umbenannt.
- *existiert bereits:* **Vorhandenen Tarif ersetzen** anhaken, wenn du ihn überschreiben willst.
- eine Fehlermeldung in einfachen Worten, wenn etwas nicht stimmt.

Die Datei kann einen Tarif enthalten oder ein Dokument mit `import_tariffs` und `export_tariffs`. Mit **Geprüfte Tarife hinzufügen** werden sie gespeichert. Vorher wird nichts gespeichert.
