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
| `house.json` | house settings (time zone, location, metering, chosen grid area) |
| `user_grid_fees.json` | your own grid values (grid area `user_house`) |

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

The grid operator's fee is the same for every tariff, whatever the supplier. Set it once in **Grid operator's fee** at the top of the main area (optional). Choose your **grid area**: Edibert offers the catalog areas of your country and federal state (from an imported catalog package). If none fits, it says so; then choose **Own values** and enter the figures of your network operator's price sheet:

- the **work price** in ct/kWh (net) and its time windows, for example the summer low price (SNAP) or the levels of section 14a EnWG module 3; time windows change the work price only,
- **further charges per kWh**, for example the grid loss charge,
- **fixed yearly amounts** in EUR per year, for example the grid base fee; they are never added to the price per kWh.

**Copy as own values** takes a catalog area (or a shared grid area, after you switched them on) as the start of your own values; Edibert then says whether your values still match that database entry. The **metering of the grid connection** (house settings) selects the values: households usually have unmetered power. If an area has no value for your metering, Edibert says so instead of using 0.

All grid prices are net: with a net tariff they are added before VAT, with a gross tariff they get the tariff's VAT rate. Click **Save grid fee** to keep the choice: `house.json` stores the chosen area, your own values are in `user_grid_fees.json`.

Before version 0.1.12 the grid base fee was entered in each tariff (grid base fee per month) and the own grid fee lived in `house.json`. On the first start Edibert asks to migrate: the own grid fee moves to `user_grid_fees.json`, and the monthly grid base fee of your tariffs becomes one fixed yearly amount of your own grid area (net, times twelve). If your tariffs carry different values, or your house uses a catalog area, the migration stops and tells you; enter the base fee in your own values yourself and remove it from the tariffs.
