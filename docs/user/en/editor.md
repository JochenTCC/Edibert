# The tariff editor

The overview lists your tariffs, the catalog and loaded templates; select tariffs there to open, copy, delete or compare them. Click **New purchase tariff** (price you pay) or **New feed-in tariff** (remuneration you get) to start a tariff in the edit view. The form has four steps. Everything you change is checked at once, and the preview on the right updates.

## Overview and edit view

The page has two views, switched at the top: **Overview** and **Edit**. Next to the switch are **New purchase tariff** and **New feed-in tariff**; both open the form in the edit view. The page starts in the overview.

### The tariff tables

The overview has a tab for **Purchase** and one for **Feed-in**. Each lists every tariff at hand: your own tariffs (origin **Own**), the tariffs of the catalog file (**Catalog**; of a tariff with several validity versions only the one valid today) and, once loaded, templates of the tariff database (**Template**). The tab title counts them.

The parameters are columns: supplier, origin, price kind (fixed price, market price with its settlement interval, monthly prices), base price or remuneration, markups or deductions on the market price, monthly fee and check state. **Show all columns** adds country, regions, number of time rules, lowest and highest price, requirements, validity and last check. Click a column header to sort.

- **Prices** above the tabs puts every price column on one basis: **gross** (default) or **net**. Tariffs store their prices with or without VAT; the table converts them with each tariff's VAT rate. This converts parameters, it is not a cost calculation.
- A market-price tariff has no fixed base price; its cell stays empty and the price kind says it is a market price.
- A monthly table shows the rate of the current month; the month is in the column header. If a tariff has no rate for this month, the cell stays empty and a line below the table names the tariff. No other month is shown in its place.

Filters above each table (each tab keeps its own): **Country** (starts with the country of the house; a tariff without a country is always listed), **Price kind**, **Origin**, a search over label and supplier, and **My region only**. With **My region only**, a tariff offered only in some federal states or cantons is hidden unless the house is in one of them; without a federal state / canton in the house settings nothing is hidden. The filters keep their values while you are in the edit view.

### Select and act

Tick rows in the table to select them. The line below the table names the selected tariffs; a selection the filters hide stays selected and is counted. The actions:

| Action | Selection | What happens |
|---|---|---|
| **Open** | exactly one own tariff | opens it in the edit view |
| **Copy as template** | one catalog tariff or template | opens an unsaved copy with a new ID (`user_...`) and the name extended by "(copy)" in the edit view |
| **Copy as template** | several catalog tariffs or templates | saves the copies as your own tariffs at once; none is opened, a message gives the number |
| **Delete** | one or more own tariffs | deletes them; see [Save](#save) for the question an embedding application can ask |

An action that does not fit the selection is greyed out; hover over it to see why. The comparison is no action: it appears below the table as soon as you select a tariff.

### Compare

The comparison appears below the table whenever one to five tariffs are selected and follows the selection. With one tariff it shows that tariff's parameters and its price curve.

- **Parameters:** the selected tariffs as columns, the parameters as rows, on the same gross or net basis as the table. A row marked **≠** differs between the tariffs; **Differences only** hides the others.
- **Price curve of one day:** one curve per tariff in one chart, for the chosen **month** and **day type** (weekday, Saturday, Sunday, holiday). It is computed like the preview of the form: with the house's country, region and grid fee, and market-price tariffs on an example market curve (a note says so; it is not a forecast). If a tariff has no curve for the chosen day, a message says why: the house has no federal state / canton for the holiday calendar, the month has no holiday, or the tariff has no price that day (for example no monthly rate).
- At most five tariffs are compared. With more selected (for example to copy or delete them), nothing is drawn and a note says so; Edibert never picks five for you.

The comparison shows prices, not costs. A comparison of yearly costs from your meter data is planned separately.

### Templates of the tariff database (unchecked)

Templates are tariffs other users shared that nobody checked yet. Open **Copy a template (unchecked)** below the tables, switch them on with **Show unchecked templates of the tariff database**, choose the country (two letters) and the direction, optionally search a supplier, then **Load templates**. The templates appear in the table of that direction with the origin **Template**; the column **Check state** shows their trust level. You can copy and compare them, not open or delete them. If the database knows a checked version of a template, a note above the actions names it: copy that one from the catalog instead. Switching the templates off removes them from the table. Compare a copied template with your contract or the supplier's price sheet before you rely on it. Needs the tariff database server (not with `EDIBERT_EXCHANGE_OFF=1`).

**Import JSON** below the tables pastes or uploads tariffs, see [Import and copying](import.md).

**Unsaved changes.** While the open tariff differs from its saved state, the editor shows **Not saved**, and the **Edit** switch carries a dot. A copied tariff counts as not saved until you save it. Switching between the views keeps your changes. When you open another tariff, start a new one or copy one, the editor asks first: **Save**, **Discard** or **Cancel**. Leaving the whole page (another page of the host application, closing the browser tab) cannot be caught; save before you go.

## Share with the tariff database

Below the overview, **Share with the tariff database** lists your saved tariffs. Each one has a checkbox; while it is ticked, the box below it shows exactly what would be sent. Only price data is sent: type, prices, time windows (without their names), fees, VAT, country, supplier and product name, source and last-checked date. Your notes, the conditions text, comments and the tariff's own ID are never sent. A tariff marked **This tariff is personal** is never shared and has no checkbox; neither has a tariff with an error or without a **Country** (the database files every tariff under its country). In both cases the line names the reason.

Whether the tariffs start ticked depends on the program: the stand-alone Edibert ticks them (you leave out what you do not want to share), Earnie leaves them unticked (you choose what to share). **Send selected tariffs** sends the ticked ones. The message afterwards counts accepted, already known and rejected tariffs and names every rejected tariff with the reason the database gave.

A tariff the database accepts (or already has) is linked to its database entry, so the form shows where it came from from then on. If the exchange is switched off (`EDIBERT_EXCHANGE_OFF=1`) or the embedding program does not send, sharing is off: the section says so, and the send button stays disabled. You can still check what would be sent; nothing leaves your computer.

## Catalog package and database status

In the stand-alone editor the sidebar holds **Import catalog package**. A package comes from a file or from the server: **Load newest catalog package** loads the catalog of the tariff database; it is free and needs no key and holds only checked tariffs and tariffs released by their supplier. The package is checked (signature, content) and the dialog lists what it adds, changes and removes. Monthly rates you entered yourself are never overwritten without asking: decide for each one, then **Import package**. A shared tariff appears in the catalog only after we checked it and a published package contains it.

A tariff copied from the tariff database (from a catalog that came from a package, or a template) shows under its "copied from" line what the database knows about this version: its **trust level** (released by the supplier, checked, reliable or unchecked), the check date, how many installations used it in the last 12 months, and whether a newer version applies from a date on. **Check overdue** means the last check is older than a quarter plus 30 days. **A checked version of this tariff is available** appears when we checked your copy's version or a newer one. When the database merged the entry into another one (the same tariff shared twice), the editor says so and offers **Link my copy to the merged entry …**; it changes the link only after you confirm, and you save the tariff afterwards. Your prices stay as they are. **Ask the tariff database** asks the server now; if the publisher runs with the status job (see [Publishing](publishing.md)), its last answer is shown without asking. A copy whose prices you changed is a version the database does not know and shows no status.

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

Fixed monthly costs of the supplier: base fee, metering fee, other. The grid base fee is part of the grid fee (see Getting started, Grid fee), not of a tariff. Enter them like the prices (net or gross as set in step 1). Leave 0 if there are none.

## Step 4: Advanced

- **Lowest / highest price** (floor and cap). A lowest price of 0 on a feed-in tariff means "never negative".
- **What the tariff requires** (for example a smart meter). Edibert warns when your house does not have it.
- **Public holidays count** like a Sunday (default), like a normal day, or only for rows that name holidays. **Extra days** (for example 24 and 31 December) can count as holidays for this tariff.
- **This tariff is personal** if it has special conditions. Personal tariffs are never shared.
- **Source**, **last checked**, and **conditions the calculation cannot show** (for example "bonus only if the provider controls charging").

## Save

**Save tariff** writes the tariff to `user_tariffs.json`. The button appears when the tariff is valid. To change a saved tariff, select it in the overview and click **Open**; to remove it, select it and click **Delete**. When the editor is embedded in another application that still uses the tariff (in a scenario, for example), the editor asks first and says where the tariff is used; it is deleted only with **Delete anyway**.
