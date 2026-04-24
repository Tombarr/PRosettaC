#!/bin/bash -l
#
# SGE submission script for PRosettaC on Boston University SCC.
#
# Replace PROJECT_NAME below with your real BU SCC project before submitting.
# Stage Protac_params.txt + the .smi file into $WORK (or export WORK to an
# existing directory) before running `qsub hpc/scc/submit.sh`.
#
# Required env vars on the submitting shell (passed through -V or set here):
#   PATCHDOCK_FULLNAME, PATCHDOCK_AFFILIATION, PATCHDOCK_EMAIL
# These are only consulted if the PatchDock cache is empty; normal runs use
# the pre-populated cache at $PROJ/patchdock_cache.

#$ -P PROJECT_NAME
#$ -N prosettac
#$ -j y
#$ -l h_rt=24:00:00
#$ -pe omp 8
#$ -l mem_per_core=4G
#$ -V

set -euo pipefail

PROJ=/projectnb/PROJECT_NAME
SIF=${SIF:-$PROJ/containers/prosettac.sif}
CACHE=${CACHE:-$PROJ/patchdock_cache}
WORK=${WORK:-$PROJ/runs/$(date +%Y%m%dT%H%M%SZ)}

mkdir -p "$WORK" "$TMPDIR/prosettac_home"

# Params file must declare `ClusterName: Local` so PRosettaC dispatches
# batches via cluster/Local/Local.py inside the container — the SGE client
# binaries on the host are not ABI-compatible with the Debian image.
if [[ ! -f "$WORK/Protac_params.txt" ]]; then
    echo "ERROR: $WORK/Protac_params.txt not found. Stage inputs into \$WORK before qsub." >&2
    exit 2
fi

scc-singularity run \
    --cleanenv \
    --home "$TMPDIR/prosettac_home" \
    --bind "$TMPDIR:/tmp" \
    --bind "$CACHE:/opt/patchdock" \
    --bind "$WORK:/work" \
    --pwd /work \
    --env "PATCHDOCK_FULLNAME=${PATCHDOCK_FULLNAME:?set PATCHDOCK_FULLNAME in your shell env}" \
    --env "PATCHDOCK_AFFILIATION=${PATCHDOCK_AFFILIATION:?set PATCHDOCK_AFFILIATION in your shell env}" \
    --env "PATCHDOCK_EMAIL=${PATCHDOCK_EMAIL:?set PATCHDOCK_EMAIL in your shell env}" \
    --env TMPDIR=/tmp \
    "$SIF" \
    auto.py Protac_params.txt
