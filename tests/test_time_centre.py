import numpy as np
import pandas as pd
import pytest
import xarray as xr

from fishmip_cesm.transform import centre_time


def _end_stamped(bounds_name: str) -> xr.Dataset:
    """Two monthly means stamped at the end of their intervals, as POP writes."""
    edges = pd.to_datetime(["2035-01-01", "2035-02-01", "2035-03-01"])
    bounds = np.stack([edges[:-1], edges[1:]], axis=1)
    return xr.Dataset(
        {
            bounds_name: (("time", "d2"), bounds),
            "TEMP": ("time", [1.0, 2.0]),
        },
        coords={"time": edges[1:]},
    )


@pytest.mark.parametrize("bounds_name", ["time_bound", "time_bnds"])
def test_centres_time_on_the_middle_of_its_averaging_interval(bounds_name):
    centred = centre_time(_end_stamped(bounds_name))

    # January's mean must read as January, not as 1 February.
    assert str(centred.time.values[0])[:7] == "2035-01"
    assert str(centred.time.values[1])[:7] == "2035-02"


def test_centring_leaves_the_data_untouched():
    centred = centre_time(_end_stamped("time_bound"))

    np.testing.assert_array_equal(centred["TEMP"].values, [1.0, 2.0])


def test_centring_refuses_a_dataset_with_no_bounds():
    # Guessing an offset would be worse than stopping: the shift is only
    # knowable from the bounds.
    naked = xr.Dataset(
        {"TEMP": ("time", [1.0])},
        coords={"time": pd.to_datetime(["2035-02-01"])},
    )

    with pytest.raises(ValueError, match="bounds"):
        centre_time(naked)


def _model_year_dataset():
    """piControl: a 365-day calendar starting at model year 1.

    datetime64 cannot represent years before 1678, so xarray decodes these to
    cftime objects. Anything that casts to datetime64 fails here.
    """
    import cftime

    edges = [
        cftime.DatetimeNoLeap(1, 1, 1),
        cftime.DatetimeNoLeap(1, 2, 1),
        cftime.DatetimeNoLeap(1, 3, 1),
    ]
    bounds = np.array([[edges[0], edges[1]], [edges[1], edges[2]]], dtype=object)
    return xr.Dataset(
        {
            "time_bound": (("time", "d2"), bounds),
            "TEMP": ("time", [1.0, 2.0]),
        },
        coords={"time": np.array(edges[1:], dtype=object)},
    )


def test_centres_a_model_year_calendar_outside_datetime64_range():
    centred = centre_time(_model_year_dataset())

    # January's mean must read as January of model year 1, not 1 February.
    first = centred.time.values[0]
    assert (first.year, first.month) == (1, 1)
    second = centred.time.values[1]
    assert (second.year, second.month) == (1, 2)


def test_model_year_centring_leaves_the_data_alone():
    centred = centre_time(_model_year_dataset())

    np.testing.assert_array_equal(centred["TEMP"].values, [1.0, 2.0])


def _historical_dataset():
    """Monthly bounds in 1850 on a noleap calendar, as the historical runs use.

    The bounds arrive already a little off a whole second: POP stores them as
    float64 days, and decoding that at 1850 means ~5.8e16 microseconds, past
    the range where float64 counts integers exactly. Model year 1 is small
    enough to hide this, which is why the existing tests do not catch it.
    """
    import cftime

    edges = [
        cftime.DatetimeNoLeap(1850, 1, 1, microsecond=7),
        cftime.DatetimeNoLeap(1850, 2, 1, microsecond=7),
        cftime.DatetimeNoLeap(1850, 3, 1, microsecond=7),
    ]
    bounds = np.array([[edges[0], edges[1]], [edges[1], edges[2]]], dtype=object)
    return xr.Dataset(
        {
            "time_bound": (("time", "d2"), bounds),
            "TEMP": ("time", [1.0, 2.0]),
        },
        coords={"time": np.array(edges[1:], dtype=object)},
    )


def test_a_historical_centre_lands_on_a_whole_second():
    # A sub-second remainder forces xarray to write the axis as
    # "microseconds since <base>.000007", and udunits will not parse a
    # fractional-second base -- ncdump and CDO both fail to decode it.
    centred = centre_time(_historical_dataset())

    for stamp in centred.time.values:
        assert stamp.microsecond == 0, f"{stamp!r} is not on a whole second"


def _residual_bounds_dataset():
    """Bounds carrying a sub-second remainder, as xarray's decode leaves them.

    POP stores time_bound as float64 days. Decoding that to datetime64[ns] at
    2035 means ~2.05e18 ns, where float64 steps about 455 ns, so the decoded
    edges arrive already a little off a whole second.
    """
    edges = pd.to_datetime(
        ["2035-01-01", "2035-02-01", "2035-03-01"]
    ) + pd.Timedelta(1536, "ns")
    bounds = np.stack([edges[:-1], edges[1:]], axis=1)
    return xr.Dataset(
        {
            "time_bound": (("time", "d2"), bounds),
            "TEMP": ("time", [1.0, 2.0]),
        },
        coords={"time": edges[1:]},
    )


def test_a_scenario_centre_lands_on_a_whole_second():
    centred = centre_time(_residual_bounds_dataset())

    nanoseconds = centred.time.values.astype("datetime64[ns]").astype("int64")
    remainder = nanoseconds % 1_000_000_000
    assert not remainder.any(), f"sub-second remainder {remainder} ns"
