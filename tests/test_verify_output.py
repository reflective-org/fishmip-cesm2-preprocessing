import numpy as np
import xarray as xr

from fishmip_cesm.verify_output import verify

MONTHS = 420


def _write(path, name="intpp", months=MONTHS, units="mol m-2 s-1", value=1e-6):
    time = xr.date_range("2035-01-01", periods=months, freq="MS")
    field = xr.DataArray(
        np.full((months, 2, 2), value),
        dims=("time", "lat", "lon"),
        coords={"time": time, "lat": [0.5, 1.5], "lon": [0.5, 1.5]},
        attrs={"units": units},
    )
    xr.Dataset({name: field}).to_netcdf(path)


def test_a_good_file_verifies(tmp_path):
    path = tmp_path / "good.nc"
    _write(path)

    assert verify(path)[0] == "ok"


def test_a_truncated_file_is_reported_incomplete(tmp_path):
    path = tmp_path / "short.nc"
    _write(path, months=120)

    verdict, detail = verify(path)

    assert verdict == "incomplete"
    assert "120" in detail


def test_a_file_that_is_not_netcdf_is_bad(tmp_path):
    # What two processes writing the same path at once can leave behind.
    path = tmp_path / "mangled.nc"
    path.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 64)

    assert verify(path)[0] == "bad"


def test_values_outside_their_range_are_bad(tmp_path):
    path = tmp_path / "wrong.nc"
    _write(path, value=5.0)  # mol m-2 s-1; five orders too large

    verdict, detail = verify(path)

    assert verdict == "bad"
    assert "range" in detail


def test_missing_units_are_bad(tmp_path):
    path = tmp_path / "nounits.nc"
    _write(path, units="")

    assert verify(path)[0] == "bad"
