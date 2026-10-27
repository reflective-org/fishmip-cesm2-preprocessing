"""Physical sanity checks on converted fields.

These exist to catch unit-conversion errors, which are otherwise invisible: a
field scaled by the wrong power of ten looks entirely plausible in isolation and
only betrays itself against a known global quantity.
"""

import numpy as np
import xarray as xr


def area_weighted_total(field: xr.DataArray, area: xr.DataArray) -> float:
    """Integrate a per-area field over cell areas."""
    return float((field * area).sum())


_G_C_PER_MOL = 12.011
_SECONDS_PER_YEAR = 365.0 * 24 * 3600  # approximate; this is a sanity check
_G_PER_PG = 1e15


def to_pg_c_per_year(mol_c_per_second: float) -> float:
    """Express a carbon flux in the units global NPP is usually quoted in."""
    return mol_c_per_second * _G_C_PER_MOL * _SECONDS_PER_YEAR / _G_PER_PG


def area_weighted_mean(field: xr.DataArray, area: xr.DataArray) -> float:
    """Area-weighted mean, excluding cells where the field is missing.

    Land must drop out of the denominator as well as the numerator, or the mean
    is diluted by the area of cells that contributed nothing.
    """
    valid_area = area.where(field.notnull())
    return float((field * valid_area).sum() / valid_area.sum())


_EARTH_RADIUS_M = 6.371e6


def cell_area_like(field: xr.DataArray) -> xr.DataArray:
    """Cell areas, in m^2, on the grid the field itself is written on.

    Built from the field's own coordinates rather than an assumed convention.
    A standalone area array on 0.5..359.5 multiplied against a field on
    -179.5..179.5 describes the same grid written two ways, but xarray joins
    on coordinates and keeps only the overlap -- so the integral comes out at
    roughly half and looks merely surprising rather than broken.

    A regular lon/lat cell spans R^2 * dlon * (sin(lat_north) - sin(lat_south)),
    which is exact; the cos(lat) approximation overstates area at the poles.
    """
    latitude = field["lat"]
    longitude = field["lon"]
    dlat = float(abs(latitude[1] - latitude[0]))
    dlon = float(abs(longitude[1] - longitude[0]))
    south = np.deg2rad(latitude.values - dlat / 2)
    north = np.deg2rad(latitude.values + dlat / 2)
    band = _EARTH_RADIUS_M**2 * np.deg2rad(dlon) * (np.sin(north) - np.sin(south))
    return xr.DataArray(
        np.repeat(band[:, None], longitude.size, axis=1),
        dims=("lat", "lon"),
        coords={"lat": latitude, "lon": longitude},
        name="areacello",
    )


def onedeg_cell_area() -> xr.DataArray:
    """Cell areas of the published 1 degree grid, in m^2.

    Only for a grid whose coordinates are not to hand; prefer cell_area_like,
    which cannot disagree with the field it is multiplied against.
    """
    template = xr.DataArray(
        np.zeros((180, 360)),
        dims=("lat", "lon"),
        coords={
            "lat": np.arange(-89.5, 90.0, 1.0),
            "lon": np.arange(0.5, 360.0, 1.0),
        },
    )
    return cell_area_like(template)
