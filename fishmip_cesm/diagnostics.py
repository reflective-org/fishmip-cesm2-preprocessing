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


def onedeg_cell_area() -> xr.DataArray:
    """Cell areas of the published 1 degree grid, in m^2.

    The published files carry no areacello, so a global integral has to derive
    areas from the grid. On a regular lon/lat grid a cell spans
    R^2 * dlon * (sin(lat_north) - sin(lat_south)), which is exact rather than
    the cos(lat) approximation -- the difference matters most at the poles,
    where the approximation overstates area.
    """
    latitude = np.arange(-89.5, 90.0, 1.0)
    edges = np.deg2rad(np.arange(-90.0, 90.5, 1.0))
    band = _EARTH_RADIUS_M**2 * np.deg2rad(1.0) * np.diff(np.sin(edges))
    return xr.DataArray(
        np.repeat(band[:, None], 360, axis=1),
        dims=("lat", "lon"),
        coords={"lat": latitude, "lon": np.arange(0.5, 360.0, 1.0)},
        name="areacello",
    )
