"""Reusable form parts: the list of time-window rows (used for tariffs and for the grid fee)."""

from __future__ import annotations

from datetime import time

import streamlit as st

from edibert.editor.model import DAY_NAMES, HOLIDAY, RuleDraft
from edibert.i18n import Translator
from edibert.rules import MODE_ABSOLUTE, MODE_PERCENT_OFF, MODES
from edibert.ui import state

DEFAULT_START, DEFAULT_END = "08:00", "20:00"
CENT_FORMAT = "%.3f"  # ct/kWh inputs keep three decimals (price sheets list e.g. 0,393 ct/kWh)


def _to_time(text: str) -> time:
    hour, minute = text.split(":")
    return time(int(hour) % 24, int(minute))


def move_rule(rules: list[RuleDraft], uid: int, delta: int) -> None:
    index = next(i for i, rule in enumerate(rules) if rule.uid == uid)
    target = index + delta
    if 0 <= target < len(rules):
        rules[index], rules[target] = rules[target], rules[index]


def delete_rule(rules: list[RuleDraft], uid: int) -> None:
    rules[:] = [rule for rule in rules if rule.uid != uid]


def add_rule(rules: list[RuleDraft], rule: RuleDraft | None = None) -> None:
    new = rule or RuleDraft(start=DEFAULT_START, end=DEFAULT_END)
    state.assign_uids([new])
    rules.append(new)


def _time_fields(t: Translator, rule: RuleDraft, key) -> None:
    if st.checkbox(t.t("ui.rule_all_day"), value=rule.start is None, key=key("all")):
        rule.start = rule.end = None
        return
    left, right = st.columns(2)
    start, end = rule.start or DEFAULT_START, rule.end or DEFAULT_END
    rule.start = left.time_input(t.t("ui.rule_from"), value=_to_time(start), step=900, key=key("from")).strftime("%H:%M")
    rule.end = right.time_input(t.t("ui.rule_to"), value=_to_time(end), step=900, key=key("to")).strftime("%H:%M")


def _effect_fields(t: Translator, rule: RuleDraft, key) -> None:
    left, right = st.columns(2)
    rule.mode = left.selectbox(
        t.t("ui.rule_effect"), MODES, index=MODES.index(rule.mode), format_func=lambda m: t.t(f"ui.mode.{m}"), key=key("mode")
    )
    low = 0.0 if rule.mode in (MODE_ABSOLUTE, MODE_PERCENT_OFF) else None
    high = 100.0 if rule.mode == MODE_PERCENT_OFF else None
    start = rule.value if low is None else min(max(rule.value, low), high or rule.value)
    rule.value = right.number_input(
        t.t("ui.rule_value"), value=float(start), min_value=low, max_value=high, step=0.1, format=CENT_FORMAT, key=key(f"value.{rule.mode}")
    )


def _rule_row(t: Translator, rule: RuleDraft, index: int, rules: list[RuleDraft], prefix: str) -> None:
    def key(name: str) -> str:
        return f"{prefix}.r{rule.uid}.{name}"

    with st.container(border=True):
        label, up, down, remove = st.columns([8, 1, 1, 1])
        rule.label = label.text_input(t.t("ui.rule_label"), value=rule.label, key=key("label"))
        up.button("↑", key=key("up"), on_click=state.bound(move_rule), args=(rules, rule.uid, -1), disabled=index == 0, help=t.t("ui.rule_up"))
        down.button("↓", key=key("down"), on_click=state.bound(move_rule), args=(rules, rule.uid, 1), disabled=index == len(rules) - 1, help=t.t("ui.rule_down"))
        remove.button("✕", key=key("del"), on_click=state.bound(delete_rule), args=(rules, rule.uid), help=t.t("ui.rule_delete"))
        _time_fields(t, rule, key)
        rule.days = st.multiselect(
            t.t("ui.rule_days"), [*DAY_NAMES, HOLIDAY], default=rule.days, format_func=lambda d: t.t(f"weekday.{d}"),
            help=t.t("ui.rule_days_help"), key=key("days"),
        )  # fmt: skip
        rule.months = st.multiselect(
            t.t("ui.rule_months"), list(range(1, 13)), default=rule.months, format_func=lambda m: t.t(f"month.{m}"),
            help=t.t("ui.rule_months_help"), key=key("months"),
        )  # fmt: skip
        _effect_fields(t, rule, key)


def rule_editor(t: Translator, rules: list[RuleDraft], prefix: str) -> None:
    """One row per rule, in order (the first matching row wins), plus a button for a new row."""
    st.caption(t.t("ui.first_wins_hint"))
    for index, rule in enumerate(rules):
        _rule_row(t, rule, index, rules, prefix)
    st.button(t.t("ui.add_rule"), key=f"{prefix}.add", on_click=state.bound(add_rule), args=(rules,))
