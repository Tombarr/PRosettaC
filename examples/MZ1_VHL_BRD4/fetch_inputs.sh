#!/usr/bin/env bash
# Pulls MZ1's canonical SMILES from PubChem (CID 122201421) into protac.smi.
set -euo pipefail

CID=122201421
URL="https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/${CID}/property/CanonicalSMILES/TXT"

out="$(dirname "$0")/protac.smi"
curl -sSf "${URL}" | tr -d '\r' > "${out}"

if ! [[ -s "${out}" ]]; then
  echo "ERROR: empty response from PubChem for CID ${CID}" >&2
  exit 1
fi

echo "Wrote MZ1 SMILES to ${out}:"
cat "${out}"
