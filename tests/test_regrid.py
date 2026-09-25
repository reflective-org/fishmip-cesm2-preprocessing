import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.regrid import (
    apply_weights,
    conservation_error,
    fishmip_grid,
    fishmip_scrip_grid,
    regrid_concentration,
    steradians_to_square_metres,
)


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


def test_fishmip_scrip_grid_describes_every_cell_for_esmf():
    scrip = fishmip_scrip_grid()

    # SCRIP lists cells in a flat array, x varying fastest.
    assert scrip.sizes["grid_size"] == 360 * 180
    assert scrip.sizes["grid_corners"] == 4
    np.testing.assert_array_equal(scrip["grid_dims"].values, [360, 180])
    assert scrip["grid_center_lon"].values[0] == -179.5
    assert scrip["grid_center_lat"].values[0] == -89.5


def test_fishmip_scrip_corners_bound_their_own_cell():
    scrip = fishmip_scrip_grid()

    # First cell spans -180..-179 in longitude and -90..-89 in latitude.
    np.testing.assert_allclose(
        sorted(set(scrip["grid_corner_lon"].values[0])), [-180.0, -179.0]
    )
    np.testing.assert_allclose(
        sorted(set(scrip["grid_corner_lat"].values[0])), [-90.0, -89.0]
    )


def test_fishmip_scrip_grid_is_entirely_unmasked():
    # The target grid is global; masking is the source grid's job.
    scrip = fishmip_scrip_grid()

    assert set(np.unique(scrip["grid_imask"].values)) == {1}


def test_converts_cell_area_from_steradians_to_square_metres():
    # ESMF writes cell areas in steradians. The whole sphere is 4*pi sr and
    # about 5.1e14 m2, which is the only anchor needed to pin the radius.
    whole_sphere = xr.DataArray([4 * np.pi], dims="cell")

    area = steradians_to_square_metres(whole_sphere)

    assert float(area.values[0]) == pytest.approx(5.10e14, rel=1e-2)


def test_concentration_regrid_averages_over_the_ocean_part_of_a_cell():
    # Target cell 1 draws equally from two source cells, one of them land.
    weights = _weights([0.5, 0.5], rows=[1, 1], cols=[1, 2])
    field = xr.DataArray([10.0, np.nan], dims="cell")

    result = regrid_concentration(field, weights, n_target=1)

    # Zero-filling would give 5.0 -- a coastal cell half as cold as the water
    # actually in it, and nothing about the output would look wrong.
    np.testing.assert_allclose(result.values, [10.0])


def test_concentration_regrid_returns_nan_for_a_target_cell_with_no_ocean():
    weights = _weights([0.5, 0.5], rows=[1, 1], cols=[1, 2])
    field = xr.DataArray([np.nan, np.nan], dims="cell")

    result = regrid_concentration(field, weights, n_target=1)

    assert np.isnan(result.values[0])


def test_concentration_regrid_weights_the_ocean_parts_by_their_share():
    # Three quarters of the cell is 20 degC water, one quarter is 8 degC water.
    weights = _weights([0.75, 0.25], rows=[1, 1], cols=[1, 2])
    field = xr.DataArray([20.0, 8.0], dims="cell")

    result = regrid_concentration(field, weights, n_target=1)

    np.testing.assert_allclose(result.values, [17.0])


def test_apply_weights_regrids_many_timesteps_in_one_call():
    # The full job is 420 months by up to 60 levels per variable; regridding
    # one field at a time would dominate the runtime.
    weights = _weights([0.25, 0.75], rows=[1, 1], cols=[1, 2])
    field = xr.DataArray([[4.0, 8.0], [8.0, 16.0]], dims=("time", "cell"))

    result = apply_weights(field, weights, n_target=1)

    assert result.dims == ("time", "cell")
    np.testing.assert_allclose(result.values, [[7.0], [14.0]])


def test_batched_regrid_still_marks_target_cells_with_no_source():
    weights = _weights([1.0], rows=[1], cols=[1])
    field = xr.DataArray([[4.0, 8.0]], dims=("time", "cell"))

    result = apply_weights(field, weights, n_target=2)

    assert np.isnan(result.values[0, 1])


def test_apply_weights_leaves_a_dask_backed_field_lazy():
    # A 60-level, 420-month field is ~25 GB. It must stream rather than load.
    pytest.importorskip("dask")
    weights = _weights([0.25, 0.75], rows=[1, 1], cols=[1, 2])
    field = xr.DataArray(
        [[4.0, 8.0], [8.0, 16.0]], dims=("time", "cell")
    ).chunk({"time": 1})

    result = apply_weights(field, weights, n_target=1)

    assert result.chunks is not None, "regrid forced computation"
    np.testing.assert_allclose(result.compute().values, [[7.0], [14.0]])


def test_apply_weights_handles_a_field_chunked_along_the_cell_axis():
    # Stacking nlat and nlon can leave the flat cell axis split across chunks.
    # The regrid needs the whole horizontal field at once -- it is only about a
    # megabyte -- so it must rechunk rather than fail.
    pytest.importorskip("dask")
    weights = _weights([0.25, 0.75], rows=[1, 1], cols=[1, 2])
    field = xr.DataArray([[4.0, 8.0], [8.0, 16.0]], dims=("time", "cell")).chunk(
        {"time": 1, "cell": 1}
    )

    result = apply_weights(field, weights, n_target=1)

    assert result.chunks is not None, "regrid forced computation"
    np.testing.assert_allclose(result.compute().values, [[7.0], [14.0]])

