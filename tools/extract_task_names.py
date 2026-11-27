#!/usr/bin/env python3
"""Extract the X-Pro3 2.00 `TSK_*` task-name table from the firmware itself.

The table is a run of NUL-separated ASCII names beginning with `TSK_UI` in the
first decompressed segment, at virtual address 0x1310ff4 for FWUP0021.DAT. Its
order is the task-id enumeration: index 0 is `TSK_UI`, and the 152nd entry is
`TSK_TOTAL`.

This is why the table must be *extracted*, not copied from a neighbouring
generation: the same names carry different ids between versions (X100V 3.01 puts
`TSK_UILIB` at 0x37 and `TSK_LCDEVF` at 0x38; X-Pro3 2.00 puts them at 0x36 and
0x37), and X-T4 2.12 inserts AAC tasks that shift everything after 0x24.

Usage:
  tools/extract_task_names.py SEGMENT.bin OUTPUT.txt [--load 0xf21000] [--at 0x1310ff4]
"""

from __future__ import annotations

import argparse
from pathlib import Path

# First `TSK_UI` in the X-Pro3 2.00 first segment. The segment itself loads at
# 0xF21000, so this is a virtual (RAM) address.
DEFAULT_AT = 0x1310FF4
DEFAULT_LOAD = 0xF21000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("segment", type=Path, help="decompressed segment holding the table")
    parser.add_argument("output", type=Path)
    parser.add_argument("--load", type=lambda v: int(v, 0), default=DEFAULT_LOAD,
                        help="load address of the segment (default 0xf21000)")
    parser.add_argument("--at", type=lambda v: int(v, 0), default=DEFAULT_AT,
                        help="virtual address of the first TSK_ name (default 0x1310ff4)")
    args = parser.parse_args()

    segment = args.segment.read_bytes()
    offset = args.at - args.load
    if not 0 <= offset < len(segment):
        raise SystemExit(f"{args.at:#x} is outside the segment's {args.load:#x} extent")

    names: list[str] = []
    cursor = offset
    while cursor < len(segment):
        if segment[cursor] == 0:
            cursor += 1
            continue
        end = segment.find(b"\x00", cursor)
        if end < 0:
            break
        name = segment[cursor:end].decode("ascii", "replace")
        if not name.startswith("TSK_"):
            break
        names.append(name)
        cursor = end + 1

    if not names or names[0] != "TSK_UI":
        raise SystemExit(f"no TSK_ table at {args.at:#x} (first entry was {names[:1]})")

    args.output.write_text("".join(f"{index:02x} {name}\n" for index, name in enumerate(names)))
    print(f"{len(names)} task names from {args.at:#x} -> {args.output}")
    print(f"  first {names[0]}, last {names[-1]}")


if __name__ == "__main__":
    main()