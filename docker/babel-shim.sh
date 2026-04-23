#!/usr/bin/env bash
# Translate OpenBabel 2.x argument syntax ("babel in.ext out.ext [flags]")
# to OpenBabel 3.x syntax ("obabel in.ext -O out.ext [flags]"), which is
# what PRosettaC's utils.py invokes via $OB/babel.
set -eu

if [[ $# -lt 2 ]]; then
  exec obabel "$@"
fi

in="$1"
out="$2"
shift 2
exec obabel "$in" -O "$out" "$@"
