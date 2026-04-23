#!/usr/bin/env bash
# Verify /opt/rosetta matches the layout PRosettaC expects. If the upstream
# image puts things elsewhere, try to discover and symlink them; otherwise
# fail the build with a clear message.
set -euo pipefail

ROSETTA_FOL=${ROSETTA_FOL:-/opt/rosetta}
want_bin="${ROSETTA_FOL}/main/source/bin/rosetta_scripts.default.linuxgccrelease"
want_clean="${ROSETTA_FOL}/tools/protein_tools/scripts/clean_pdb.py"
want_molfile="${ROSETTA_FOL}/main/source/scripts/python/public/molfile_to_params.py"

find_one() {
  local name="$1"
  find "${ROSETTA_FOL}" -name "${name}" -type f -print -quit 2>/dev/null || true
}

fixup() {
  local want="$1" name="$2"
  [[ -e "${want}" ]] && return 0
  local found
  found=$(find_one "${name}")
  if [[ -z "${found}" ]]; then
    return 1
  fi
  mkdir -p "$(dirname "${want}")"
  ln -sf "${found}" "${want}"
  echo "linked ${want} -> ${found}"
}

ok=1
fixup "${want_bin}"     "rosetta_scripts.default.linuxgccrelease" || ok=0
fixup "${want_clean}"   "clean_pdb.py"                             || ok=0
fixup "${want_molfile}" "molfile_to_params.py"                     || ok=0

if [[ ${ok} -eq 0 ]]; then
  cat >&2 <<EOF
ERROR: Could not locate required Rosetta artifacts under ${ROSETTA_FOL}.
Expected:
  ${want_bin}
  ${want_clean}
  ${want_molfile}

The upstream rosettacommons/rosetta image layout likely differs from the
default. Rebuild with the correct source path, e.g.:
  docker build --build-arg ROSETTA_SRC=/actual/path/in/image ...

To inspect the upstream image layout:
  docker run --rm --entrypoint bash rosettacommons/rosetta:serial -c \\
    'find / \( -name "rosetta_scripts*linuxgccrelease" -o -name "clean_pdb.py" \
              -o -name "molfile_to_params.py" \) 2>/dev/null'
EOF
  exit 1
fi

echo "Rosetta layout verified."
