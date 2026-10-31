"""Right-hand side of the editor: errors and hints, price curves, price at a time, invoice check, save."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time

import altair as alt
import pandas as pd
import streamlit as st

from edibert.checks import check_grid_fee, check_tariff
from edibert.context import PricingContext
from edibert.editor.house import load_house_grids
from edibert.editor.invoice import (
    BASE_BAND,
    TOLERANCE_PERCENT,
    invoice_bands,
    invoice_check,
)
from edibert.editor.model import TariffDraft, Validation, validate
from edibert.editor.plausibility import plausibility_warnings
from edibert.editor.preview import DAY_KEYS, day_curve, representative_dates
from edibert.editor.userstore import save_user_tariff, user_tariff_ids
from edibert.errors import EdibertError
from edibert.gridfee import GridFee
from edibert.i18n import Translator
from edibert.report import grid_fixed_lines, price_lines
from edibert.tariff import IMPORT, Tariff, evaluate, monthly_rate
from edibert.ui import state, widgets
from edibert.ui.config import UiConfig


@contextmanager
def guarded(t: Translator) -> Iterator[None]:
    """Show coded errors as a message instead of a stack trace."""
    try:
        yield
    except EdibertError as err:
        st.error(t.error(err))


def _hints(t: Translator, tariff: Tariff, ctx: PricingContext, grid_fee: GridFee | None, capabilities: list[str]) -> None:
    notes = check_tariff(tariff, capabilities) + (check_grid_fee(grid_fee) if grid_fee else [])
    notes += plausibility_warnings(tariff, ctx, date.today().year)
    for note in notes:
        st.warning(t.warning(note))


def _month_rate_hint(t: Translator, tariff: Tariff, ctx: PricingContext, year: int, month: int) -> None:
    """A monthly table without this month: say which month's rate is used instead (``MONTH_RATE_FALLBACK``)."""
    if tariff.type != "monthly_table":
        return
    _rate, notes = monthly_rate(tariff, ctx.to_local(datetime(year, month, 1)))
    for note in notes:
        st.warning(t.warning(note))


def _chart_frame(t: Translator, tariff: Tariff, ctx: PricingContext, grid_fee: GridFee | None, month: int) -> pd.DataFrame:
    rows = []
    for key, day in representative_dates(ctx, tariff, date.today().year, month).items():
        for point in day_curve(tariff, ctx, day, grid_fee=grid_fee):
            hour = point.start.hour + point.start.minute / 60
            rows.append({"hour": hour, "cent": point.cent, "day": t.t(f"ui.day.{key}")})
    return pd.DataFrame(rows)


def _curves(t: Translator, tariff: Tariff, ctx: PricingContext, grid_fee: GridFee | None) -> None:
    st.subheader(t.t("ui.preview"))
    month = st.selectbox(
        t.t("ui.preview_month"), list(range(1, 13)), index=date.today().month - 1, format_func=lambda m: t.t(f"month.{m}"),
        key=state.k("ui.preview_month"),
    )  # fmt: skip
    if tariff.is_spot:
        st.caption(t.t("ui.preview_mtu", interval=t.t(f"ui.mtu_short.{tariff.settlement_mtu}")))
    if tariff.uses_market_price:
        st.caption(t.t("ui.preview_spot_note"))
    frame = _chart_frame(t, tariff, ctx, grid_fee, month)
    _month_rate_hint(t, tariff, ctx, date.today().year, month)
    chart = (
        alt.Chart(frame)
        .mark_line(interpolate="step-after")
        .encode(
            x=alt.X("hour:Q", title=t.t("ui.chart_x"), scale=alt.Scale(domain=[0, 24])),
            y=alt.Y("cent:Q", title=t.t("ui.chart_y")),
            color=alt.Color("day:N", title=None, sort=[t.t(f"ui.day.{key}") for key in DAY_KEYS]),
            tooltip=["day", "hour", "cent"],
        )
    )
    st.altair_chart(chart, width="stretch")


def _probe(t: Translator, tariff: Tariff, ctx: PricingContext, grid_fee: GridFee | None) -> None:
    st.subheader(t.t("ui.probe"))
    left, right = st.columns(2)
    day = left.date_input(t.t("ui.probe_date"), value=date.today(), key=state.k("ui.probe_date"))
    moment = right.time_input(t.t("ui.probe_time"), value=time(12, 0), step=900, key=state.k("ui.probe_time"))
    epex = None
    if tariff.uses_market_price:
        epex = st.number_input(t.t("ui.probe_market"), value=10.0, step=0.5, format=widgets.CENT_FORMAT, key=state.k("ui.probe_market"))
    slot = datetime.combine(day, moment)
    result = evaluate(tariff, slot, ctx, epex, grid_fee)
    lines = price_lines(t, tariff, result, ctx.to_local(slot), ctx.timezone)
    lines += grid_fixed_lines(t, grid_fee if tariff.direction == IMPORT else None)
    st.code("\n".join(lines), language=None)
    for note in result.warnings:
        st.warning(t.warning(note))


def _invoice(t: Translator, tariff: Tariff, ctx: PricingContext, grid_fee: GridFee | None) -> None:
    with st.expander(t.t("ui.invoice")), guarded(t):
        st.caption(t.t("ui.invoice_hint"))
        month = st.date_input(t.t("ui.invoice_month"), value=date.today().replace(day=1), key=state.k("ui.inv_month"))
        market = None
        if tariff.uses_market_price:
            market = st.number_input(t.t("ui.invoice_market"), value=10.0, step=0.5, format=widgets.CENT_FORMAT, key=state.k("ui.inv_market"))
        _month_rate_hint(t, tariff, ctx, month.year, month.month)
        kwh: dict[str, float] = {}
        for band in invoice_bands(tariff, ctx, month, market_cent=market, grid_fee=grid_fee):
            label = t.t("ui.band_base") if band.id == BASE_BAND else band.label
            kwh[band.id] = st.number_input(
                t.t("ui.invoice_kwh", band=label, cent=t.number(band.cent)), min_value=0.0, step=1.0,
                key=state.k(f"ui.inv.{state.key(band.id)}"),
            )  # fmt: skip
        total = st.number_input(t.t("ui.invoice_total"), min_value=0.0, step=1.0, key=state.k("ui.inv_total"))
        if total > 0 and any(kwh.values()):
            check = invoice_check(tariff, ctx, month, kwh, total, market_cent=market, grid_fee=grid_fee)
            st.write(t.t("ui.invoice_result", expected=t.number(check.expected_eur, 2), invoice=t.number(check.invoice_eur, 2), deviation=t.number(check.deviation_percent, 2)))
            if check.grid_fixed_eur:
                st.caption(t.t("ui.invoice_grid_fixed", eur=t.number(check.grid_fixed_eur, 2)))
            if check.ok:
                st.success(t.t("ui.invoice_ok"))
            else:
                st.warning(t.t("ui.invoice_off", tolerance=t.number(TOLERANCE_PERCENT, 1)))


def store(t: Translator, config: UiConfig, draft: TariffDraft, validation: Validation) -> None:
    """Write the validated draft to the user file, tell the host and leave the success notice."""
    save_user_tariff(config.user_file, validation.raw, draft.direction)
    draft.id = validation.raw["id"]
    state.mark_saved()
    if config.on_change is not None:
        config.on_change("save", draft.direction, draft.id)
    state.notify(t.t("ui.saved", tariff_id=draft.id))


def _save(t: Translator, draft: TariffDraft, validation: Validation, config: UiConfig) -> None:
    if st.button(t.t("ui.save"), type="primary", key=state.k("ui.save")):
        store(t, config, draft, validation)
        st.rerun()


def _house_facts(config: UiConfig) -> tuple[PricingContext, GridFee | None, list[str]]:
    """Context, grid fee and capabilities: from the host when it supplies them, else the editor's house settings."""
    host = config.host_house
    if host is not None:
        return host.context, host.grid_fee, list(host.capabilities)
    house = state.house()
    return house.context(), house.grid_fee(load_house_grids(config.catalog, config.data_dir)), house.capabilities


def render_curves(t: Translator, tariff: Tariff, ctx: PricingContext, grid_fee: GridFee | None, capabilities: list[str]) -> None:
    """Hints and price curves of one tariff (the host's preview of a selected tariff)."""
    with guarded(t):
        _hints(t, tariff, ctx, grid_fee, capabilities)
    with guarded(t):
        _curves(t, tariff, ctx, grid_fee)


def render(t: Translator, draft: TariffDraft, config: UiConfig) -> None:
    """Validate the draft and show everything that depends on it."""
    taken = user_tariff_ids(config.user_file)[draft.direction]
    validation = validate(draft, taken)
    if validation.tariff is None:
        st.error(t.error(validation.error))  # type: ignore[arg-type]
        return
    with guarded(t):
        ctx, grid_fee, capabilities = _house_facts(config)
        with guarded(t):
            _hints(t, validation.tariff, ctx, grid_fee, capabilities)
        with guarded(t):
            _curves(t, validation.tariff, ctx, grid_fee)
        with guarded(t):
            _probe(t, validation.tariff, ctx, grid_fee)
        _invoice(t, validation.tariff, ctx, grid_fee)
    _save(t, draft, validation, config)
