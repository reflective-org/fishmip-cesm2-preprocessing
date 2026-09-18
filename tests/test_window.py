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
