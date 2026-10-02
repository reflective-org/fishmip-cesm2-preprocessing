import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.naming import fixed_filename, object_key
from fishmip_cesm.transform import masked_thickness


def test_thickness_is_broadcast_from_the_one_dimensional_layer_depths():
    dz = xr.DataArray([100.0, 200.0, 300.0], dims="z_t")  # cm
    kmt = xr.DataArray([[3]], dims=("nlat", "nlon"))

    thickness = masked_thickness(dz, kmt)

    assert thickness.dims == ("z_t", "nlat", "nlon")
    np.testing.assert_allclose(thickness.values[:, 0, 0], [100.0, 200.0, 300.0])


def test_thickness_is_masked_below_the_seafloor():
    # KMT counts active levels, so a column with 2 has no third layer. Writing a
    # thickness there would claim water below the seafloor.
    dz = xr.DataArray([100.0, 200.0, 300.0], dims="z_t")
    kmt = xr.DataArray([[2]], dims=("nlat", "nlon"))

    thickness = masked_thickness(dz, kmt)

    assert np.isnan(thickness.values[2, 0, 0])


def test_thickness_is_entirely_missing_over_land():
    dz = xr.DataArray([100.0, 200.0], dims="z_t")
    kmt = xr.DataArray([[0]], dims=("nlat", "nlon"))

    thickness = masked_thickness(dz, kmt)

    assert np.all(np.isnan(thickness.values[:, 0, 0]))


def test_a_fixed_field_is_named_without_a_member_or_a_time_range():
    # These fields are identical for every member and every scenario, so a name
    # carrying either would imply 34 copies of one file.
    name = fixed_filename("deptho")

    assert name == "cesm2_deptho_onedeg_global_fx.nc"
    assert object_key(scenario="grid", filename=name) == f"fishmip/grid/{name}"


def test_a_fixed_field_name_is_refused_for_a_variable_that_varies_in_time():
    with pytest.raises(ValueError, match="thetao"):
        fixed_filename("thetao")


def test_fixed_fields_are_built_and_regridded(tmp_path):
    # End to end on a tiny grid: HT and dz in, deptho and thkcello out on the
    # FishMIP grid, with land and sub-seafloor levels missing.
    from fishmip_cesm.write_static import build_fixed_fields

    n_source, n_target = 4, 180 * 360
    grid = xr.Dataset(
        {
            "KMT": (("nlat", "nlon"), np.array([[3, 0], [2, 3]])),
            "HT": (("nlat", "nlon"), np.array([[300000.0, 0.0], [200000.0, 400000.0]])),
            "dz": ("z_t", np.array([100.0, 200.0, 300.0])),
        }
    )
    weights = xr.Dataset(
        {
            "S": ("n_s", [1.0, 1.0, 1.0, 1.0]),
            "row": ("n_s", [1, 2, 3, 4]),
            "col": ("n_s", [1, 2, 3, 4]),
        }
    )

    fields = build_fixed_fields(grid, weights, n_target)

    assert set(fields) == {"deptho", "thkcello"}
    assert fields["deptho"].dims == ("lat", "lon")
    assert fields["thkcello"].dims == ("z_t", "lat", "lon")
    # HT is cm; 300000 cm is 3000 m.
    depths = fields["deptho"].values[np.isfinite(fields["deptho"].values)]
    assert depths.max() == pytest.approx(4000.0)
