"""Derive FishMIP variables from raw CESM POP/MARBL fields."""

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
    # Clip before indexing: KMT = 0 is land, and -1 would wrap round to the
    # deepest level instead of masking.
    bottom = (kmt - 1).clip(min=0).astype(int)
    return field.isel(z_t=bottom).where(kmt > 0)


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
    return data.sel(
        time=slice(
            f"{start_year}-{start_month:02d}",
            f"{end_year}-{end_month:02d}",
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


def centre_time(dataset: xr.Dataset) -> xr.Dataset:
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
    if name is None:
        raise ValueError(
            "cannot centre time: no bounds variable "
            f"(looked for {', '.join(_BOUNDS_NAMES)})"
        )

    bounds = dataset[name]
    edge_dim = [d for d in bounds.dims if d != "time"][0]
    centred = bounds.astype("datetime64[ns]").mean(dim=edge_dim)
    return dataset.assign_coords(time=centred)
