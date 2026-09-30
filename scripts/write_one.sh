#!/bin/bash
# Write every variable for one member. Takes "ensemble|member" as $1.
# Reads WEIGHTS, OUT_DIR and DASK_WORKERS from the environment.
set -uo pipefail

IFS='|' read -r ensemble member <<< "$1"
echo "[$(date +%H:%M:%S)] start ${ensemble} ${member}"

timeout --signal=TERM --kill-after=60 "${MEMBER_TIMEOUT:-3h}" \
    python -m fishmip_cesm.write_output \
    --weights "${WEIGHTS}" \
    --out-dir "${OUT_DIR}" \
    --ensemble "${ensemble}" \
    --member "${member}" \
    --workers "${DASK_WORKERS}" \
    --write
status=$?

echo "[$(date +%H:%M:%S)] end   ${ensemble} ${member} (exit ${status})"
# Report the real status. xargs keeps going on any code except 255, so one bad
# member still does not take the array with it -- but swallowing the code made
# a run where every member failed print "done" and exit clean.
exit "${status}"
