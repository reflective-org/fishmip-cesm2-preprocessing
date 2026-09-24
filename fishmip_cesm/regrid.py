"""Regrid POP's curvilinear gx1v7 output onto the regular FishMIP grid.

Regridding must be **conservative**, not bilinear. `intpp` and `expc-bot` are
fluxes, and bilinear interpolation does not preserve their global integral --
it would quietly change how much carbon enters the fish models.
"""

import numpy as np
import xarray as xr


def fishmip_grid() -> xr.Dataset:
    """The 1 degree global target grid, with cell bounds for conservative regridding."""
    lat_b = np.arange(-90.0, 90.0 + 1.0, 1.0)
    lon_b = np.arange(-180.0, 180.0 + 1.0, 1.0)
    return xr.Dataset(
        coords={
            "lat": ("lat", (lat_b[:-1] + lat_b[1:]) / 2),
            "lon": ("lon", (lon_b[:-1] + lon_b[1:]) / 2),
            "lat_b": ("lat_b", lat_b),
            "lon_b": ("lon_b", lon_b),
        }
    )


def conservation_error(
    source: xr.DataArray,
    source_area: xr.DataArray,
    target: xr.DataArray,
    target_area: xr.DataArray,
) -> float:
    """Relative change in a field's global integral across a regrid.

    Zero means the integral was preserved. Negative means the target integrates
    low, positive high. This is the acceptance test for the regrid: a
    conservative scheme should return something at the level of floating-point
    noise, and anything larger means the weights or the masks are wrong.
    """
    before = float((source * source_area).sum())
    after = float((target * target_area).sum())
    return (after - before) / before


def apply_weights(
    field: xr.DataArray,
    weights: xr.Dataset,
    n_target: int,
) -> xr.DataArray:
    """Apply an ESMF/SCRIP sparse weight file to a flattened source field.

    Weight generation is done once, offline, with ESMF_RegridWeightGen; this is
    the cheap step that runs per variable and member.

    Target cells that receive no weights come back as NaN rather than zero. For
    a flux that distinction matters: zero is a physical claim that nothing is
    there, whereas these cells are simply outside the source grid's coverage,
    and summing them as zero would understate nothing but mask a coverage bug.
    """
    # ESMF writes 1-based indices.
    rows = weights["row"].values - 1
    cols = weights["col"].values - 1
    sparse = weights["S"].values

    out = np.full(n_target, np.nan)
    contributions = np.zeros(n_target)
    np.add.at(contributions, rows, sparse * field.values[cols])
    touched = np.zeros(n_target, dtype=bool)
    touched[rows] = True
    out[touched] = contributions[touched]
    return xr.DataArray(out, dims="cell")


def fishmip_scrip_grid() -> xr.Dataset:
    """The FishMIP target grid as a SCRIP descriptor, for ESMF_RegridWeightGen.

    The gx1v7 source grid already ships as SCRIP in CESM's inputdata; the target
    has to be written out to pair with it. SCRIP flattens the grid with x
    varying fastest, and lists each cell's four corners counterclockwise from
    the south-west.
    """
    grid = fishmip_grid()
    lat_b = grid["lat_b"].values
    lon_b = grid["lon_b"].values
    ny, nx = len(lat_b) - 1, len(lon_b) - 1

    centre_lon, centre_lat = np.meshgrid(grid["lon"].values, grid["lat"].values)
    west, east = lon_b[:-1], lon_b[1:]
    south, north = lat_b[:-1], lat_b[1:]

    corner_lon = np.stack(
        [
            np.tile(west, ny),
            np.tile(east, ny),
            np.tile(east, ny),
            np.tile(west, ny),
        ],
        axis=1,
    )
    corner_lat = np.stack(
        [
            np.repeat(south, nx),
            np.repeat(south, nx),
            np.repeat(north, nx),
            np.repeat(north, nx),
        ],
        axis=1,
    )

    degrees = {"units": "degrees"}
    return xr.Dataset(
        {
            "grid_dims": ("grid_rank", np.array([nx, ny], dtype="int32")),
            "grid_center_lat": ("grid_size", centre_lat.ravel(), degrees),
            "grid_center_lon": ("grid_size", centre_lon.ravel(), degrees),
            "grid_corner_lat": (("grid_size", "grid_corners"), corner_lat, degrees),
            "grid_corner_lon": (("grid_size", "grid_corners"), corner_lon, degrees),
            "grid_imask": (
                "grid_size",
                np.ones(nx * ny, dtype="int32"),
                {"units": "unitless"},
            ),
        },
        attrs={"title": "FishMIP 1 degree global grid", "Conventions": "SCRIP"},
    )


# ESMF's default sphere, matching CESM's.
EARTH_RADIUS_M = 6.37122e6


def steradians_to_square_metres(area: xr.DataArray) -> xr.DataArray:
    """Convert ESMF cell areas, which are written in steradians, to m^2."""
    return area * EARTH_RADIUS_M**2
