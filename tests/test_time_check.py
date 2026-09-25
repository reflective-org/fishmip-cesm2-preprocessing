import pandas as pd
import xarray as xr

from fishmip_cesm.validate import check_time_coverage

WINDOW = ((2035, 1), (2069, 12))


def _monthly(start: str, months: int) -> xr.DataArray:
    time = pd.date_range(start, periods=months, freq="MS") + pd.Timedelta(days=14)
    return xr.DataArray(range(months), dims="time", coords={"time": time})


def test_time_check_passes_on_a_complete_window():
    assert check_time_coverage(_monthly("2035-01-01", 420), WINDOW).passed


def test_time_check_fails_when_a_month_is_missing():
    # The real failure: POP's end-of-interval stamps dropped December 2069.
    check = check_time_coverage(_monthly("2035-01-01", 419), WINDOW)

    assert not check.passed
    assert "419" in check.detail and "420" in check.detail


def test_time_check_fails_when_the_axis_starts_on_the_wrong_month():
    # The other half of the same bug: every month shifted by one.
    check = check_time_coverage(_monthly("2035-02-01", 420), WINDOW)

    assert not check.passed
    assert "2035-02" in check.detail
