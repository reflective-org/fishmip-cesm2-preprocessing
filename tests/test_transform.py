import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.transform import (
    convert_variable,
    derive_intpp,
    derive_tob,
    extract_seafloor,
)


def _column_field() -> xr.DataArray:
    """A 4-level field whose values encode their own level: 10, 20, 30, 40."""
    levels = np.arange(1, 5, dtype=float) * 10.0
    return xr.DataArray(
        np.broadcast_to(levels[:, None, None], (4, 2, 2)).copy(),
        dims=("z_t", "nlat", "nlon"),
    )


def test_extracts_the_deepest_active_level_in_each_column():
    # KMT counts active levels, so the bottom is at index KMT - 1.
    kmt = xr.DataArray(np.array([[4, 2], [3, 1]]), dims=("nlat", "nlon"))

    seafloor = extract_seafloor(_column_field(), kmt)

    np.testing.assert_array_equal(
        seafloor.values, np.array([[40.0, 20.0], [30.0, 10.0]])
    )


def test_masks_land_columns_where_no_levels_are_active():
    # KMT = 0 is land. Indexing naively gives -1, which would silently return
    # the deepest level instead of a mask.
    kmt = xr.DataArray(np.array([[4, 0], [3, 1]]), dims=("nlat", "nlon"))

    seafloor = extract_seafloor(_column_field(), kmt)

    assert np.isnan(seafloor.values[0, 1])


def test_converts_nitrate_from_mmol_per_m3_to_mol_per_m3():
    no3 = xr.DataArray([35.0], dims="x")  # mmol/m^3, typical deep ocean

    converted = convert_variable("NO3", no3)

    assert converted.name == "no3"
    assert converted.attrs["units"] == "mol m-3"
    np.testing.assert_allclose(converted.values, [0.035])


@pytest.mark.parametrize(
    "cesm_name, fishmip_name, raw, expected, units",
    [
        ("TEMP", "thetao", 12.5, 12.5, "degC"),
        ("pocToSed", "expc-bot", 2.0, 2.0e-5, "mol m-2 s-1"),
        ("spC", "phyc", 4.0, 4.0e-3, "mol m-3"),
        ("diatC", "phydiat", 4.0, 4.0e-3, "mol m-3"),
        ("zooC", "zooc", 4.0, 4.0e-3, "mol m-3"),
        ("zoo_loss_zint", "zoo_loss", 2.0, 2.0e-5, "mol m-2 s-1"),
        ("dz", "thkcello", 500.0, 5.0, "m"),
        ("HT", "deptho", 400000.0, 4000.0, "m"),
        ("TAREA", "areacello", 1.0e10, 1.0e6, "m2"),
    ],
)
def test_converts_each_single_source_variable(
    cesm_name, fishmip_name, raw, expected, units
):
    converted = convert_variable(cesm_name, xr.DataArray([raw], dims="x"))

    assert converted.name == fishmip_name
    assert converted.attrs["units"] == units
    np.testing.assert_allclose(converted.values, [expected])


def test_intpp_sums_particulate_and_dissolved_carbon_production():
    poc_prod = xr.DataArray([2.0], dims="x")  # mmol/m^3 cm/s
    doc_prod = xr.DataArray([3.0], dims="x")

    intpp = derive_intpp(poc_prod, doc_prod)

    assert intpp.name == "intpp"
    assert intpp.attrs["units"] == "mol m-2 s-1"
    np.testing.assert_allclose(intpp.values, [5.0e-5])


def test_tob_is_temperature_at_the_seafloor():
    kmt = xr.DataArray(np.array([[4, 2], [3, 1]]), dims=("nlat", "nlon"))

    tob = derive_tob(_column_field(), kmt)

    assert tob.name == "tob"
    assert tob.attrs["units"] == "degC"
    np.testing.assert_array_equal(tob.values, np.array([[40.0, 20.0], [30.0, 10.0]]))
