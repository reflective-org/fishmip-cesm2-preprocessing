import numpy as np
import xarray as xr

from fishmip_cesm.write_output import is_complete


def _written(path, months: int) -> None:
    time = xr.date_range("2035-01-01", periods=months, freq="MS")
    xr.Dataset(
        {"intpp": ("time", np.zeros(months))}, coords={"time": time}
    ).to_netcdf(path)


def test_a_missing_file_is_not_complete(tmp_path):
    assert not is_complete(tmp_path / "absent.nc", 420)


def test_a_fully_written_file_is_complete(tmp_path):
    target = tmp_path / "full.nc"
    _written(target, 420)

    assert is_complete(target, 420)


def test_a_truncated_file_is_not_complete(tmp_path):
    # A job killed mid-write leaves a short file. Treating it as done would
    # publish a gap that nothing downstream would notice.
    target = tmp_path / "short.nc"
    _written(target, 120)

    assert not is_complete(target, 420)


def test_an_unreadable_file_is_not_complete(tmp_path):
    target = tmp_path / "corrupt.nc"
    target.write_bytes(b"not a netcdf file")

    assert not is_complete(target, 420)
