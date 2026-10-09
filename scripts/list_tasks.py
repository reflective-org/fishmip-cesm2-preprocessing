"""Print one `ensemble|member` line per unit of work, for the batch runner.

Members are independent, so this is the natural unit: 34 lines, each a job that
writes every variable for one member.
"""

from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.sources import member_cases, member_labels


def main() -> int:
    for ensemble in ENSEMBLES:
        for label in member_labels(member_cases(ensemble)):
            print(f"{ensemble.name}|{label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
