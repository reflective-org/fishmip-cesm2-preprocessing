import pandas as pd
import xarray as xr

from fishmip_cesm.transform import subset_to_window


def _monthly_series(start: str, months: int) -> xr.DataArray:
    # CESM writes monthly means stamped mid-month, not at the month boundary.
    time = pd.date_range(start, periods=months, freq="MS") + pd.Timedelta(days=15)
    return xr.DataArray(range(months), dims="time", coords={"time": time})


def test_subsets_a_monthly_axis_to_the_window_inclusive_of_both_end_months():
    series = _monthly_series("2034-01-01", months=36)

    subset = subset_to_window(series, window=((2035, 1), (2035, 12)))

    assert len(subset.time) == 12
    assert subset.time.values[0].astype("datetime64[M]").astype(str) == "2035-01"
    assert subset.time.values[-1].astype("datetime64[M]").astype(str) == "2035-12"


def _model_year_series(start_year: int, months: int):
    """A 365-day calendar series, as piControl is decoded."""
    import cftime
    import numpy as np

    stamps = [
        cftime.DatetimeNoLeap(start_year + m // 12, m % 12 + 1, 16)
        for m in range(months)
    ]
    return xr.DataArray(
        range(months), dims="time", coords={"time": np.array(stamps, dtype=object)}
    )


def test_subsets_a_model_year_calendar():
    # piControl years are three digits or fewer, and cftime needs a four-digit
    # ISO year: "335-01" does not parse, "0335-01" does.
    series = _model_year_series(334, 36)

    subset = subset_to_window(series, window=((335, 1), (335, 12)))

    assert len(subset.time) == 12
    assert (subset.time.values[0].year, subset.time.values[0].month) == (335, 1)
    assert (subset.time.values[-1].year, subset.time.values[-1].month) == (335, 12)
