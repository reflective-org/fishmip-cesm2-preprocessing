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
# One worker, deliberately. HDF5 is not thread-safe, and concurrent writes into
# one file produced chunk-level corruption: "filter returned failure during
# read" while writing, which is HDF5 failing to decompress a chunk it had just
# written. Threads were never buying anything here -- the work is CPU bound and
# HDF5 serialises reads behind a global lock -- so this costs nothing.
DASK_WORKERS="${DASK_WORKERS:-1}"

# The work is CPU bound on zlib. Level 1 roughly halves the compression cost for
# a file maybe 15% larger, which is the right trade when cycles are the thing
# in short supply.
COMPLEVEL="${COMPLEVEL:-1}"

if [ ! -f "${WEIGHTS}" ]; then
    echo "weight file not found: ${WEIGHTS}" >&2
    exit 2
fi

# HDF5 takes file locks by default and locking on Lustre is unreliable enough
# that it can block forever rather than fail. A run hung here for 38 hours in
# state S with no output at all, which is worse than any crash.
export HDF5_USE_FILE_LOCKING=FALSE

export WEIGHTS OUT_DIR DASK_WORKERS COMPLEVEL

python scripts/list_tasks.py > logs/tasks.txt
: > logs/timed_out.txt
total=$(wc -l < logs/tasks.txt)
echo "$(date +%F\ %T) starting: ${total} members, ${CONCURRENT_MEMBERS} at a time"
echo "complevel ${COMPLEVEL}, ${DASK_WORKERS} dask worker(s), nice 19"
echo

run_one() {
    IFS='|' read -r ensemble member <<< "$1"
    echo "$(date +%T) >> ${ensemble} ${member}"
    status=0
    # A member takes well under an hour; three is generous. Without this a
    # single hung write stalls the whole run indefinitely, and resume makes
    # killing and retrying cheap.
    timeout --signal=TERM --kill-after=60 "${MEMBER_TIMEOUT:-3h}" \
        nice -n 19 python -m fishmip_cesm.write_output \
        --weights "${WEIGHTS}" \
        --out-dir "${OUT_DIR}" \
        --ensemble "${ensemble}" \
        --member "${member}" \
        --workers "${DASK_WORKERS}" \
        --complevel "${COMPLEVEL}" \
        --write || status=$?
    if [ "${status}" -eq 124 ]; then
        echo "$(date +%T) !! ${ensemble} ${member} TIMED OUT -- will retry on re-run"
        echo "${ensemble}|${member}" >> logs/timed_out.txt
    fi
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

timed_out=$(wc -l < logs/timed_out.txt)

if [ "${xargs_status}" -ne 0 ] || [ "${written}" -lt "${expected}" ]; then
    echo
    if [ "${timed_out}" -gt 0 ]; then
        echo "${timed_out} member(s) TIMED OUT after ${MEMBER_TIMEOUT:-3h}:"
        sed 's/^/  /' logs/timed_out.txt
        echo
        echo "A member normally takes well under an hour, so a timeout means a"
        echo "hang rather than slow progress. The usual cause is a damaged"
        echo "output file left by an earlier interrupted run: opening it to"
        echo "check whether it is complete blocks instead of failing."
    else
        echo "SOME MEMBERS FAILED. Look for 'FAILED' in this log."
        echo "Running out of room is a common cause: the full set is about"
        echo "280 GB, which does not fit in a GLADE home directory."
    fi
    echo
    echo "Clear anything damaged, then retry:"
    echo "  python -m fishmip_cesm.verify_output --out-dir ${OUT_DIR} --delete-bad"
    echo "  bash scripts/write_all_local.sh"
    exit 1
fi
echo "all members complete"
