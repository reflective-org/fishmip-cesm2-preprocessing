"""Derive FishMIP variables from raw CESM POP/MARBL fields."""

import numpy as _np
import pandas as _pd
import xarray as xr


# POP writes full-depth fields on z_t, but MARBL writes its ecosystem tracers
# (NO3, spC, diatC, zooC) over the top 150 m only, on z_t_150m.
FULL_DEPTH_DIM = "z_t"
UPPER_OCEAN_DIM = "z_t_150m"
_DEPTH_DIMS = (FULL_DEPTH_DIM, UPPER_OCEAN_DIM)


def depth_dim(field: xr.DataArray) -> str | None:
    """Name the field's depth dimension, or None if it has none."""
    return next((d for d in field.dims if d in _DEPTH_DIMS), None)


def extract_seafloor(field: xr.DataArray, kmt: xr.DataArray) -> xr.DataArray:
    """Take the deepest active level of a 3D field at each column.

    POP's KMT counts active levels per column, so the bottom sits at index
    KMT - 1. The field must be full depth: KMT indexes the whole 60-level
    column, so applying it to a 150 m field would read the wrong depths.
    """
    found = depth_dim(field)
    if found != FULL_DEPTH_DIM:
        raise ValueError(
            f"seafloor extraction needs a {FULL_DEPTH_DIM} field, got {found!r}"
        )
    # Some archives store KMT with a fill value, so land decodes to NaN rather
    # than 0. Casting NaN to an integer index is undefined behaviour -- x86
    # yields INT64_MIN and raises far out of bounds, arm64 yields 0 -- so land
    # is normalised to 0 before any arithmetic touches it.
    levels = kmt.fillna(0)
    # Clip before indexing: KMT = 0 is land, and -1 would wrap round to the
    # deepest level instead of masking.
    bottom = (levels - 1).clip(min=0).astype(int)
    return field.isel(z_t=bottom).where(levels > 0)


# CESM name -> (FishMIP name, multiplicative factor, FishMIP units).
#
# mmol/m^3       -> mol m-3      : 1e-3
# mmol/m^3 cm/s  -> mol m-2 s-1  : 1e-3 mol/mmol * 1e-2 m/cm = 1e-5
# nmol/cm^2/s    -> mol m-2 s-1  : 1e-9 mol/nmol * 1e4 cm2/m2 = 1e-5
CONVERSIONS = {
    "TEMP": ("thetao", 1.0, "degC"),
    "NO3": ("no3", 1e-3, "mol m-3"),
    "spC": ("phyc", 1e-3, "mol m-3"),
    "diatC": ("phydiat", 1e-3, "mol m-3"),
    "zooC": ("zooc", 1e-3, "mol m-3"),
    "pocToSed": ("expc-bot", 1e-5, "mol m-2 s-1"),
    # Vertically integrated, hence m-2. The upstream spec asks for mol m-3 s-1,
    # which cannot be right for an integral; awaiting Colleen Petrik. The output
    # name is provisional for the same reason -- there is no CMIP name for this.
    "zoo_loss_zint": ("zoo_loss", 1e-5, "mol m-2 s-1"),
    # Grid geometry, cm -> m. POP writes layer thickness as dz directly, so
    # there is no need to difference z_w_top and z_w_bot.
    "dz": ("thkcello", 0.01, "m"),
    "HT": ("deptho", 0.01, "m"),
    # POP writes cell area in cm^2, not m^2. Getting this wrong scales every
    # global integral by 1e4.
    "TAREA": ("areacello", 1e-4, "m2"),
    # Total carbon fixation: this, not POC_PROD_zint + DOC_prod_zint, is
    # primary production. CMIP6 CMORizes photoC_TOT_zint to intpp for CESM2.
    "photoC_TOT_zint": ("intpp", 1e-5, "mol m-2 s-1"),
}


def convert_variable(cesm_name: str, field: xr.DataArray) -> xr.DataArray:
    """Rename a CESM field to its FishMIP name and convert it to FishMIP units."""
    fishmip_name, factor, units = CONVERSIONS[cesm_name]
    converted = field * factor
    converted.attrs = {"units": units}
    return converted.rename(fishmip_name)


_ZINT_TO_MOL_M2_S = 1e-5


def derive_detrital_carbon_production(
    poc_prod_zint: xr.DataArray,
    doc_prod_zint: xr.DataArray,
) -> xr.DataArray:
    """Vertically integrated production of particulate and dissolved detritus.

    The upstream spec proposed this sum as `intpp`, but it is not primary
    production -- it is organic matter routed into the POC and DOC pools by
    mortality, grazing and aggregation. Integrated globally it comes to roughly
    a third of net primary production. Kept so the two can be compared; use
    `photoC_TOT_zint` for `intpp`.
    """
    detrital = (poc_prod_zint + doc_prod_zint) * _ZINT_TO_MOL_M2_S
    detrital.attrs = {"units": "mol m-2 s-1"}
    return detrital.rename("detrital_c_prod")


def derive_tob(temperature: xr.DataArray, kmt: xr.DataArray) -> xr.DataArray:
    """Sea water potential temperature at the seafloor."""
    tob = extract_seafloor(temperature, kmt)
    tob.attrs = {"units": "degC"}
    return tob.rename("tob")


def subset_to_window(data, window):
    """Clip a monthly time axis to `window`, inclusive of both end months.

    String slicing is deliberate: it selects on year-month regardless of where
    in the month the timestamp falls, which matters because CESM stamps monthly
    means mid-month. It also works for both numpy and cftime axes.
    """
    (start_year, start_month), (end_year, end_month) = window
    # Four-digit years: cftime parses "0335-01" but not "335-01", and piControl
    # model years are three digits or fewer.
    return data.sel(
        time=slice(
            f"{start_year:04d}-{start_month:02d}",
            f"{end_year:04d}-{end_month:02d}",
        )
    )


# Variables produced by a derive_* function rather than by the conversion table.
# Their units are set in the function; these are repeated here so there is one
# place to ask what units any FishMIP variable should carry.
DERIVED_UNITS = {
    "tob": "degC",
    "detrital_c_prod": "mol m-2 s-1",
}


def fishmip_units(fishmip_name: str) -> str:
    """The units a FishMIP variable should carry, converted or derived."""
    for name, _, units in CONVERSIONS.values():
        if name == fishmip_name:
            return units
    return DERIVED_UNITS[fishmip_name]


_BOUNDS_NAMES = ("time_bound", "time_bnds", "time_bounds")


def _month_start(stamp):
    """The first instant of the month a timestamp falls in."""
    if isinstance(stamp, _np.datetime64) or not hasattr(stamp, "calendar"):
        return _np.datetime64(str(_pd.Timestamp(stamp).to_period("M")), "ns")
    import cftime

    return type(stamp)(stamp.year, stamp.month, 1)


def _previous_month_start(stamp):
    """The first instant of the month before the one a timestamp falls in."""
    start = _month_start(stamp)
    if isinstance(start, _np.datetime64):
        period = _pd.Timestamp(start).to_period("M") - 1
        return _np.datetime64(str(period), "ns")
    return type(stamp)(
        stamp.year - 1 if stamp.month == 1 else stamp.year,
        12 if stamp.month == 1 else stamp.month - 1,
        1,
    )


def monthly_bounds(time: xr.DataArray) -> xr.DataArray:
    """Rebuild the averaging intervals of monthly means that ship without them.

    Some archives distribute concatenated monthly means with no `time_bound`:
    the G6-1.5K-MCB runs are one. POP stamps a monthly mean at the *end* of its
    interval, so a mean dated 2035-02-01 covers January, and the interval is
    (first of the previous month, the stamp itself) -- recoverable from the
    stamp alone, with no need for its neighbours.

    This encodes a convention rather than reading one, so it is verified
    against archives that do carry bounds: reconstructing from their stamps
    reproduces their `time_bound` exactly. It stays opt-in per archive even so,
    because an archive that stamps differently would be silently shifted a
    month, which is the error this whole mechanism exists to prevent.
    """
    stamps = time.values
    lower = _np.array([_previous_month_start(s) for s in stamps], dtype=stamps.dtype)
    return xr.DataArray(
        _np.stack([lower, stamps], axis=1), dims=("time", "d2"), name="time_bound"
    )


def covered_span(time) -> tuple[tuple[int, int], tuple[int, int]]:
    """The year-months a run of end-stamped monthly means actually covers.

    Needed where the filenames carry no date range, so the only way to know
    what a file holds is to read its time axis -- and reading it naively is off
    by a month, because the first stamp belongs to the month before it.
    """
    first, last = time[0], time[-1]
    start = _previous_month_start(first)
    end = _previous_month_start(last)
    return (
        (_year_of(start), _month_of(start)),
        (_year_of(end), _month_of(end)),
    )


def _year_of(stamp):
    return _pd.Timestamp(stamp).year if isinstance(stamp, _np.datetime64) else stamp.year


def _month_of(stamp):
    return (
        _pd.Timestamp(stamp).month if isinstance(stamp, _np.datetime64) else stamp.month
    )


def centre_time(dataset: xr.Dataset, reconstruct: bool = False) -> xr.Dataset:
    """Re-stamp monthly means at the middle of their averaging interval.

    POP labels a monthly mean with the *end* of its interval, so January's mean
    arrives dated 1 February. Left alone this shifts every field one month --
    January's data read as February -- and drops the final month of any window,
    because its stamp falls just outside. Neither shows up as an error; a
    seasonal cycle simply comes out a month late.

    The offset is only knowable from the bounds, so a dataset without them is
    refused rather than guessed at.
    """
    declared = dataset["time"].attrs.get("bounds")
    candidates = (declared, *_BOUNDS_NAMES) if declared else _BOUNDS_NAMES
    name = next((n for n in candidates if n and n in dataset.variables), None)
    if name is None and reconstruct:
        bounds = monthly_bounds(dataset["time"])
    elif name is None:
        raise ValueError(
            "cannot centre time: no bounds variable "
            f"(looked for {', '.join(_BOUNDS_NAMES)}). Pass reconstruct=True "
            "for an archive known to stamp monthly means at interval end."
        )
    else:
        bounds = dataset[name]
    edge_dim = [d for d in bounds.dims if d != "time"][0]

    lower = bounds.isel({edge_dim: 0})
    upper = bounds.isel({edge_dim: 1})
    centred = xr.DataArray(
        _midpoint(lower.values, upper.values), dims=lower.dims, name="time"
    )
    return dataset.assign_coords(time=centred)


# A monthly mean carries no sub-second meaning, and a remainder there is
# poison: it forces xarray to write the axis as "nanoseconds since
# <base>.000001536", and udunits will not parse a fractional-second base.
# ncdump prints raw integers and CDO reports every timestamp as
# 0000-00-00 00:00:00, so the axis is silently unreadable outside Python.
_NS_PER_SECOND = 1_000_000_000


def _midpoint(lower, upper):
    """Halfway between two time arrays, whatever calendar they are on.

    piControl runs on a 365-day calendar from model year 1, which datetime64
    cannot represent -- its range starts in 1678 -- so xarray decodes it to
    cftime objects. Those cannot be cast to datetime64, averaged, or added to a
    timedelta64, so each case is converted to a number, halved, and converted
    back.

    Both branches round to the nearest second. The bounds arrive with a
    sub-second remainder already in them, because POP stores them as float64
    days and decoding that lands outside the range where float64 counts
    integers exactly -- about 1536 ns at 2035, about 7 us at 1850.
    """
    if lower.dtype == object:  # cftime, i.e. a model-year or non-standard calendar
        import cftime

        calendar = lower.flat[0].calendar
        # Seconds, not days: a day-based count has to be scaled by 86400e6 to
        # reach microseconds, which overflows exact float64 range on its own.
        units = "seconds since 0001-01-01"
        start = cftime.date2num(lower, units, calendar)
        end = cftime.date2num(upper, units, calendar)
        middle = _np.round((start + end) / 2)
        return cftime.num2date(middle, units, calendar)

    start = lower.astype("datetime64[ns]").astype("int64")
    end = upper.astype("datetime64[ns]").astype("int64")
    middle = start + (end - start) // 2
    # Integer rounding to the nearest second, exact at every magnitude.
    whole = (middle + _NS_PER_SECOND // 2) // _NS_PER_SECOND * _NS_PER_SECOND
    return whole.astype("datetime64[ns]")


def masked_thickness(dz: xr.DataArray, kmt: xr.DataArray) -> xr.DataArray:
    """Layer thickness on the POP grid, masked below the seafloor.

    POP writes `dz` as a single column of nominal layer thicknesses, identical
    everywhere. Broadcasting it across the grid and masking by `KMT` gives the
    field FishMIP expects: a thickness wherever there is water, and nothing
    where there is not. Writing a thickness below the seafloor would claim
    water that is not there.
    """
    level = xr.DataArray(range(dz.sizes[dz.dims[0]]), dims=dz.dims[0])
    return dz.where(level < kmt)
