#!/usr/bin/env bash
set -euo pipefail

source /opt/conda/etc/profile.d/conda.sh
conda activate "${CONDA_ENV:-prosettac}"

: "${PROSETTAC_HOME:=/opt/prosettac}"
: "${ROSETTA3_HOME:=/opt/rosetta}"
: "${PATCHDOCK:=/opt/patchdock}"
: "${OB:=/opt/conda/envs/prosettac/bin}"
: "${SCRIPTS_FOL:=${PROSETTAC_HOME}/}"
export PROSETTAC_HOME ROSETTA3_HOME PATCHDOCK OB SCRIPTS_FOL

if [[ $# -eq 0 || "$1" == "--help" || "$1" == "-h" ]]; then
  cat <<EOF
PRosettaC container.

Usage:
  docker run --rm -it \\
    -v /path/to/patchdock_cache:/opt/patchdock \\
    -v \$PWD:/work \\
    prosettac <script> <params-file>

<script> is one of: auto.py | main.py | extended.py | short.py
Params file path is relative to /work (your bind-mounted working directory).

On first run, PatchDock is fetched from bio3d.cs.huji.ac.il using your
real name, affiliation, and email (license acceptance). Provide these
interactively on a tty, or non-interactively via environment variables:
  PATCHDOCK_FULLNAME, PATCHDOCK_AFFILIATION, PATCHDOCK_EMAIL

Set ClusterName: Local in your params file to run without a scheduler.
EOF
  exit 0
fi

rosetta_bin="${ROSETTA3_HOME}/main/source/bin/rosetta_scripts.default.linuxgccrelease"
if [[ ! -x "${rosetta_bin}" ]]; then
  echo "ERROR: Rosetta binary not found at ${rosetta_bin}." >&2
  exit 2
fi

"${PROSETTAC_HOME}/docker/fetch-patchdock.sh"

if [[ ! -x "${PATCHDOCK}/patch_dock.Linux" ]]; then
  echo "ERROR: PatchDock not found at ${PATCHDOCK}/patch_dock.Linux after install attempt." >&2
  exit 2
fi

script="$1"; shift
exec python "${PROSETTAC_HOME}/${script}" "$@"
