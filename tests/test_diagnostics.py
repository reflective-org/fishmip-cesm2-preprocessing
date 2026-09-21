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
