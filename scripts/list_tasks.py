"""Print one `ensemble|member` line per unit of work, for the batch runner.

Members are independent, so this is the natural unit: 34 lines, each a job that
writes every variable for one member.
"""

from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.write_output import _member_label, _members


def main() -> int:
    for ensemble in ENSEMBLES:
        for month_1 in _members(ensemble):
            print(f"{ensemble.name}|{_member_label(month_1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
