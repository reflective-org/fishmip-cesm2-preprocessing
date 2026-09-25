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
