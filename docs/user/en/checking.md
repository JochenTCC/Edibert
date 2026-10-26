# Checking a tariff

The right half of the editor shows what your tariff does.

## Errors and hints

- **Red message:** the first problem Edibert found, in plain words. The tariff cannot be saved until it is fixed.
- **Yellow hints** do not stop you:
  - *A time window never takes effect:* an earlier row matches first. Move it up or change its window.
  - *A time window never applies:* check months, days and validity.
  - *Unusual price:* check the unit (cent, not euro) and net/gross.
  - *Market-price tariff with gross prices.*
  - *The tariff requires something the house does not have.*
  - *A window does not start and end on a full hour* in a tariff settled hourly.

## Price curve

The chart shows the price per hour for a typical weekday, Saturday, Sunday and, if a region is set, a public holiday of the chosen month. For market-price tariffs the chart uses an **example market curve**. It is made up to show the shape and is not a forecast.

## Price at a given time

Pick a date and time. Edibert shows the base price, the rule that applied, the grid fee and the final price, exactly as the calculation does.

## Check against an invoice

1. Open **Check against an invoice** and choose the month.
2. Enter the kWh of that month for each price band (the base price and each time window), and the invoice total including VAT. For market-price tariffs also enter the month's average market price.
3. Edibert recalculates the total with your tariff, adds the fixed monthly costs, and shows the difference.

A difference up to 2 % is normal (rounding). A larger one usually means net/gross mixed up, a forgotten time window, a missing fee or the grid fee.
