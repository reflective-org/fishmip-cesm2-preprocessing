import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.output import to_fishmip_dataset, unflatten


def test_unflatten_places_each_value_at_the_right_latitude_and_longitude():
    # SCRIP orders cells with longitude varying fastest, so cell 1 is one step
    # east of cell 0 and cell 360 is one step north. A transposed or
    # column-major reshape would put the Pacific over Africa and look fine
    # until someone plotted it.
    flat = xr.DataArray(np.arange(180 * 360, dtype=float), dims="cell")

    field = unflatten(flat)

    assert field.sizes == {"lat": 180, "lon": 360}
    assert float(field.sel(lat=-89.5, lon=-179.5)) == 0.0
    assert float(field.sel(lat=-89.5, lon=-178.5)) == 1.0
    assert float(field.sel(lat=-88.5, lon=-179.5)) == 360.0


def _blank_field() -> xr.DataArray:
    field = unflatten(xr.DataArray(np.zeros(180 * 360), dims="cell"))
    field.attrs = {"units": "mol m-2 s-1"}
    return field


def _dataset() -> xr.Dataset:
    return to_fishmip_dataset(
        "intpp",
        _blank_field(),
        model="CESM2-WACCM6",
        scenario="G6-1.5K-SAI",
        member="001",
        cesm_source="photoC_TOT_zint",
    )


def test_dataset_carries_cf_coordinate_metadata():
    dataset = _dataset()

    assert dataset["lat"].attrs["units"] == "degrees_north"
    assert dataset["lon"].attrs["units"] == "degrees_east"
    assert dataset.attrs["Conventions"].startswith("CF-")


def test_dataset_records_which_cesm_variable_it_came_from():
    # intpp is a correction to the upstream spec, so the file should say so
    # rather than leaving a reader to assume POC_PROD_zint + DOC_prod_zint.
    dataset = _dataset()

    assert "photoC_TOT_zint" in dataset.attrs["history"]


def test_dataset_identifies_the_simulation_it_describes():
    dataset = _dataset()

    assert dataset.attrs["source_id"] == "CESM2-WACCM6"
    assert dataset.attrs["experiment_id"] == "G6-1.5K-SAI"
    assert dataset.attrs["variant_label"] == "001"


def test_dataset_keeps_the_variable_units():
    assert _dataset()["intpp"].attrs["units"] == "mol m-2 s-1"


def test_unflatten_preserves_leading_time_and_depth_dimensions():
    flat = xr.DataArray(
        np.arange(2 * 180 * 360, dtype=float).reshape(2, -1), dims=("time", "cell")
    )

    field = unflatten(flat)

    assert field.dims == ("time", "lat", "lon")
    assert float(field.isel(time=1).sel(lat=-89.5, lon=-179.5)) == 64800.0


def test_unflatten_leaves_a_dask_backed_field_lazy():
    # .values here materialises the whole regridded variable: for a 60-level
    # field over the analysis window that is a single 13 GB allocation, which
    # no amount of chunking upstream can survive.
    pytest.importorskip("dask")
    flat = xr.DataArray(
        np.zeros((4, 180 * 360)), dims=("time", "cell")
    ).chunk({"time": 1})

    field = unflatten(flat)

    assert field.chunks is not None, "unflatten forced computation"
