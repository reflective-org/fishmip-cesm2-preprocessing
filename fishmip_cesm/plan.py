"""What the writer intends to produce, before it produces any of it.

The full job is large enough that knowing the shape of it in advance matters:
at full depth the complete set runs to hundreds of gigabytes, and it is
destined for a bucket that charges for storage and egress.
"""

from dataclasses import dataclass

from fishmip_cesm.naming import object_key, output_filename
from fishmip_cesm.regrid import fishmip_grid

BYTES_PER_VALUE = 4  # float32
_GRID_CELLS = fishmip_grid().sizes["lat"] * fishmip_grid().sizes["lon"]


@dataclass(frozen=True)
class OutputPlan:
    model: str
    scenario: str
    member: str
    variable: str
    filename: str
    key: str
    months: int
    levels: int

    @property
    def gigabytes(self) -> float:
        """Uncompressed. NetCDF4 deflate typically recovers a factor of two."""
        values = self.months * self.levels * _GRID_CELLS
        return values * BYTES_PER_VALUE / 1e9


def _months_between(window) -> int:
    (y0, m0), (y1, m1) = window
    return (y1 - y0) * 12 + (m1 - m0) + 1


def plan_output(
    *,
    model: str,
    scenario: str,
    member: str,
    variable: str,
    window,
    levels: int,
) -> OutputPlan:
    """Describe one file the writer would produce."""
    filename = output_filename(
        model=model,
        scenario=scenario,
        member=member,
        variable=variable,
        start_year=window[0][0],
        end_year=window[1][0],
    )
    return OutputPlan(
        model=model,
        scenario=scenario,
        member=member,
        variable=variable,
        filename=filename,
        key=object_key(scenario=scenario, filename=filename),
        months=_months_between(window),
        levels=levels,
    )
