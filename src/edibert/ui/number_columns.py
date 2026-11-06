"""Numeric table columns in the browser's number format, shared with hosts such as Earnie.

Streamlit tables draw numbers in the browser, so server-side number text does not reach them
unless the column becomes text, which breaks numeric sorting. Printf formats always write a
point, and the ``localized`` format writes what the browser's locale says.
"""

from __future__ import annotations

import streamlit as st


def localized_number_column(label: str | None = None, *, decimals: int | None = None, **options):
    """A ``NumberColumn`` in the browser's locale; the values stay numbers and sort as numbers.

    ``decimals`` fixes the digits shown. It also sets ``step``, which limits what a user can type
    in ``st.data_editor``, so leave it out for editable amounts: the browser then shows up to three
    decimals and the stored value keeps all of its digits.
    """
    if decimals is not None:
        if "step" in options:
            raise ValueError("Pass either decimals or step, not both.")
        options["step"] = 10**-decimals
    return st.column_config.NumberColumn(label, format="localized", **options)
