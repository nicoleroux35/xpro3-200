#!/usr/bin/env python3
"""Read a stopped XP4 application snapshot without a running board.

`fujimod-emulator boot --save-snapshot` writes the portable checkpoint archive:
CBOR metadata, content-addressed blobs, and a root node whose state is a CBOR
header and whose blobs are the four Cortex-A7 register banks followed by the
sparse page images of the board's memory regions.

A PC trace records the beginning of a run, not its end, so this reader exists to
answer "where did each core actually stop" and "what does RAM hold now". It is
read-only and works on a snapshot file alone.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import cbor2

PAGE = 0x1000
REGISTERS = ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
             "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc")


def page_image(blob: bytes) -> bytes:
    """Rebuild a sparse page image into a flat extent."""
    if blob[:8] != b"FJMPAGE2":
        raise ValueError("not a sparse page image")
    length, stored, blank = struct.unpack_from("<QQQ", blob, 8)
    memory = bytearray([blank]) * length
    offset = 32
    for _ in range(stored):
        index = struct.unpack_from("<Q", blob, offset)[0]
        offset += 8
        span = min(PAGE, length - index * PAGE)
        memory[index * PAGE:index * PAGE + span] = blob[offset:offset + span]
        offset += span
    return bytes(memory)


class Snapshot:
    def __init__(self, path: Path) -> None:
        archive = cbor2.loads(path.read_bytes())
        if archive.get("schema") != 1:
            raise ValueError("unknown snapshot archive schema")
        self.blobs = [blob["data"] for blob in archive["blobs"]]
        self.root = archive["root"]
        self.header = cbor2.loads(self.blobs[self.root["state"]])
        self.cores = len(self.header["per_core"])
        self.regions = self.header["memory"]
        self.memory = {
            base: page_image(self.blobs[self.root["blobs"][self.cores + index]])
            for index, (base, _size, _permissions) in enumerate(self.regions)
        }

    def core(self, index: int) -> dict[str, int]:
        state = cbor2.loads(self.blobs[self.root["blobs"][index]])
        registers = state["architecture"]["cortex-a7"]["registers"]
        return dict(zip(REGISTERS, registers))

    def word(self, address: int) -> int | None:
        for base, size, _permissions in self.regions:
            if base <= address < base + size:
                return struct.unpack_from("<I", self.memory[base], address - base)[0]
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--word", type=lambda value: int(value, 0), action="append",
                        default=[], help="print the word at this physical address")
    args = parser.parse_args()
    snapshot = Snapshot(args.snapshot)
    for core in range(snapshot.cores):
        registers = snapshot.core(core)
        print(f"core {core}: pc={registers['pc']:08x} lr={registers['lr']:08x} "
              f"sp={registers['sp']:08x}")
    for address in args.word:
        value = snapshot.word(address)
        print(f"{address:#010x} = {'unmapped' if value is None else f'{value:#010x}'}")


if __name__ == "__main__":
    main()