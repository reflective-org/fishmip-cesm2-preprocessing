"""Assemble regridded fields into publishable, self-describing NetCDF."""

import xarray as xr

from fishmip_cesm.regrid import fishmip_grid


def unflatten(flat: xr.DataArray) -> xr.DataArray:
    """Reshape a flat SCRIP-ordered field back onto the FishMIP grid.

    SCRIP lists cells with longitude varying fastest, which is row-major over
    (lat, lon). Getting this wrong transposes the map -- the Pacific ends up
    over Africa -- and nothing downstream would object.

    Leading dimensions (time, depth) are carried through unchanged.
    """
    grid = fishmip_grid()
    n_lat = grid.sizes["lat"]
    n_lon = grid.sizes["lon"]
    leading = flat.shape[:-1]
    return xr.DataArray(
        flat.values.reshape(*leading, n_lat, n_lon),
        dims=flat.dims[:-1] + ("lat", "lon"),
        coords={"lat": grid["lat"].values, "lon": grid["lon"].values},
    )


CONVENTIONS = "CF-1.8"


def to_fishmip_dataset(
    variable: str,
    field: xr.DataArray,
    *,
    model: str,
    scenario: str,
    member: str,
    cesm_source: str,
    notes: str = "",
) -> xr.Dataset:
    """Wrap a regridded field as a self-describing FishMIP forcing dataset.

    The provenance in `history` is not decoration. `intpp` here comes from
    `photoC_TOT_zint`, which differs from what the project specification asked
    for, and a reader who assumes otherwise would misinterpret the field by a
    factor of about three. The file has to be able to answer that question
    without anyone having to find us.
    """
    dataset = xr.Dataset({variable: field})
    dataset["lat"].attrs = {
        "units": "degrees_north",
        "standard_name": "latitude",
        "axis": "Y",
    }
    dataset["lon"].attrs = {
        "units": "degrees_east",
        "standard_name": "longitude",
        "axis": "X",
    }

    history = (
        f"{variable} derived from CESM {cesm_source}; "
        "unit-converted, conservatively regridded from POP gx1v7 to a regular "
        "1 degree grid using ESMF first-order conservative weights"
    )
    if notes:
        history = f"{history}; {notes}"

    dataset.attrs = {
        "Conventions": CONVENTIONS,
        "title": f"FishMIP forcing: {variable}, {model} {scenario} {member}",
        "source_id": model,
        "experiment_id": scenario,
        "variant_label": member,
        "history": history,
        "grid": "regular 1x1 degree, 360x180, cell centres on half degrees",
        "grid_label": "onedeg",
    }
    return dataset
