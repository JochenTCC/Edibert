# Import and copying

## Copy a catalog tariff

If you started the editor with `--catalog tariffs.json`, open **Copy a catalog tariff** in the sidebar, pick a tariff and click **Copy as template**. You get your own editable tariff with a new ID (`user_...`) and the name extended by "(copy)". The catalog itself is not changed. Typical use: take a tariff that is almost yours and change the price.

## Import JSON

Open **Import JSON** in the sidebar and paste the tariff JSON or upload a `.json` file. Edibert checks every tariff and tells you what it found:

- *valid:* ready to add.
- *renamed:* your own tariff IDs must start with `user_`, so a different ID is renamed.
- *already exists:* tick **Replace existing** if you want to overwrite it.
- an error message in plain words if something is wrong.

The file can hold one tariff or a document with `import_tariffs` and `export_tariffs`. Click **Add checked tariffs** to store them. Nothing is stored before that.
