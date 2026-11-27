#!/usr/bin/env bash
set -euo pipefail

# Open the X-Pro3 analysis bench on the stock 2.00 firmware.
#
# Usage:
#   apps/xpro3-bench/run.sh [--check] [EXTRA BENCH OPTIONS...]
#
# The firmware and plan are read from ../xpro3-firmware by default; override
# them with FUJIMOD_XPRO3_FIRMWARE_DIR.

workspace=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
firmware_dir=${FUJIMOD_XPRO3_FIRMWARE_DIR:-$workspace/../xpro3-firmware}

if [[ ! -f "$firmware_dir/FWUP0021.DAT" ]]; then
  echo "run.sh: missing $firmware_dir/FWUP0021.DAT" >&2
  echo "run.sh: set FUJIMOD_XPRO3_FIRMWARE_DIR to the directory holding the update" >&2
  exit 2
fi

# The declared plan references its files relative to its own directory; make
# them absolute so the bench can run from anywhere.
plan=$(mktemp --suffix=.json)
trap 'rm -f "$plan"' EXIT
python3 - "$firmware_dir/xpro3-emulator-plan.json" "$plan" <<'PY'
import json, sys
from pathlib import Path

source, out = Path(sys.argv[1]), Path(sys.argv[2])
document = json.loads(source.read_text())
base = source.parent
if document.get("flash"):
    document["flash"] = str((base / document["flash"]).resolve())
for image in document.get("images", []):
    image["file"] = str((base / image["file"]).resolve())
out.write_text(json.dumps(document, indent=1))
PY

cd "$workspace"
cargo build -p fujimod-xpro3-bench
exec ./target/debug/fujimod-xpro3-bench \
  --update "$firmware_dir/FWUP0021.DAT" \
  --application-plan "$plan" \
  "$@"