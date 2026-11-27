#!/usr/bin/env python3
"""Write a copy of the X-Pro3 application plan with passive labels added.

Labels are observation points only: `fujimod-emulator boot` records the first
instruction count at which each address is entered, plus call arguments and
results for labelled call sites. They never select device or CPU behaviour, so
this is safe on any run.

Usage:
    tools/add_labels.py IN_PLAN OUT_PLAN [--labels 0xADDR[,0xADDR...]]...

Default label set covers the boot chain measured in
`docs/CORRECTIONS-2026-11-27.md`; pass extra addresses with --labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BOOT_CHAIN = [
    0x1162F14,  # main()
    0x114F798,  # task registration / thread creation path
    0x4C1E0, 0x4C04C,  # thread create wrappers
    0x1163500,  # TSK_ROOT body
    0x1150210,  # start task
    0x1152B30, 0x1152D24, 0x108C5D4, 0x10A981C, 0x108B03C,
    0x115F838, 0x115FA30, 0x57974, 0x1151048, 0x1152C18,
    0x1163744, 0x113A7BC,  # storage init, configuration read
    0x1093410,  # NOR read through 0xFFFD80xx
    0x10907AC,  # transfer submitter
    0x109099C,  # transfer-engine wait (0x400)
    0x10908C0, 0x10908E8, 0x1090AF8, 0x1090B3C,  # completion paths
    0x1090BEC,  # posts 0x400
    0x1090DB8,  # engine wait on 0x100
    0x1090BA8,  # posts 0x100
    0x1090E68,  # event-8 callback registration
    0x114FC44, 0x57B74, 0x51E9C, 0x4E998,  # current-task-id chain
    0x4A94C, 0x54FE8, 0x516F0, 0x11500F4, 0x1150004,  # event flags
    0x4B0C4, 0x4B074, 0x4BE9C,  # registry / presence
    0x5B4F8, 0x5B570,
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("in_plan", type=Path)
    parser.add_argument("out_plan", type=Path)
    parser.add_argument(
        "--labels",
        action="append",
        default=[],
        help="extra hexadecimal addresses, comma separated",
    )
    parser.add_argument(
        "--boot-chain",
        action="store_true",
        help="add the default boot-chain label set",
    )
    args = parser.parse_args()

    document = json.loads(args.in_plan.read_text())
    definition = document["board"]["definition"]
    labels = set(definition.get("labels") or [])
    if args.boot_chain:
        labels.update(BOOT_CHAIN)
    for group in args.labels:
        for text in group.split(","):
            text = text.strip()
            if text:
                labels.add(int(text, 0))
    definition["labels"] = sorted(labels)
    args.out_plan.write_text(json.dumps(document, indent=2) + "\n")
    print(f"{args.out_plan}: {len(labels)} labels")


if __name__ == "__main__":
    main()