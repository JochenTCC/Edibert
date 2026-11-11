# Import and copying

## Copy a catalog tariff or a template

If you started the editor with `--catalog tariffs.json`, the catalog tariffs are listed in the overview (see [The tariff editor](editor.md)). Select one and click **Copy as template**: you get your own editable tariff with a new ID (`user_...`) and the name extended by "(copy)", opened in the edit view and not yet saved. Select several and click **Copy as template** to save all copies at once without opening them. Templates of the tariff database are copied the same way, once loaded. The catalog itself is not changed. Typical use: take a tariff that is almost yours and change the price.

## Import JSON

Open **Import JSON** below the overview tables and paste the tariff JSON or upload a `.json` file. Edibert checks every tariff and tells you what it found:

- *valid:* ready to add.
- *renamed:* your own tariff IDs must start with `user_`, so a different ID is renamed.
- *already exists:* tick **Replace existing** if you want to overwrite it.
- an error message in plain words if something is wrong.

The file can hold one tariff or a document with `import_tariffs` and `export_tariffs`. Click **Add checked tariffs** to store them. Nothing is stored before that.
