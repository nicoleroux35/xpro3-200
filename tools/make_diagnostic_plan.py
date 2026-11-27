#!/usr/bin/env python3
"""Build an X-Pro3 runnable plan from the handoff plan, with the two known
blockers worked around *as diagnostics only*.

Two independent things are needed to get past the transfer-engine stop:

1. `--discovery` on the command line (it is a CLI flag, not a plan key) plus a
   declared transmit receiver, so the fixed-destination DMA is modelled.
2. A patch that forces the synchronous path instead of the completion-event
   wait, because the engine's service thread never exists in this
   configuration. See reports/EMULATOR-2026-11-26.md §5-6.

Neither changes the firmware file; both are per-run and reversible.

Usage:
    tools/make_diagnostic_plan.py IN_PLAN OUT_PLAN [--labels 0xADDR,...]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Receive address used by the XP4 transmit path; 0x34 = the request id the
# X-T3 profile declares for its receiver. Values are diagnostics, not
# measurements of an X-Pro3.
RECEIVER = {
    "address": 0xFFF69000,
    "request": 34,
    "capacity": 4096,
    "offer_at": 0,
    "offer_bytes": 64,
}

POWER_SPI_OUTPUT = {"bank": False, "register": 17, "value": 4096}

PATCH = """\
# Diagnostic only: take the transfer engine's synchronous polling path instead
# of waiting for the completion event (0x400), which needs an engine service
# thread that does not exist in this configuration.
[[patch]]
address = 0x10908a4
original_hex = "000059e3"
patched_hex = "0000a0e3"
at_ms = 0
reason = "diagnostic: synchronous polling instead of the 0x400 event wait"
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("in_plan", type=Path)
    parser.add_argument("out_plan", type=Path)
    parser.add_argument("--labels", default="", help="extra hex addresses, comma separated")
    parser.add_argument("--patch-out", type=Path, help="write the diagnostic patch file here")
    args = parser.parse_args()

    document = json.loads(args.in_plan.read_text())
    definition = document["board"]["definition"]
    definition["discovery_tx_receiver"] = RECEIVER
    definition.setdefault("power_spi_command_output", POWER_SPI_OUTPUT)
    if args.labels:
        labels = set(definition.get("labels") or [])
        for text in args.labels.split(","):
            text = text.strip()
            if text:
                labels.add(int(text, 0))
        definition["labels"] = sorted(labels)

    # the emulator resolves plan file references relative to the plan's directory
    base = args.in_plan.parent
    document["flash"] = str((base / document["flash"]).resolve())
    for image in document.get("images", []):
        image["file"] = str((base / image["file"]).resolve())

    args.out_plan.write_text(json.dumps(document, indent=2) + "\n")
    print(f"{args.out_plan}")
    if args.patch_out:
        args.patch_out.write_text(PATCH)
        print(f"{args.patch_out}")


if __name__ == "__main__":
    main()