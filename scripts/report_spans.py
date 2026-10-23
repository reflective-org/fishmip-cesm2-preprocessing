"""Available span against the window we take, for every ensemble."""

from fishmip_cesm.ensembles import ENSEMBLES, WITHHELD
from fishmip_cesm.sources import member_cases, variable_files
from fishmip_cesm.catalog import parse_timeseries_filename


def _span(ensemble, case):
    parsed = [
        p
        for p in (
            parse_timeseries_filename(f.name)
            for f in variable_files(ensemble, case, "TEMP")
        )
        if p
    ]
    return (min(p.start for p in parsed), max(p.end for p in parsed)) if parsed else None


for ensemble in (*ENSEMBLES, *WITHHELD):
    cases = member_cases(ensemble)
    spans = [s for s in (_span(ensemble, c) for c in cases) if s]
    if not spans:
        print(f"{ensemble.name:28} no TEMP files found")
        continue
    low = min(s[0] for s in spans)
    high = max(s[1] for s in spans)
    (uf, _), (ul, _) = ensemble.window
    note = "" if len(set(spans)) == 1 else "  MEMBERS DIFFER"
    spare = high[0] - ul
    print(
        f"{ensemble.name:28} have {low[0]}-{high[0]}  "
        f"take {uf}-{ul}  "
        f"{'+' + str(spare) + ' yr unused' if spare > 0 else 'all'}{note}"
    )
