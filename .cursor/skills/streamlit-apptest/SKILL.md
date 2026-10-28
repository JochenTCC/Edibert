---
name: streamlit-apptest
description: >-
  Keep the headless Streamlit AppTest tests of the Edibert editor in sync when
  src/edibert/ui/ changes: new or renamed widgets, steps, buttons, visible texts,
  language handling. Use when editing the editor page or tests/test_ui_app.py.
---

# Streamlit AppTest for the editor

The page script is `src/edibert/ui/app.py` (it only calls `main()`); tests live in `tests/test_ui_app.py`.

## Pattern

```python
app = AppTest.from_file(str(APP), default_timeout=60)
app.run()
app.sidebar.button(key="new.import").click().run()
app.text_input(key=widget_key(app, "label")).set_value("My tariff").run()
```

- Environment (`EDIBERT_DATA_DIR`, `EDIBERT_LANG`, `EDIBERT_CATALOG`) is set with `monkeypatch` to a temporary folder; tests never touch real data.
- `widget_key(app, name)` builds `"<ui.ver>.<name>"` like `state.key`. Keys are language independent, so the same test works in `en` and `de`.
- Assert on **behavior** (file written, rows added, error shown) and on a few exact texts per language; do not assert every label.

## Checklist when the UI changes

```
Streamlit AppTest:
- [ ] New widget or button has a stable, language-independent key
- [ ] New visible text uses a catalog key (en + de) and tests/test_i18n_catalogs.py is green
- [ ] A new flow (step, import path, house setting) has at least one AppTest
- [ ] Renamed/removed keys are updated in tests/test_ui_app.py
- [ ] python -m pytest tests/test_ui_app.py -q
```

## Browser tests (`st.data_editor`)

AppTest cannot edit `st.data_editor` tables. The monthly-rate table is covered at model level and in the browser by `tests/test_ui_browser.py` (Playwright, headless Chromium, marker `browser`, left out of the normal run by `addopts`):

```powershell
pip install -e ".[ui,browser]"
python -m playwright install chromium
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -m pytest -m browser tests/test_ui_browser.py -q
```

Each test starts `streamlit run` on a free port with an empty data folder (English). The grid is a canvas: cells are reached by coordinates (35 px rows) and the keyboard (`Enter` opens the cell editor `input.gdg-input`); wait for each rerun (`settle`). Run them when the table, its columns or the editor layout change, and in the quality gate. Not in CI yet.

## Out of scope

Pixel layout and chart details (check those in the browser by hand).
