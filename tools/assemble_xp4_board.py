#!/usr/bin/env python3
"""Assemble a complete X-Pro3 XP4 emulator board definition.

Device-owner windows are taken from the checked XP4 device contracts. Raw MMIO
windows are the page-aligned complement; register banks cover the within-page
gaps that cannot be represented by page-aligned raw windows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def page(value: int) -> int:
    return value & ~0xFFF


def merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for lo, hi in sorted(ranges):
        if result and lo <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], hi))
        else:
            result.append((lo, hi))
    return result


def subtract(ranges: list[tuple[int, int]], cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for lo, hi in ranges:
        at = lo
        for cut_lo, cut_hi in cuts:
            if cut_hi <= at or cut_lo >= hi:
                continue
            if cut_lo > at:
                out.append((at, cut_lo))
            at = max(at, cut_hi)
        if at < hi:
            out.append((at, hi))
    return [(lo, hi) for lo, hi in out if hi > lo]


# Exact device-owner windows observed from the XP4 board assembly.
OWNERS: list[tuple[int, int]] = [
    (0xFFFD8000, 0xFFFD8100),   # serial NOR controller
    (0xF0000000, 0xF8000000),   # serial NOR aperture
    (0xFFFE0000, 0xFFFF0000),   # DMA
    (0xFFF4A500, 0xFFF4A520),   # DMA request mux
    (0xFFF4A800, 0xFFF4A880),   # DMP or remaining lane mux
    (0xFFFC4000, 0xFFFC5000),   # SD host 0
    (0xFFFC8000, 0xFFFC9000),   # SD host 1
    (0xFFF40000, 0xFFF40048),   # ADC
    (0xFFF6C000, 0xFFF6C244),   # sensor command
    (0xFFF69000, 0xFFF69254),   # imaging receiver
    (0xFFF70000, 0xFFF702EC),   # input buffer
    (0xFFF10000, 0xFFF1E000),   # statistics SRAM
    (0xFFF72000, 0xFFF7210C),   # MOVDC0
    (0xFFF73000, 0xFFF7310C),   # MOVDC1
    (0xFFF7A000, 0xFFF7A604),   # LCDC0
    (0xFFFA9000, 0xFFFA9604),   # LCDC1
    (0xFFF41000, 0xFFF41400),   # GPIO
    (0xFFF4700C, 0xFFF47010),   # temperature status
    (0xFFF47028, 0xFFF4702C),   # temperature control
    (0xFFF47810, 0xFFF47854),   # temperature data
    (0xFFF33000, 0xFFF33028),   # power SPI
    (0xFFF3C300, 0xFFF3C350),   # interval timer, eight channels
    (0xFFFA0000, 0xFFFA1000),   # JPEG encoder
    (0xFFF4A744, 0xFFF4A748),   # JPEG memory type
    # Posted control groups: whole 0x100 window each, all twenty of the XP4
    # catalog, including the paired members and 0xfffae000.
    (0xFF701000, 0xFF701100),
    (0xFF701200, 0xFF701300),
    (0xFF701400, 0xFF701500),
    (0xFF701600, 0xFF701700),
    (0xFF701800, 0xFF701900),
    (0xFF701A00, 0xFF701B00),
    (0xFF701C00, 0xFF701D00),
    (0xFF702000, 0xFF702100),
    (0xFF702200, 0xFF702300),
    (0xFF703000, 0xFF703100),
    (0xFF704000, 0xFF704100),
    (0xFF705000, 0xFF705100),
    (0xFF706000, 0xFF706100),
    (0xFF707000, 0xFF707100),
    (0xFF708000, 0xFF708100),
    (0xFF709000, 0xFF709100),
    (0xFF70A000, 0xFF70A100),
    (0xFF70B000, 0xFF70B100),
    (0xFF70C000, 0xFF70C100),
    (0xFFFAE000, 0xFFFAE100),
]

# Pages fully or partly owned by devices. Raw windows avoid these pages.
EXCLUDED_PAGES = merge([(page(lo), page(hi - 1) + 0x1000) for lo, hi in OWNERS])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    firmware = args.firmware_dir
    boot_info = bytearray(1488)
    boot_info[320:324] = (4).to_bytes(4, "little")
    (firmware / "boot-info.bin").write_bytes(boot_info)
    ffboot = (firmware / "recovery-card/ffboot.bin").read_bytes()
    dat = (firmware / "FWUP0021.DAT").read_bytes()

    mmio_pages = EXCLUDED_PAGES
    raw = subtract([(0xFF500000, 0xFFFF0000)], mmio_pages)
    memory_regions = [
        {"base": lo, "size": hi - lo, "permissions": 5 if lo == 0xFFF00000 else 7}
        for lo, hi in raw
    ]

    register_banks = []
    for lo, hi in mmio_pages:
        cuts = [(a, b) for a, b in OWNERS if a < hi and lo < b]
        gaps = subtract([(lo, hi)], merge(cuts))
        register_banks.extend([[a, b] for a, b in gaps])

    power_inputs = {
        0: 64511, 1: 0, 2: 0, 3: 520, 4: 640, 5: 0, 6: 0, 16: 4, 21: 0,
        24: 0, 27: 0, 32: 0, 34: 0, 35: 0,
    }
    sd_card = {
        "sectors": 4194304,
        "max_dirty_sectors": 65536,
        "partition_start": 2048,
        "sectors_per_cluster": 8,
        "label": "FUJIMOD",
        "read_only_files": [],
    }
    sd_options = {
        "base": 0xFFFC4000,
        "transfer_ticks": 8,
        "clock_ticks": 8,
        "rca": 2,
        "ram_bytes": 536870912,
        "high_speed": False,
        "capabilities": 635973808,
        "capabilities_2": 8311,
        "slot_and_version": 16908288,
        "vendor_offsets": [256, 264, 268, 272, 276, 292, 304, 336, 340, 480, 484],
    }
    sd_options_2 = dict(sd_options, base=0xFFFC8000)
    # Posted control requests: the +0x80 word of each control group of the XP4
    # catalog (twenty blocks, including the paired members such as
    # 0xff701200..0xff701c00 and 0xfffae000). Each block is the `[base, base +
    # 0x100)` window of its catalog entry; the stock image posts requests
    # 2/3/5/6 and waits for the low three busy bits of the +0x80 word.
    control_groups = [
        0xFF701000, 0xFF701200, 0xFF701400, 0xFF701600, 0xFF701800,
        0xFF701A00, 0xFF701C00, 0xFF702000, 0xFF702200, 0xFF703000,
        0xFF704000, 0xFF705000, 0xFF706000, 0xFF707000, 0xFF708000,
        0xFF709000, 0xFF70A000, 0xFF70B000, 0xFF70C000, 0xFFFAE000,
    ]
    control_requests = [[base + 0x80, 8] for base in control_groups]
    scene = json.dumps({
        "name": "diagnostic-flat-linear-statistics",
        "luma": 4096,
        "samples_per_cell": 1024,
        "black_level": 1024,
        "signal_shift": 2,
    }, separators=(",", ":"))

    definition: dict[str, Any] = {
        "ram_size": 536870912,
        "cores": 4,
        "discovery": False,
        "cbar": 4294901760,
        "memory_regions": memory_regions,
        "register_banks": register_banks,
        "initial_registers": [[[{"Arm32": {"R": 15}}, 0]] for _ in range(4)],
        "adc": [[2048, 2048, 4095, 4095, 0, 0, 0, 0, 0, 0, 2048, 2048], 16],
        "gpio": [8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 20, 6, 0, 0, 0, 3],
        "temperature": [25000, 5000],
        "lcdc": [
            [0xFFF7A000, 2, 112, 113, "abgr8888-straight", "yycbcr422"],
            [0xFFFA9000, 2, 117, 118, "abgr8888-straight", "yycbcr422"],
        ],
        "movdc": [[0xFFF72000, 107, 8, 900900, 128], [0xFFF73000, 108, 8, 900900, 128]],
        "imaging": [
            [0xFFF6C000, 0xFFF69000, [296, 298], [297, 297], [102, 100], [97, 98]],
            [900900, 450450, 5400, 8],
            [81, 8],
            [0xFFF70000, 106, 8, 0xFFF10000, 0x7000, scene],
        ],
        "power_spi": [0xFFF33000, False, 12, 5, True, power_inputs, 54000000],
        # XP4 interval timer: eight channels at 0xFFF3C300, each with its own
        # interrupt line from the XP4 catalog block. The stock image programs a
        # channel and measures its decrementing counter, so the bank must count.
        "timer_base": 0xFFF3C300,
        "timer_layout": "xp4",
        "timer_routes": [[channel, 57 + channel] for channel in range(8)],
        # XP4 processor profile: the ARMv7-A identity profile. Without it the
        # board answers no MPIDR, so every core sees affinity 0, none takes the
        # parked-secondary path and all four run the boot core's sequence.
        "pmu_cycles_per_tick": 24,
        "control_requests": control_requests,
        "storage_jedec": 2145056,
        "storage_geometry": [65536, 256, 4096, 512],
        "storage_irq": 37,
        "storage_dma_routes": list(range(32, 48)),
        "sd_hosts": [
            {"options": sd_options, "card": sd_card, "irq": 230},
            {"options": sd_options_2, "card": sd_card, "irq": 237},
        ],
        "jpeg_encoder": {"base": 0xFFFA0000, "irq": 135, "run_ticks": 108000, "memory_type": 0xFFF4A744},
    }

    plan = {
        "configuration_id": "xpro3-200-handoff",
        "flash": "FWUP0021.DAT",
        "images": [
            {"address": 0, "file": "recovery-card/ffboot.bin", "sha256": sha256(ffboot)},
            {"address": 63596, "file": "boot-info.bin", "sha256": sha256(boot_info)},
        ],
        "board": {"kind": "xp4", "definition": definition},
    }
    args.output.write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({
        "firmware_sha256": sha256(dat),
        "memory_regions": len(memory_regions),
        "register_banks": len(register_banks),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
