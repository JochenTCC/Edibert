"""The four steps of the tariff form: base price, time windows, further costs, advanced."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from edbert.editor.model import FEE_KEYS, KINDS, TariffDraft
from edbert.editor.templates import TEMPLATES, rules_for_template
from edbert.i18n import Translator
from edbert.rules import HOLIDAY_MODES, REQUIRES
from edbert.tariff import EXPORT, IMPORT
from edbert.ui import state, widgets


def _number(t: Translator, label_key: str, value: float, name: str, **options) -> float:
    return st.number_input(t.t(label_key), value=float(value), step=options.pop("step", 0.1), format="%.2f", key=state.key(name), **options)


def _vat_fields(t: Translator, draft: TariffDraft) -> None:
    draft.prices_include_vat = st.checkbox(t.t("ui.vat_included"), value=draft.prices_include_vat, key=state.key("vat_included"))
    draft.vat_percent = _number(t, "ui.vat_percent", draft.vat_percent, "vat_percent", min_value=0.0)
    if draft.kind == "spot":
        st.caption(t.t("ui.vat_hint_spot"))


def _spot_fields(t: Translator, draft: TariffDraft) -> None:
    if draft.direction == IMPORT:
        draft.markup_percent = _number(t, "ui.markup_percent", draft.markup_percent, "markup")
        draft.fee_cent = _number(t, "ui.fee_cent", draft.fee_cent, "fee")
    else:
        draft.feed_in_fee_factor = _number(t, "ui.feed_in_fee_factor", draft.feed_in_fee_factor, "fee_factor", min_value=0.0, step=0.01)
        draft.fee_cent = _number(t, "ui.fee_cent_export", draft.fee_cent, "fee")
        draft.feed_in_fix_cent = _number(t, "ui.feed_in_fix_cent", draft.feed_in_fix_cent, "fix")
    options = ("15min", "60min")
    draft.settlement_mtu = st.selectbox(
        t.t("ui.settlement"), options, index=options.index(draft.settlement_mtu), format_func=lambda o: t.t(f"ui.mtu.{o}"),
        key=state.key("mtu"),
    )  # fmt: skip


def _monthly_fields(t: Translator, draft: TariffDraft) -> None:
    st.caption(t.t("ui.monthly_hint"))
    today = date.today()
    frame = pd.DataFrame(
        draft.monthly_rates or [(today.year, today.month, 0.0)], columns=["year", "month", "cent"]
    ).astype({"year": "int64", "month": "int64", "cent": "float64"})
    edited = st.data_editor(frame, num_rows="dynamic", hide_index=True, key=state.key("rates"))
    draft.monthly_rates = [
        (int(row.year), int(row.month), float(row.cent)) for row in edited.dropna().itertuples() if 1 <= int(row.month) <= 12
    ]


def step_base(t: Translator, draft: TariffDraft) -> None:
    draft.label = st.text_input(t.t("ui.label"), value=draft.label, key=state.key("label"))
    draft.supplier = st.text_input(t.t("ui.supplier"), value=draft.supplier, key=state.key("supplier"))
    draft.kind = st.radio(
        t.t("ui.kind"), KINDS, index=KINDS.index(draft.kind), format_func=lambda k: t.t(f"ui.kind.{k}"),
        horizontal=True, key=state.key("kind"),
    )  # fmt: skip
    if draft.kind == "fixed":
        label = "ui.price_cent" if draft.direction == IMPORT else "ui.price_cent_export"
        draft.price_cent = _number(t, label, draft.price_cent, "price", min_value=0.0)
    elif draft.kind == "spot":
        _spot_fields(t, draft)
    else:
        _monthly_fields(t, draft)
    _vat_fields(t, draft)


def _add_template(draft: TariffDraft, name: str, t: Translator) -> None:
    taken = {rule.id for rule in draft.rules if rule.id}
    for rule in rules_for_template(name, t, kind=draft.kind, base_cent=draft.price_cent or 30.0, taken_ids=taken):
        widgets.add_rule(draft.rules, rule)


def step_windows(t: Translator, draft: TariffDraft) -> None:
    st.subheader(t.t("ui.templates"))
    for first in range(0, len(TEMPLATES), 2):
        for column, name in zip(st.columns(2), TEMPLATES[first : first + 2], strict=False):
            column.button(
                t.t(f"editor.template.{name}"), key=state.key(f"tpl.{name}"), on_click=_add_template, args=(draft, name, t),
                width="stretch",
            )  # fmt: skip
    if draft.kind == "spot":
        st.caption(t.t("ui.spot_rules_hint"))
    widgets.rule_editor(t, draft.rules, state.key("rules"))


def step_costs(t: Translator, draft: TariffDraft) -> None:
    st.caption(t.t("ui.fees_hint"))
    fees = {key: _number(t, f"ui.fee.{key}", draft.fees.get(key, 0.0), f"fee_{key}", min_value=0.0) for key in FEE_KEYS}
    draft.fees = {key: value for key, value in fees.items() if value}


def _limit(t: Translator, label: str, current: float | None, name: str) -> float | None:
    if not st.checkbox(t.t(label), value=current is not None, key=state.key(f"use_{name}")):
        return None
    return st.number_input(t.t(f"{label}_value"), value=float(current or 0.0), step=0.1, format="%.2f", key=state.key(name))


def step_advanced(t: Translator, draft: TariffDraft) -> None:
    draft.price_floor_cent_kwh = _limit(t, "ui.floor", draft.price_floor_cent_kwh, "floor")
    draft.price_cap_cent_kwh = _limit(t, "ui.cap", draft.price_cap_cent_kwh, "cap")
    draft.requires = st.multiselect(
        t.t("ui.requires"), REQUIRES, default=draft.requires, format_func=lambda r: t.t(f"requirement.{r}"), key=state.key("requires")
    )
    draft.holiday_mode = st.selectbox(
        t.t("ui.holidays"), HOLIDAY_MODES, index=HOLIDAY_MODES.index(draft.holiday_mode),
        format_func=lambda m: t.t(f"ui.holidays.{m}"), key=state.key("holiday_mode"),
    )  # fmt: skip
    extra = st.text_area(t.t("ui.extra_holidays"), value="\n".join(draft.extra_holiday_dates), help=t.t("ui.extra_holidays_help"), key=state.key("extra_holidays"))
    draft.extra_holiday_dates = [line.strip() for line in extra.splitlines() if line.strip()]
    draft.individual = st.checkbox(t.t("ui.individual"), value=draft.individual, help=t.t("ui.individual_help"), key=state.key("individual"))
    draft.source = st.text_input(t.t("ui.source"), value=draft.source, key=state.key("source"))
    verified = st.text_input(t.t("ui.last_verified"), value=draft.last_verified or "", placeholder="YYYY-MM-DD", key=state.key("verified"))
    draft.last_verified = verified.strip() or None
    draft.behavior_notes = st.text_area(t.t("ui.behavior_notes"), value=draft.behavior_notes, key=state.key("notes"))


STEPS = {1: ("editor.step.base_price", step_base), 2: ("editor.step.time_windows", step_windows),
         3: ("editor.step.further_costs", step_costs), 4: ("editor.step.advanced", step_advanced)}  # fmt: skip


def render_steps(t: Translator, draft: TariffDraft) -> None:
    """Step selector (language-independent keys) and the form of the chosen step."""
    step = st.radio(
        t.t("ui.step"), list(STEPS), index=st.session_state[state.STEP] - 1, format_func=lambda n: f"{n}. {t.t(STEPS[n][0])}",
        horizontal=True, key="ui.step_radio",
    )  # fmt: skip
    st.session_state[state.STEP] = step
    STEPS[step][1](t, draft)


__all__ = ["EXPORT", "render_steps"]
