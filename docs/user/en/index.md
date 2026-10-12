# Edbert user manual

Edbert describes your electricity tariff once and calculates the price of every quarter hour from it. This manual covers the **tariff editor** (the browser page), publishing over MQTT and the command line. The English pages are authoritative; a German translation is in `docs/user/de/`.

**Status:** draft. The editor and the MQTT publisher work; a native Home Assistant integration is not available yet.

Chapters:

1. [Getting started](getting-started.md): install, start the editor, language
2. [The tariff editor](editor.md): the four steps, preview, saving
3. [Checking a tariff](checking.md): price curve, price at a time, invoice check, hints
4. [Import and copying](import.md): copy a catalog tariff, import JSON
5. [Command line](cli.md): price of a slot, price series, schema
6. [Publishing over MQTT](publishing.md): topics, market prices, optional forecast
