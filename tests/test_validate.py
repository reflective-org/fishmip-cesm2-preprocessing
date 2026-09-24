import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.validate import (
    check_no_ocean_holes,
    check_range,
    check_units,
    gate_passed,
    validate_variable,
)


def test_range_check_passes_when_every_value_is_plausible():
    thetao = xr.DataArray([-1.5, 15.0, 30.0], dims="cell")

    assert check_range("thetao", thetao).passed


def test_range_check_fails_and_names_the_offending_extreme():
    # A Kelvin/Celsius slip would look exactly like this.
    thetao = xr.DataArray([288.0, 295.0], dims="cell")

    check = check_range("thetao", thetao)

    assert not check.passed
    assert "295" in check.detail


def test_range_check_ignores_land():
    thetao = xr.DataArray([np.nan, 15.0, np.nan], dims="cell")

    assert check_range("thetao", thetao).passed


def test_range_check_refuses_a_variable_it_has_no_range_for():
    # Failing closed: an unrecognised variable must stop the gate, not pass it.
    with pytest.raises(KeyError):
        check_range("chl", xr.DataArray([1.0], dims="cell"))


def test_ocean_hole_check_fails_when_a_cell_with_ocean_has_no_value():
    # A regrid that drops cells leaves holes the range check cannot see.
    field = xr.DataArray([10.0, np.nan, 12.0], dims="cell")
    ocean = xr.DataArray([True, True, True], dims="cell")

    check = check_no_ocean_holes(field, ocean)

    assert not check.passed
    assert "1" in check.detail


def test_ocean_hole_check_allows_missing_values_over_land():
    field = xr.DataArray([10.0, np.nan], dims="cell")
    ocean = xr.DataArray([True, False], dims="cell")

    assert check_no_ocean_holes(field, ocean).passed


def test_units_check_passes_when_units_match_the_conversion_table():
    thetao = xr.DataArray([1.0], dims="cell", attrs={"units": "degC"})

    assert check_units("thetao", thetao).passed


def test_units_check_fails_when_the_units_attribute_is_missing():
    # Attributes are easy to drop in an xarray round-trip, and a file published
    # without units is not usable forcing.
    thetao = xr.DataArray([1.0], dims="cell")

    assert not check_units("thetao", thetao).passed


def test_units_check_fails_when_the_units_are_wrong():
    thetao = xr.DataArray([1.0], dims="cell", attrs={"units": "K"})

    check = check_units("thetao", thetao)

    assert not check.passed
    assert "degC" in check.detail


def test_every_variable_with_a_range_also_has_known_units():
    # tob is derived rather than converted, so it is easy for it to have a
    # plausible range declared but no units the gate can check against.
    from fishmip_cesm.validate import PLAUSIBLE_RANGES, _expected_units

    missing = []
    for name in PLAUSIBLE_RANGES:
        try:
            _expected_units(name)
        except KeyError:
            missing.append(name)

    assert missing == []


def test_validating_a_variable_checks_range_units_and_coverage():
    thetao = xr.DataArray([10.0, 12.0], dims="cell", attrs={"units": "degC"})
    ocean = xr.DataArray([True, True], dims="cell")

    checks = validate_variable("thetao", thetao, ocean)

    assert {c.name for c in checks} == {
        "thetao range",
        "thetao units",
        "ocean coverage",
    }
    assert gate_passed(checks)


def test_the_gate_fails_if_any_single_check_fails():
    # Units and coverage are fine; only the range is wrong.
    thetao = xr.DataArray([10.0, 999.0], dims="cell", attrs={"units": "degC"})
    ocean = xr.DataArray([True, True], dims="cell")

    checks = validate_variable("thetao", thetao, ocean)

    assert not gate_passed(checks)
