#!/usr/bin/env python3
"""Build an experimental X-Pro3 fast SD loader from the X-T3 loader recipe.

The X-T3 and X-Pro3 FujiMod loaders share the same code at every fast-loader
patch site. This script verifies that before applying the code, then fills the
loader fields and sparse segment table from the supplied X-Pro3 ffboot image.

Output is an offline development artifact, not a camera-tested firmware.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
import re
import struct
import zlib
from pathlib import Path

INIT_FIELDS = 0x4784
FAST_TABLE = 0x3E10
FAST_END = 0x4000
MIN_RUN = 0x10000
PAGE = 0x1000
FIRST = 0x1000
STRIDE = 16


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def segments(image: bytes) -> list[tuple[int, int]]:
    gaps: list[tuple[int, int]] = []
    for match in re.finditer(rb"\x00{%d,}" % MIN_RUN, image):
        start = (match.start() + PAGE - 1) & ~(PAGE - 1)
        end = match.end() & ~(PAGE - 1)
        if end - start >= MIN_RUN:
            gaps.append((start, end))
    result: list[tuple[int, int]] = []
    at = 0
    for start, end in gaps:
        result.append((at, start))
        at = end
    if at < len(image):
        result.append((at, len(image)))
    result = [(start, end) for start, end in result if end > start]
    return [(0, FIRST), (FIRST, result[0][1])] + result[1:]


def fast_pair(template: bytes, image: bytes) -> tuple[bytes, bytes]:
    ranges = segments(image)
    small = b"".join(image[start:end] for start, end in ranges)
    table = b"".join(struct.pack("<2I", start, end - start) for start, end in ranges)
    table += struct.pack("<2I", len(image), 0)
    if len(table) > FAST_END - FAST_TABLE:
        raise ValueError("too many sparse segments")
    rolling = 0
    for offset in range(0, len(small), 4 * STRIDE):
        word = struct.unpack_from("<I", small, offset)[0]
        rolling = (word + (((rolling << 1) | (rolling >> 31)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    loader = bytearray(template)
    loader[FAST_TABLE:FAST_END] = table + bytes(FAST_END - FAST_TABLE - len(table))
    struct.pack_into("<2I", loader, INIT_FIELDS, len(small), rolling)
    return bytes(loader), small


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--xt3-loader", type=Path, required=True)
    parser.add_argument("--xpro3-loader", type=Path, required=True)
    parser.add_argument("--xpro3-image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    recipe = json.loads(lzma.decompress(args.recipe.read_bytes()))
    xt3_loader = args.xt3_loader.read_bytes()
    xpro3_loader = args.xpro3_loader.read_bytes()
    image = args.xpro3_image.read_bytes()
    if len(xt3_loader) != recipe["base"]["size"] or sha256(xt3_loader) != recipe["base"]["sha256"]:
        raise ValueError("X-T3 loader does not match the fast-loader recipe")
    if len(xpro3_loader) != len(xt3_loader):
        raise ValueError("X-Pro3 loader size differs from X-T3")

    patched = bytearray(xpro3_loader)
    checks: list[dict[str, object]] = []
    for index, op in enumerate(recipe["ops"]):
        if op.get("op") != "own":
            raise ValueError(f"op {index}: fast-loader recipe uses unsupported operation")
        replacement = base64.b64decode(op["data"])
        at = int(op["at"])
        overlaps_fields = at < INIT_FIELDS + 12 and at + len(replacement) > INIT_FIELDS
        same = xt3_loader[at : at + len(replacement)] == xpro3_loader[at : at + len(replacement)]
        if not same and not overlaps_fields:
            raise ValueError(f"op {index}: loader code differs at {at:#x}")
        if overlaps_fields:
            # The X-T3 recipe stores its own target-image size here. The X-Pro3
            # baseline already has the correct full-image size, and fast_pair
            # below fills the sparse size and rolling checksum.
            checks.append({"op": index, "address": at, "length": len(replacement), "same": same, "metadata": True, "applied": False})
            continue
        patched[at : at + len(replacement)] = replacement
        checks.append({"op": index, "address": at, "length": len(replacement), "same": same, "metadata": False, "applied": True})

    loader, small = fast_pair(bytes(patched), image)
    if args.output.exists():
        raise ValueError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)
    (args.output / "ffinit.bin").write_bytes(loader)
    (args.output / "ffboot.bin").write_bytes(small)
    report = {
        "status": "experimental-offline-build",
        "camera_tested": False,
        "xpro3_loader_sha256": sha256(xpro3_loader),
        "xpro3_image_sha256": sha256(image),
        "outputs": {
            "ffinit.bin": {"size": len(loader), "sha256": sha256(loader)},
            "ffboot.bin": {"size": len(small), "sha256": sha256(small)},
        },
        "checks": checks,
    }
    (args.output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
