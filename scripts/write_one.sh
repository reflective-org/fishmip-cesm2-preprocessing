#!/bin/bash
# Write every variable for one member. Takes "ensemble|member" as $1.
# Reads WEIGHTS, OUT_DIR and DASK_WORKERS from the environment.
set -uo pipefail

IFS='|' read -r ensemble member <<< "$1"
echo "[$(date +%H:%M:%S)] start ${ensemble} ${member}"

python -m fishmip_cesm.write_output \
    --weights "${WEIGHTS}" \
    --out-dir "${OUT_DIR}" \
    --ensemble "${ensemble}" \
    --member "${member}" \
    --workers "${DASK_WORKERS}" \
    --write
status=$?

echo "[$(date +%H:%M:%S)] end   ${ensemble} ${member} (exit ${status})"
# Deliberately not fatal: one bad member should not take the array with it.
# Re-running the job skips whatever completed and retries the rest.
exit 0
