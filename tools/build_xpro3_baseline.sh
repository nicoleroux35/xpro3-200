#!/usr/bin/env bash
set -euo pipefail

# Build a stock-derived X-Pro3 recovery card. This is not FujiMod and does not
# write to any camera or SD card.
#
# Usage:
#   tools/build_xpro3_baseline.sh FUJIMOD_SD_CARD_BINARY OFFICIAL_FWUP0021.DAT NEW_OUTPUT_DIRECTORY

if [[ $# -ne 3 ]]; then
  echo "usage: $0 FUJIMOD_SD_CARD_BINARY OFFICIAL_FWUP0021.DAT NEW_OUTPUT_DIRECTORY" >&2
  exit 2
fi

binary=$1
dat=$2
output=$3

if [[ -e "$output" ]]; then
  echo "refusing: output already exists: $output" >&2
  exit 2
fi

"$binary" sd-card-recovery-build xpro3-200 "$dat" "$output"
