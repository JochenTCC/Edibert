# The tariff editor

Click **New purchase tariff** (price you pay) or **New feed-in tariff** (remuneration you get). The form has four steps. Everything you change is checked at once, and the preview on the right updates.

## Step 1: Base price

- **Name of the tariff** and **Supplier.** The name is required. Your tariff gets an ID like `user_my_tariff`.
- **How is the price formed?**
  - **Fixed price:** one price in ct/kWh.
  - **Market price + markup:** the day-ahead market price plus a percentage and a fixed amount. For feed-in tariffs: market price minus a share and a fixed amount. Choose whether the tariff is settled every quarter hour or hourly (the mean of the four quarter hours).
  - **Monthly prices:** one price per month. A missing month stops the calculation.
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

**Save tariff** writes the tariff to `user_tariffs.json`. The button appears when the tariff is valid. Open a saved tariff from **My tariffs** to change it; **Delete this tariff** removes it.
