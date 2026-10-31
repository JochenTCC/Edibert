# The tariff editor

Click **New purchase tariff** (price you pay) or **New feed-in tariff** (remuneration you get). The form has four steps. Everything you change is checked at once, and the preview on the right updates.

## Tariff list, catalog and import

The row above the form holds three tools:

- **My tariffs:** your saved tariffs, plus the buttons for a new tariff. Market-price tariffs show their settlement interval (quarter-hourly or hourly).
- **Copy a catalog tariff:** filter by **Country** (starts with the country of the house), **Direction** and **Type**, then copy a tariff as the start of your own. The list is sorted by name; without a direction filter all purchase tariffs come first, then all feed-in tariffs. A catalog tariff offered only in some federal states or cantons is listed only when the house is in one of them; without a federal state / canton in the house settings it is listed too. The list shows the local catalog file; tariffs of the tariff database (shared ones included) get there through a catalog package, see below.
- **Import JSON:** paste or upload tariffs.

**Unsaved changes.** While the open tariff differs from its saved state, the editor shows **Not saved**. A copied catalog tariff counts as not saved until you save it. When you open another tariff, start a new one or copy one, the editor asks first: **Save**, **Discard** or **Cancel**. Leaving the whole page (another page of the host application, closing the browser tab) cannot be caught; save before you go.

## Share with the free catalog

Below the tool row, **Share with the free catalog** lists your saved tariffs. Each one has a checkbox; while it is ticked, the box below it shows exactly what would be sent. Only price data is sent: type, prices, time windows (without their names), fees, VAT, country, supplier and product name, source and last-checked date. Your notes, the conditions text, comments and the tariff's own ID are never sent. A tariff marked **This tariff is personal** is never shared and has no checkbox; neither has a tariff with an error or without a **Country** (the database files every tariff under its country). In both cases the line names the reason.

Whether the tariffs start ticked depends on the program: the stand-alone Edibert ticks them (you leave out what you do not want to share), Earnie leaves them unticked (you choose what to share). **Send selected tariffs** sends the ticked ones. The message afterwards counts accepted, already known and rejected tariffs and names every rejected tariff with the reason the database gave.

A tariff the database accepts (or already has) is linked to its database entry, so the form shows where it came from from then on. If the exchange is switched off (`EDIBERT_EXCHANGE_OFF=1`) or the embedding program does not send, sharing is off: the section says so, and the send button stays disabled. You can still check what would be sent; nothing leaves your computer.

## Catalog package and database status

In the stand-alone editor the sidebar holds **Import catalog package**. A package comes from a file or from the server: **Load newest package of the … tariff database** loads the verified database when an access key is set (`EDIBERT_ACCESS_KEY`), otherwise the free one. A catalog from the verified database is never replaced by a free package; without the key the section says so. Either way the package is checked (signature, content) and the dialog lists what it adds, changes and removes. Monthly rates you entered yourself are never overwritten without asking: decide for each one, then **Import package**. A shared tariff appears in the catalog once a published package contains it.

A tariff copied from a catalog that came from a package shows under its "copied from" line what the tariff database knows about this version: whether it counts as **reliable**, how many installations used it in the last 12 months, and whether a newer version applies from a date on. **Ask the tariff database** asks the server now; if the publisher runs with the status job (see [Publishing](publishing.md)), its last answer is shown without asking. A copy whose prices you changed is a version the database does not know and shows no status.

## Step 1: Base price

- **Name of the tariff** and **Supplier.** The name is required. Your tariff gets an ID like `user_my_tariff`.
- **Country of the tariff.** A new tariff starts with the country of the house; you can change it or leave it at "–". Tariff lists (for example in Earnie) filter by this country.
- **Federal states / cantons.** Fill in only if the tariff is offered in part of the country (for example a regional utility). Empty means the whole country.
- **How is the price formed?**
  - **Fixed price:** one price in ct/kWh.
  - **Market price + markup:** the day-ahead market price plus a percentage and a fixed amount. For feed-in tariffs: market price minus a share and a fixed amount. Choose whether the tariff is settled every quarter hour or hourly (the mean of the four quarter hours).
  - **Monthly prices:** one price per month. For a missing month Edibert takes the same month of the previous year, else the previous month, and shows a warning; if neither exists, the calculation stops. Add new months in time.
- **Prices include VAT** and the **VAT** rate. Market-price tariffs normally state net prices plus VAT.

## Step 2: Time windows

Use this step when the price changes at certain times. Each row is a **time window**:

- **All day**, or **From** and **To** (the end is exclusive; windows may cross midnight, for example 22:00 to 06:00).
- **Days:** leave empty for every day, or pick weekdays and **Holiday**.
- **Months:** leave empty for every month.
- **What changes:** *Price is …* replaces the price, *Surcharge / discount* adds or subtracts ct/kWh, *Discount (%)* reduces it by a percentage.

**The first matching row wins.** Use the arrows to change the order. Example: a night row in front of a weekend row means that on Saturday night the night price applies.

**Quick templates** add the usual rows with a suggested value that you should correct: night tariff, weekend, summer midday window, high/low tariff. For market-price tariffs the rows are surcharges (value 0).

## Step 3: Further costs

Fixed monthly costs: base fee, metering fee, grid base fee, other. Enter them like the prices (net or gross as set in step 1). Leave 0 if there are none.

## Step 4: Advanced

- **Lowest / highest price** (floor and cap). A lowest price of 0 on a feed-in tariff means "never negative".
- **What the tariff requires** (for example a smart meter). Edibert warns when your house does not have it.
- **Public holidays count** like a Sunday (default), like a normal day, or only for rows that name holidays. **Extra days** (for example 24 and 31 December) can count as holidays for this tariff.
- **This tariff is personal** if it has special conditions. Personal tariffs are never shared.
- **Source**, **last checked**, and **conditions the calculation cannot show** (for example "bonus only if the provider controls charging").

## Save

**Save tariff** writes the tariff to `user_tariffs.json`. The button appears when the tariff is valid. Open a saved tariff from **My tariffs** to change it; **Delete this tariff** removes it. When the editor is embedded in another application that still uses the tariff (in a scenario, for example), the editor asks first and says where the tariff is used; it is deleted only with **Delete anyway**.
