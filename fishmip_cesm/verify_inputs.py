"""Verify every configured ensemble before preprocessing. Run this on Derecho.

    python -m fishmip_cesm.verify_inputs

Exits non-zero if any ensemble is missing variables or has coverage gaps.
"""

import sys

from fishmip_cesm.catalog import CaseReport, verify_ensemble
from fishmip_cesm.ensembles import ANALYSIS_WINDOW, ENSEMBLES, REQUIRED_VARIABLES


def _format_span(span) -> str:
    (y0, m0), (y1, m1) = span
    return f"{y0}-{m0:02d} to {y1}-{m1:02d}"


def _describe(report: CaseReport) -> list[str]:
    lines = []
    if report.missing_variables:
        lines.append(f"    missing: {', '.join(report.missing_variables)}")
    for variable, gaps in sorted(report.gaps.items()):
        if gaps:
            spans = "; ".join(_format_span(g) for g in gaps)
            lines.append(f"    gap in {variable}: {spans}")
    return lines


def main() -> int:
    window = _format_span(ANALYSIS_WINDOW)
    print(f"Verifying {len(ENSEMBLES)} ensembles over {window}\n")

    failures = 0
    for ensemble in ENSEMBLES:
        reports = verify_ensemble(
            ensemble.root,
            ensemble.case_glob,
            REQUIRED_VARIABLES,
            ANALYSIS_WINDOW,
        )
        ok = sum(1 for r in reports if r.ok)
        status = "ok" if reports and ok == len(reports) else "PROBLEM"
        print(f"{ensemble.name} [{ensemble.model}]: {ok}/{len(reports)} members ok  {status}")

        if not reports:
            print(f"    no case directories matched {ensemble.case_glob}")
            print(f"    under {ensemble.root}")
            failures += 1
        for report in reports:
            if not report.ok:
                failures += 1
                print(f"  {report.case}")
                for line in _describe(report):
                    print(line)
        print()

    if failures:
        print(f"{failures} problem(s) found.")
        return 1
    print("All ensembles complete over the analysis window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
