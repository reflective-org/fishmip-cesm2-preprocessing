"""Repairing a time axis that only Python can read, without rewriting the data."""

import cftime
import netCDF4
import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.repair_time import needs_repair, repair_file


def _file_with(tmp_path, units, calendar, values):
    """A minimal forcing file carrying the given time encoding."""
    path = tmp_path / "sample.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", len(values))
        time = dataset.createVariable("time", "i8", ("time",))
        time.units = units
        time.calendar = calendar
        time[:] = values
        field = dataset.createVariable("intpp", "f4", ("time",))
        field.units = "mol m-2 s-1"
        field[:] = np.arange(len(values), dtype="f4")
    return path


# The exact encoding and values found on 36 published historical files.
_BROKEN_UNITS = "microseconds since 1850-01-16 13:00:00.000007"
_BROKEN_VALUES = [0, 2545199999993, 5093999999993]


def test_a_fractional_second_base_is_flagged(tmp_path):
    path = _file_with(tmp_path, _BROKEN_UNITS, "noleap", _BROKEN_VALUES)

    assert needs_repair(path)


def test_a_clean_base_is_left_alone(tmp_path):
    path = _file_with(tmp_path, "hours since 2035-01-16 12:00:00",
                      "noleap", [0, 708, 1416])

    assert not needs_repair(path)
    assert repair_file(path) is False


def test_repair_makes_the_axis_readable(tmp_path):
    path = _file_with(tmp_path, _BROKEN_UNITS, "noleap", _BROKEN_VALUES)

    assert repair_file(path) is True

    with netCDF4.Dataset(path) as dataset:
        units = dataset.variables["time"].units
    assert "." not in units.split(":")[-1], f"still fractional: {units}"
    assert not needs_repair(path)


def test_repair_preserves_the_timestamps_to_the_second(tmp_path):
    path = _file_with(tmp_path, _BROKEN_UNITS, "noleap", _BROKEN_VALUES)
    before = cftime.num2date(np.array(_BROKEN_VALUES), _BROKEN_UNITS, "noleap")

    repair_file(path)

    with xr.open_dataset(path) as dataset:
        after = dataset["time"].values
    for original, repaired in zip(before, after):
        drift = abs((repaired - original).total_seconds())
        assert drift <= 0.5, f"{original} moved to {repaired}"


def test_repair_does_not_touch_the_data(tmp_path):
    path = _file_with(tmp_path, _BROKEN_UNITS, "noleap", _BROKEN_VALUES)

    repair_file(path)

    with xr.open_dataset(path) as dataset:
        np.testing.assert_array_equal(
            dataset["intpp"].values, np.array([0.0, 1.0, 2.0], dtype="f4")
        )


# The encoding on the 72 published scenario files. cftime refuses to decode
# 'nanoseconds' at all, so a repair that goes through dates cannot touch these.
_BROKEN_NS_UNITS = "nanoseconds since 2035-01-16 13:00:00.000001536"
_SECOND_NS = 1_000_000_000
_BROKEN_NS_VALUES = [0, 2548800 * _SECOND_NS - 1536, 5097600 * _SECOND_NS - 1536]


def test_a_nanosecond_axis_is_repaired(tmp_path):
    path = _file_with(tmp_path, _BROKEN_NS_UNITS, "noleap", _BROKEN_NS_VALUES)

    assert repair_file(path) is True
    assert not needs_repair(path)

    with netCDF4.Dataset(path) as dataset:
        time = dataset.variables["time"]
        assert time.units == "hours since 2035-01-16 13:00:00"
        np.testing.assert_array_equal(time[:], [0, 708, 1416])


def test_a_nanosecond_repair_keeps_the_data(tmp_path):
    path = _file_with(tmp_path, _BROKEN_NS_UNITS, "noleap", _BROKEN_NS_VALUES)

    repair_file(path)

    with netCDF4.Dataset(path) as dataset:
        np.testing.assert_array_equal(
            dataset.variables["intpp"][:], np.array([0.0, 1.0, 2.0], dtype="f4")
        )
