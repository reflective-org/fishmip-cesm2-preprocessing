import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.diagnostics import (
    area_weighted_mean,
    area_weighted_total,
    to_pg_c_per_year,
)


def test_area_weighted_total_multiplies_each_cell_by_its_area_and_sums():
    field = xr.DataArray([2.0, 3.0], dims="cell")  # mol m-2 s-1
    area = xr.DataArray([1.0e6, 2.0e6], dims="cell")  # m2

    assert area_weighted_total(field, area) == pytest.approx(8.0e6)


def test_area_weighted_total_ignores_land_cells():
    # Land is NaN after masking; a plain sum would poison the whole total.
    field = xr.DataArray([2.0, np.nan, 3.0], dims="cell")
    area = xr.DataArray([1.0e6, 5.0e6, 2.0e6], dims="cell")

    assert area_weighted_total(field, area) == pytest.approx(8.0e6)


def test_converts_a_carbon_flux_from_mol_per_second_to_petagrams_per_year():
    # 1 mol C/s * 12.011 g/mol * 3.1536e7 s/yr = 3.788e8 g/yr = 3.788e-7 Pg/yr
    assert to_pg_c_per_year(1.0) == pytest.approx(3.788e-7, rel=1e-3)


def test_area_weighted_mean_weights_each_cell_by_its_area():
    # 10 degC over 1 unit of area and 20 degC over 3 gives 17.5, not 15.
    field = xr.DataArray([10.0, 20.0], dims="cell")
    area = xr.DataArray([1.0e6, 3.0e6], dims="cell")

    assert area_weighted_mean(field, area) == pytest.approx(17.5)


def test_area_weighted_mean_excludes_land_from_both_field_and_area():
    field = xr.DataArray([10.0, np.nan, 20.0], dims="cell")
    area = xr.DataArray([1.0e6, 9.0e6, 3.0e6], dims="cell")

    assert area_weighted_mean(field, area) == pytest.approx(17.5)


def test_published_grid_areas_sum_to_the_surface_of_the_earth():
    # The published files carry no areacello, so a global integral has to
    # compute cell areas from the grid itself. If that formula is wrong every
    # integral built on it is wrong by the same factor, which is precisely the
    # kind of error these checks exist to catch.
    from fishmip_cesm.diagnostics import onedeg_cell_area

    total = float(onedeg_cell_area().sum())

    assert abs(total - 5.10e14) / 5.10e14 < 0.001


def test_an_integral_does_not_silently_drop_mismatched_cells():
    # Areas built on 0.5..359.5 and a field on -179.5..179.5 are the same grid
    # written two ways, but xarray's inner join keeps only the overlap and the
    # integral comes out near half -- plausible enough to publish. The areas
    # must come from the field's own coordinates.
    from fishmip_cesm.diagnostics import area_weighted_total, cell_area_like

    field = xr.DataArray(
        np.ones((180, 360)),
        dims=("lat", "lon"),
        coords={
            "lat": np.arange(-89.5, 90.0, 1.0),
            "lon": np.arange(-179.5, 180.0, 1.0),
        },
    )

    total = area_weighted_total(field, cell_area_like(field))

    assert abs(total - 5.10e14) / 5.10e14 < 0.001


def test_areas_follow_the_fields_own_latitudes():
    from fishmip_cesm.diagnostics import cell_area_like

    field = xr.DataArray(
        np.ones((180, 360)),
        dims=("lat", "lon"),
        coords={
            "lat": np.arange(-89.5, 90.0, 1.0),
            "lon": np.arange(-179.5, 180.0, 1.0),
        },
    )

    area = cell_area_like(field)

    np.testing.assert_array_equal(area["lon"].values, field["lon"].values)
