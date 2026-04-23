#!/usr/bin/env bash
# Fetch and install PatchDock into $PATCHDOCK.
#
# PatchDock is distributed under a registration-gated form at
# https://bio3d.cs.huji.ac.il/webserver/patchdock/ . The user accepts the
# license by providing their real name, affiliation, and email — which this
# script collects either from env vars (PATCHDOCK_FULLNAME, PATCHDOCK_AFFILIATION,
# PATCHDOCK_EMAIL) or by prompting on a tty.
#
# The download is skipped if $PATCHDOCK/patch_dock.Linux already exists, so
# bind-mount $PATCHDOCK to a persistent host directory to avoid redownloading.
set -euo pipefail

PATCHDOCK=${PATCHDOCK:-/opt/patchdock}
DOWNLOAD_URL=${PATCHDOCK_URL:-https://bio3d.cs.huji.ac.il/webserver/patchdock/download_installer}

if [[ -x "${PATCHDOCK}/patch_dock.Linux" ]]; then
  exit 0
fi

mkdir -p "${PATCHDOCK}"
if ! touch "${PATCHDOCK}/.write_test" 2>/dev/null; then
  echo "ERROR: ${PATCHDOCK} is not writable. Mount it without :ro so PatchDock can be installed." >&2
  exit 2
fi
rm -f "${PATCHDOCK}/.write_test"

prompt_or_env() {
  local var="$1" label="$2" value="${!1:-}"
  if [[ -n "${value}" ]]; then
    printf '%s' "${value}"
    return
  fi
  if [[ ! -t 0 ]]; then
    echo "ERROR: ${var} is not set and stdin is not a tty. Set ${var} or run with 'docker run -it'." >&2
    exit 2
  fi
  local reply=""
  while [[ -z "${reply}" ]]; do
    read -r -p "${label}: " reply </dev/tty
  done
  printf '%s' "${reply}"
}

cat >&2 <<EOF
PatchDock is not installed at ${PATCHDOCK}.
Downloading from ${DOWNLOAD_URL} requires accepting the PatchDock license.
Please provide your real information — it is submitted to the PatchDock
maintainers exactly as it would be on their web form.
EOF

FULLNAME=$(prompt_or_env PATCHDOCK_FULLNAME    "Full name")
AFFIL=$(prompt_or_env    PATCHDOCK_AFFILIATION "Affiliation")
EMAIL=$(prompt_or_env    PATCHDOCK_EMAIL       "Email")

tmp=$(mktemp -d)
trap 'rm -rf "${tmp}"' EXIT
zip="${tmp}/patchdock.zip"

echo "Requesting PatchDock installer..." >&2
http_code=$(curl -sS -L -o "${zip}" -w '%{http_code}' \
  --data-urlencode "fullname=${FULLNAME}" \
  --data-urlencode "affiliation=${AFFIL}" \
  --data-urlencode "email=${EMAIL}" \
  --data-urlencode "os=Linux" \
  "${DOWNLOAD_URL}")

if [[ "${http_code}" != "200" ]]; then
  echo "ERROR: PatchDock download failed (HTTP ${http_code})." >&2
  exit 2
fi

if ! file "${zip}" 2>/dev/null | grep -qi 'zip archive'; then
  echo "ERROR: Server response was not a zip archive. First 200 bytes:" >&2
  head -c 200 "${zip}" >&2 || true
  echo >&2
  exit 2
fi

echo "Extracting..." >&2
unzip -q "${zip}" -d "${tmp}/extract"

bin=$(find "${tmp}/extract" -maxdepth 4 -type f -name 'patch_dock.Linux' -print -quit)
if [[ -z "${bin}" ]]; then
  echo "ERROR: patch_dock.Linux not found in the downloaded archive." >&2
  exit 2
fi

src_dir=$(dirname "${bin}")
cp -a "${src_dir}/." "${PATCHDOCK}/"
chmod +x "${PATCHDOCK}/patch_dock.Linux" 2>/dev/null || true
find "${PATCHDOCK}" -maxdepth 1 -name '*.pl' -exec chmod +x {} +

echo "PatchDock installed to ${PATCHDOCK}." >&2
