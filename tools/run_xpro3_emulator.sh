#!/usr/bin/env bash
set -euo pipefail

# Offline X-Pro3 emulator attempt. It never touches a camera or SD card.
#
# Usage:
#   tools/run_xpro3_emulator.sh FUJIMOD_DIR FIRMWARE_DIR [INSTRUCTION_LIMIT]
#
# The stock image is a second-stage loader. Its first-stage loader
# (`ffinit.bin`) reads the core count and parks the secondary cores; loading
# the second stage directly leaves that word at one, so the boot core never
# parks them and all four run the boot sequence concurrently. The run therefore
# supplies the real core count before it starts.

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 FUJIMOD_DIR FIRMWARE_DIR [INSTRUCTION_LIMIT]" >&2
  exit 2
fi

repo=$1
firmware_dir=$2
dat="$firmware_dir/FWUP0021.DAT"
plan="$firmware_dir/xpro3-emulator-plan.json"
limit=${3:-2000000}

cd "$repo"
cargo run --locked -p fujimod-emulator-cli --bin fujimod-emulator -- boot \
  --configuration xpro3-200-handoff \
  --update "$dat" \
  --application-plan "$plan" \
  --instruction-limit "$limit" \
  --execution-policy interactive \
  --poke 0xa2ec=4