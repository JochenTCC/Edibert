"""AppTest helpers for the tariff overview: views, tables, row selection and actions.

AppTest cannot click a table row. The selection is set the way the spike of Editor P4a found: write the table
widget's state (``{"selection": {"rows": [...], "columns": []}}``) before ``run()``.
"""

from streamlit.testing.v1 import AppTest

DIRECTIONS = ("import", "export")


def show_view(app: AppTest, view: str, prefix: str = "") -> None:
    app.segmented_control(key=f"{prefix}view.switch").set_value(view).run()


def table(app: AppTest, direction: str):
    """The table of the overview tab ``direction`` as a DataFrame (the overview's tabs come first on the page)."""
    (frame,) = app.tabs[DIRECTIONS.index(direction)].dataframe
    return frame.value


def labels(app: AppTest, direction: str) -> list[str]:
    return list(table(app, direction)["label"])


def table_key(app: AppTest, direction: str, prefix: str = "") -> str:
    start = f"{prefix}ov.{direction}.table."
    (key,) = [key for key in app.session_state.keys() if key.startswith(start)]  # noqa: SIM118 (AppTest state has no __iter__)
    return key


def _select_rows(app: AppTest, direction: str, rows: list[int], prefix: str) -> None:
    app.session_state[table_key(app, direction, prefix)] = {"selection": {"rows": rows, "columns": []}}
    app.run()


def select(app: AppTest, direction: str, chosen: list[str], prefix: str = "") -> None:
    """Select the rows with these labels in the ``direction`` table (all other shown rows unselected)."""
    shown = labels(app, direction)
    _select_rows(app, direction, [shown.index(label) for label in chosen], prefix)


def select_keys(app: AppTest, direction: str, keys: list[str], prefix: str = "") -> None:
    """Select rows by their row key (``own:user_x``, ``catalog:at_y``)."""
    shown = list(table(app, direction).index)
    _select_rows(app, direction, [shown.index(key) for key in keys], prefix)


def open_own(app: AppTest, direction: str, tariff_id: str, prefix: str = "") -> None:
    """Open an own tariff the way a user does: overview, select its row, "Open"."""
    show_view(app, "overview", prefix)
    select_keys(app, direction, [f"own:{tariff_id}"], prefix)
    run_action(app, direction, "open", prefix)


def action(app: AppTest, direction: str, name: str, prefix: str = ""):
    """The action button ``open`` / ``copy`` / ``delete`` / ``compare`` of the ``direction`` table."""
    return app.button(key=f"{prefix}ov.{direction}.{name}")


def run_action(app: AppTest, direction: str, name: str, prefix: str = "") -> None:
    button = action(app, direction, name, prefix)
    assert not button.disabled, button.help
    button.click().run()
