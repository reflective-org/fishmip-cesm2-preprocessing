import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.transform import depth_dim, extract_seafloor


def _field(dim: str) -> xr.DataArray:
    return xr.DataArray(np.zeros((2, 1, 1)), dims=(dim, "nlat", "nlon"))


def test_finds_the_full_depth_dimension():
    assert depth_dim(_field("z_t")) == "z_t"


def test_finds_the_upper_ocean_dimension_marbl_uses_for_tracers():
    # MARBL writes NO3, spC, diatC and zooC over the top 150 m only.
    assert depth_dim(_field("z_t_150m")) == "z_t_150m"


def test_returns_none_for_a_field_with_no_depth():
    assert depth_dim(xr.DataArray(np.zeros((1, 1)), dims=("nlat", "nlon"))) is None


def test_seafloor_extraction_refuses_a_field_that_is_not_full_depth():
    # KMT indexes the full 60-level column. Applying it to a 15-level field
    # would read the wrong depths or fall off the end.
    kmt = xr.DataArray(np.array([[2]]), dims=("nlat", "nlon"))

    with pytest.raises(ValueError, match="z_t_150m"):
        extract_seafloor(_field("z_t_150m"), kmt)
