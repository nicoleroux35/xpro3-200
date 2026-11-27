#!/usr/bin/env python3
"""Cross-check FWUP0021.DAT against the published X-Pro3 2.00 baseline.

The baseline comes from `cdeschenes/fujifilm-xFW` (`X-Pro3/analysis/baseline.json`)
and was produced by an independent analysis of the same official file. Comparing
against it catches a corrupted local copy, a wrong assumption about the container
header, or a later local edit that silently changed the image.

Two header lengths appear in the published tooling and they are **not**
interchangeable; each was confirmed against this file:

- `PAYLOAD_HEADER = 0x214` — the offset `fwup.py` hashes from, giving
  `payload_sha256`. The bytes `0x214..0x274` are `0xFF` fill (`ffffffff`,
  `01000000`), i.e. part of the inverted region rather than the container.
- `CHECKSUM_HEADER = 0x274` — the first byte covered by the header checksum:
  `0x20C = 0xFFFFFFFF - sum(de-inverted [0x274:0x274+0x2FC0020])`
  reproduces `0xc54bab2e` exactly.

Segment `file_offset` in the baseline is the absolute file offset of the packed
stream; its FFLZ signature sits 0x0c bytes later (`0x260280`, `0x580280`), and
the segment must be de-inverted before decompression.

Usage:
  tools/verify_baseline.py FIRMWARE_DIR [BASELINE.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PAYLOAD_HEADER = 0x214
CHECKSUM_HEADER = 0x274
CHECKSUM_REGION = 0x2FC0020
FFLZ_PAGE = 0x4000
FFLZ_SIGNATURE = FFLZ_PAGE.to_bytes(4, "little") + (4).to_bytes(4, "little")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def deinvert(data: bytes) -> bytes:
    return bytes(byte ^ 0xFF for byte in data)


def decompress(packed: bytes, fujimod_dir: Path) -> bytes:
    """Run the FujiMod segment decompressor, which expects the de-inverted form."""
    result = subprocess.run(
        ["cargo", "run", "-q", "--locked", "-p", "fujimod-firmware",
         "--bin", "fujimod-decompress"],
        cwd=fujimod_dir,
        input=deinvert(packed),
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip()[:200])
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware_dir", type=Path)
    parser.add_argument(
        "baseline",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1] / "reports/xpro3-2.00-baseline.json",
    )
    parser.add_argument(
        "--fujimod",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "fujimod-xpro3",
        help="FujiMod checkout whose decompressor is used (defaults to the sibling copy)",
    )
    parser.add_argument("--skip-decompress", action="store_true",
                        help="check the container only, without unpacking the segments")
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text())["baseline"]
    image = (args.firmware_dir / "FWUP0021.DAT").read_bytes()
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        print(f"{'ok  ' if condition else 'FAIL'} {message}")
        if not condition:
            failures.append(message)

    check(len(image) == baseline["file_size"],
          f"file size {len(image)} matches the baseline {baseline['file_size']}")
    check(sha256(image) == baseline["sha256"],
          "whole-file SHA-256 matches the baseline")

    header = baseline["header"]
    check(image[0:4] == (6).to_bytes(4, "little"),
          f"container type 6 (version {header['version']})")

    # Model id: 512 bytes of ASCII hexadecimal ('3030303535373131' = b'00055711')
    # holding the eight-byte id followed by '0' padding.
    code_block = image[4:0x204].decode("ascii")[:16]
    model_id = bytes.fromhex(code_block).decode("ascii")
    check(model_id == header["model_ids"][0],
          f"model id {model_id} matches {header['model_ids'][0]}")

    version = (int.from_bytes(image[0x204:0x208], "little"),
               int.from_bytes(image[0x208:0x20C], "little"))
    major, minor = (int(part) for part in header["version"].split("."))
    check(version == (major, minor), f"header version {version} is {header['version']}")

    check(sha256(image[PAYLOAD_HEADER:]) == baseline["payload_sha256"],
          "payload SHA-256 from 0x214 matches payload_sha256")

    checksum_field = int.from_bytes(image[0x20C:0x210], "little")
    region = deinvert(image[CHECKSUM_HEADER:CHECKSUM_HEADER + CHECKSUM_REGION])
    computed = 0xFFFFFFFF - (sum(region) & 0xFFFFFFFF)
    check(checksum_field == computed,
          f"header checksum {computed:#010x} reproduces the stored {checksum_field:#010x}")
    check(checksum_field == header["words"][2],
          "header checksum equals the baseline's recorded word")

    for index, segment in enumerate(baseline["fflz_segments"]):
        start, packed_size = segment["file_offset"], segment["packed_size"]
        packed = image[start:start + packed_size]
        check(len(packed) == packed_size,
              f"segment {index} packed extent {packed_size} read at {start:#x} "
              f"(load {segment['load_addr']:#x})")
        check(deinvert(packed)[0x0c:0x14] == FFLZ_SIGNATURE,
              f"segment {index} FFLZ signature at {start + 0x0c:#x}")
        if args.skip_decompress:
            continue
        try:
            unpacked = decompress(packed, args.fujimod)
        except RuntimeError as error:
            check(False, f"segment {index} decompresses ({error})")
            continue
        check(len(unpacked) == segment["unpacked_size"],
              f"segment {index} unpacks to {len(unpacked)} bytes "
              f"(baseline {segment['unpacked_size']})")
        check(sha256(unpacked) == segment["sha256"],
              f"segment {index} decompressed SHA-256 matches at {segment['load_addr']:#x}")

    for index, raw in enumerate(baseline["raw_images"]):
        chunk = image[raw["file_offset"]:raw["file_offset"] + raw["size"]]
        check(len(chunk) == raw["size"],
              f"raw image {index} extent read at {raw['file_offset']:#x} "
              f"(load {raw['load_addr']:#x})")

    print()
    print(f"content map: {len(baseline['content_map'])} entries; "
          f"RTOS fingerprint: {', '.join(baseline['fingerprints'].get('ThreadX', ['?']))}")
    if failures:
        print(f"{len(failures)} mismatch(es) against the published baseline", file=sys.stderr)
        sys.exit(1)
    print("firmware matches the published X-Pro3 2.00 baseline")


if __name__ == "__main__":
    main()