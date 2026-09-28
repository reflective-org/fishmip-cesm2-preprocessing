#!/bin/bash
# Write the full set on a login node, slowly and politely.
#
#     nohup bash scripts/write_all_local.sh > logs/local.log 2>&1 &
#     tail -f logs/local.log
#
# Login nodes are shared and NCAR's arbiter throttles or kills users who take
# too much of one. So this runs few members at a time, at the lowest priority,
# with cheap compression. It is slow by design: expect most of a day.
#
# Stopping it is safe and resuming is the normal way to use it -- completed
# files are skipped, truncated ones are rewritten. Kill it whenever the node is
# busy and start it again later.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
mkdir -p logs output

WEIGHTS="${WEIGHTS:-grids/gx1v7_to_fishmip_1deg_conserve.nc}"
OUT_DIR="${OUT_DIR:-output}"

# Two concurrent members at one core each. Raising this is what gets a login
# node account throttled; it is not the place to make up time.
CONCURRENT_MEMBERS="${CONCURRENT_MEMBERS:-2}"
DASK_WORKERS="${DASK_WORKERS:-1}"

# The work is CPU bound on zlib. Level 1 roughly halves the compression cost for
# a file maybe 15% larger, which is the right trade when cycles are the thing
# in short supply.
COMPLEVEL="${COMPLEVEL:-1}"

if [ ! -f "${WEIGHTS}" ]; then
    echo "weight file not found: ${WEIGHTS}" >&2
    exit 2
fi

export WEIGHTS OUT_DIR DASK_WORKERS COMPLEVEL

python scripts/list_tasks.py > logs/tasks.txt
total=$(wc -l < logs/tasks.txt)
echo "$(date +%F\ %T) starting: ${total} members, ${CONCURRENT_MEMBERS} at a time"
echo "complevel ${COMPLEVEL}, ${DASK_WORKERS} dask worker(s), nice 19"
echo

run_one() {
    IFS='|' read -r ensemble member <<< "$1"
    echo "$(date +%T) >> ${ensemble} ${member}"
    status=0
    nice -n 19 python -m fishmip_cesm.write_output \
        --weights "${WEIGHTS}" \
        --out-dir "${OUT_DIR}" \
        --ensemble "${ensemble}" \
        --member "${member}" \
        --workers "${DASK_WORKERS}" \
        --complevel "${COMPLEVEL}" \
        --write || status=$?
    echo "$(date +%T) << ${ensemble} ${member} (exit ${status})"
    return "${status}"
}
export -f run_one

xargs -a logs/tasks.txt -d '\n' -P "${CONCURRENT_MEMBERS}" -I{} \
    bash -c 'run_one "$@"' _ {}
xargs_status=$?

written=$(ls -1 "${OUT_DIR}"/*.nc 2>/dev/null | wc -l)
expected=$(( total * 9 ))
echo
echo "$(date +%F\ %T) finished: ${written} of ${expected} file(s) in ${OUT_DIR}"

if [ "${xargs_status}" -ne 0 ] || [ "${written}" -lt "${expected}" ]; then
    echo
    echo "SOME MEMBERS FAILED. Look for 'FAILED' in this log."
    echo "Running out of room is the usual cause: the full set is about 280 GB,"
    echo "which does not fit in a GLADE home directory. Set OUT_DIR to scratch."
    echo
    echo "Then check what landed and retry:"
    echo "  python -m fishmip_cesm.verify_output --out-dir ${OUT_DIR} --delete-bad"
    echo "  bash scripts/write_all_local.sh"
    exit 1
fi
echo "all members complete"
