import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.regrid import apply_weights, conservation_error, fishmip_grid


def test_fishmip_grid_is_one_degree_with_cell_centres_on_half_degrees():
    grid = fishmip_grid()

    assert grid.sizes["lat"] == 180
    assert grid.sizes["lon"] == 360
    assert grid.lat.values[0] == -89.5
    assert grid.lat.values[-1] == 89.5
    assert grid.lon.values[0] == -179.5
    assert grid.lon.values[-1] == 179.5


def test_fishmip_grid_bounds_tile_the_globe_with_no_gaps_or_overlaps():
    grid = fishmip_grid()

    # One more bound than cell, spanning pole to pole and the full longitude
    # circle, with every cell exactly one degree wide.
    assert len(grid.lat_b) == 181
    assert len(grid.lon_b) == 361
    assert grid.lat_b.values[0] == -90.0
    assert grid.lat_b.values[-1] == 90.0
    assert grid.lon_b.values[0] == -180.0
    assert grid.lon_b.values[-1] == 180.0
    np.testing.assert_allclose(np.diff(grid.lat_b.values), 1.0)
    np.testing.assert_allclose(np.diff(grid.lon_b.values), 1.0)


def test_conservation_error_is_zero_when_the_global_integral_is_preserved():
    # 2 units over 3 m2 = 6, redistributed as 1 unit over each of two 3 m2 cells.
    source = xr.DataArray([2.0], dims="cell")
    source_area = xr.DataArray([3.0], dims="cell")
    target = xr.DataArray([1.0, 1.0], dims="cell")
    target_area = xr.DataArray([3.0, 3.0], dims="cell")

    error = conservation_error(source, source_area, target, target_area)

    assert error == pytest.approx(0.0)


def test_conservation_error_reports_the_relative_shortfall():
    # Source integrates to 6; target to 5.7, i.e. 5% low.
    source = xr.DataArray([2.0], dims="cell")
    source_area = xr.DataArray([3.0], dims="cell")
    target = xr.DataArray([1.9], dims="cell")
    target_area = xr.DataArray([3.0], dims="cell")

    error = conservation_error(source, source_area, target, target_area)

    assert error == pytest.approx(-0.05)


def _weights(sparse_values, rows, cols) -> xr.Dataset:
    """A minimal ESMF/SCRIP weight file. row and col are 1-based."""
    return xr.Dataset(
        {
            "S": ("n_s", sparse_values),
            "row": ("n_s", rows),
            "col": ("n_s", cols),
        }
    )


def test_apply_weights_combines_source_cells_into_each_target_cell():
    # Target cell 1 draws a quarter of source cell 1 and three quarters of 2.
    weights = _weights([0.25, 0.75], rows=[1, 1], cols=[1, 2])
    field = xr.DataArray([4.0, 8.0], dims="cell")

    result = apply_weights(field, weights, n_target=1)

    np.testing.assert_allclose(result.values, [7.0])


def test_apply_weights_leaves_target_cells_with_no_source_contribution_empty():
    # Target cell 2 gets no weights at all -- it must not silently read as zero.
    weights = _weights([1.0], rows=[1], cols=[1])
    field = xr.DataArray([4.0, 8.0], dims="cell")

    result = apply_weights(field, weights, n_target=2)

    np.testing.assert_allclose(result.values[0], 4.0)
    assert np.isnan(result.values[1])
