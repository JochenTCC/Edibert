# Getting started

## Install

Edibert needs Python 3.11 or newer.

```bash
pip install -e ".[ui]"
```

`[ui]` adds Streamlit, which draws the editor. Without it the command line still works.

## Start the editor

```bash
python -m edibert ui --data-dir edibert_data
```

Then open `http://localhost:8501` in your browser. Add `--lang de` before `ui` to start in German, `--port 8601` to use another port, and `--catalog tariffs.json` if you want to copy tariffs from a catalog file.

```bash
python -m edibert --lang de ui --data-dir edibert_data --catalog tariffs.json
```

## Where your data is stored

Everything stays on your computer in the data folder (default `edibert_data`):

| File | Content |
|---|---|
| `user_tariffs.json` | your tariffs |
| `house.json` | house settings (time zone, location, grid fee) |

Nothing is sent anywhere. There is no upload yet.

## Language

The sidebar has a **Language** selector (English or German). Your entries are kept when you switch.

## House settings

Open **House settings** in the sidebar once, before you rely on the preview:

- **Time zone** (for example `Europe/Vienna`). All times are local time of the house.
- **Country** and **federal state / canton.** The region is needed as soon as a tariff has rules for certain days, because public holidays can change the price. Without a region Edibert stops with a clear message instead of guessing.
- **What the house has**: smart meter, quarter-hour meter, separate meter, controllable device. A tariff that needs something the house does not have gets a hint.

Click **Save house settings** to keep them.

## Grid fee

The grid operator's fee is the same for every tariff, whatever the supplier. Enter it once in **Grid operator's fee** at the top of the main area (optional): base price in ct/kWh (net) and time windows, for example the high and low level of section 14a EnWG module 3. It is a net price: with a net tariff it is added before VAT, with a gross tariff it gets the tariff's VAT rate and is then added. Click **Save grid fee** to keep it; it is stored in `house.json`.

The grid operator's fixed yearly charge is not entered here but in each tariff under **Further costs** (grid base fee per month).
