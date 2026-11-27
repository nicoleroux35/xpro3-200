#!/usr/bin/env python3
"""Generate an X-Pro3 XP4 emulator application plan from the FujiMod catalog.

The generated plan is a declared research input, not camera evidence. It adds
catalog-backed display, ADC, GPIO and temperature devices and fills the
remaining peripheral space with raw memory windows so execution can proceed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def complement(ranges: list[tuple[int, int]], begin: int, end: int) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(ranges):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    out: list[tuple[int, int]] = []
    at = begin
    for lo, hi in merged:
        if lo > at:
            out.append((at, lo))
        at = max(at, hi)
    if at < end:
        out.append((at, end))
    return [(lo, hi) for lo, hi in out if hi > lo]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fujimod", type=Path, required=True)
    parser.add_argument("--firmware-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    blocks_dir = args.fujimod / "catalog/soc/xp4/blocks"
    blocks = []
    for path in sorted(blocks_dir.glob("*.json")):
        if path.name.endswith(".generated.json"):
            continue
        data = json.loads(path.read_text())
        if "base" in data and "size" in data:
            blocks.append(data)

    # Only reserve pages owned by a device model this plan actually installs.
    # Other catalog blocks stay as raw memory windows so unknown writes do not
    # stop execution before the display path is reached.
    modeled = {
        "display",
        "movdc",
        "adc",
        "gpio",
        "sensor_command",
        "imaging_receiver",
        "imaging_input_buffer",
    }
    reserved: list[tuple[int, int]] = []
    for block in blocks:
        device = block.get("device")
        model = device.get("model") if isinstance(device, dict) else None
        if model not in modeled:
            continue
        base = int(block["base"])
        size = int(block["size"]) or 4
        reserved.append((base & ~0xFFF, (base + size + 0xFFF) & ~0xFFF))

    # Catalog SRAM and ROM windows are fixed memory regions, not raw MMIO.
    reserved.extend([(0xFFF00000, 0xFFF08000), (0xFFF10000, 0xFFF1E000), (0xFFF1E000, 0xFFF30000)])

    raw = complement(reserved, 0xFF500000, 0xFFFF0000)
    memory_regions = [{"base": lo, "size": hi - lo, "permissions": 7} for lo, hi in raw]

    def block_by_model(model: str) -> list[dict[str, Any]]:
        return [b for b in blocks if isinstance(b.get("device"), dict) and b["device"].get("model") == model]

    lcdc = []
    for block in block_by_model("display"):
        device = block["device"]
        irqs = [int(i["line"]) for i in block.get("interrupts", [])]
        if len(irqs) < 2:
            continue
        lcdc.append([
            int(block["base"]),
            int(device.get("pixel_clock_ticks", 2)),
            irqs[0],
            irqs[1],
            device.get("picture_layout"),
            device.get("video_layout"),
        ])

    movdc = []
    for block in block_by_model("movdc"):
        irqs = [int(i["line"]) for i in block.get("interrupts", [])]
        movdc.append([
            int(block["base"]),
            irqs[0] if irqs else 0,
            int(block["device"].get("reset_ticks", 8)),
            900900,
            128,
        ])

    def block_by_id(name: str) -> dict[str, Any] | None:
        return next((b for b in blocks if b.get("id") == name), None)

    def irq_lines(block: dict[str, Any] | None, output: str) -> list[int]:
        if block is None:
            return []
        return [
            int(i["line"])
            for i in block.get("interrupts", [])
            if i.get("output", "").startswith(output)
        ]

    command = block_by_id("sensor-command")
    receiver = block_by_id("imaging-receiver")
    ibuf = block_by_id("input-buffer")
    imaging = None
    if command and receiver and ibuf:
        normal = irq_lines(receiver, "normal")
        errors = irq_lines(receiver, "error")
        timing = irq_lines(command, "timing")
        raw_dma = irq_lines(receiver, "raw-dma")
        scene = json.dumps({
            "name": "diagnostic-flat-linear-statistics",
            "luma": 4096,
            "samples_per_cell": 1024,
            "black_level": 1024,
            "signal_shift": 2,
        }, separators=(",", ":"))
        imaging = [
            [
                int(command["base"]),
                int(receiver["base"]),
                normal,
                errors,
                timing,
                raw_dma,
            ],
            [900900, 450450, int(command["device"].get("command_ticks", 5400)), 8],
            [81, 8],
            [
                int(ibuf["base"]),
                irq_lines(ibuf, "interrupt")[0] if irq_lines(ibuf, "interrupt") else 106,
                int(ibuf["device"].get("reset_ticks", 8)),
                0xFFF10000,
                int(ibuf["device"].get("bank_bytes", 0x7000)),
                scene,
            ],
        ]

    # Power controller SPI peer. Register inputs follow the checked X100V XP4
    # harness and are declared virtual for X-Pro3.
    spi1 = block_by_id("spi1")
    power_inputs = {
        0: 64511, 1: 0, 2: 0, 3: 520, 4: 640, 5: 0, 6: 0, 16: 4, 21: 0,
        24: 0, 27: 0, 32: 0, 34: 0, 35: 0,
    }
    power_spi = None
    if spi1:
        power_spi = [
            int(spi1["base"]), False, 12, 5, True, power_inputs, 54000000,
        ]

    # Serial NOR backing and DMA wiring from catalog facts.
    serial_flash = block_by_id("serial-flash")
    storage_jedec = None
    storage_geometry = None
    storage_irq = None
    if serial_flash:
        storage_jedec = 2145056
        storage_geometry = [65536, 256, 4096, 512]
        irqs = irq_lines(serial_flash, "interrupt")
        storage_irq = irqs[0] if irqs else 37

    # DMA channel completion lines, read from the catalog rather than guessed.
    # The X-Pro3 firmware arms these lines; declaring other numbers leaves its
    # completion interrupt permanently pending and blocks the storage path.
    # See ../CORRECTIONS-2026-11-27.md.
    dma = block_by_id("dma")
    storage_dma_routes = (
        [int(i["line"]) for i in dma.get("interrupts", [])] if dma else []
    )
    if len(storage_dma_routes) != 16:
        raise SystemExit(
            "catalog dma block must declare 16 channel interrupt lines, "
            f"found {len(storage_dma_routes)}"
        )

    sd_hosts = []
    for block in block_by_model("sd_host"):
        device = block["device"]
        irqs = irq_lines(block, "status")
        sd_hosts.append({
            "options": {
                "base": int(block["base"]),
                "transfer_ticks": int(device.get("transfer_ticks", 8)),
                "clock_ticks": int(device.get("clock_ticks", 8)),
                "rca": 2,
                "ram_bytes": 536870912,
                "high_speed": False,
                "capabilities": int(device.get("capabilities", 0)),
                "capabilities_2": int(device.get("capabilities_2", 0)),
                "slot_and_version": int(device.get("slot_and_version", 0)),
                "vendor_offsets": [int(x) for x in device.get("vendor_offsets", [])],
            },
            "card": {
                "sectors": 4194304,
                "max_dirty_sectors": 65536,
                "partition_start": 2048,
                "sectors_per_cluster": 8,
                "label": "FUJIMOD",
                "read_only_files": [],
            },
            "irq": irqs[0] if irqs else None,
        })

    jpeg_encoder = None
    for block in block_by_model("jpeg_codec"):
        if block.get("id") != "jpeg-encoder":
            continue
        irqs = irq_lines(block, "interrupt")
        jpeg_encoder = {
            "base": int(block["base"]),
            "irq": irqs[0] if irqs else 135,
            "run_ticks": int(block["device"].get("run_ticks", 108000)),
            "memory_type": 0xFFF4A744,
        }

    # Declared virtual external inputs, adapted from the checked X100V harness.
    adc_samples = [2048, 2048, 4095, 4095, 0, 0, 0, 0, 0, 0, 2048, 2048]
    gpio_levels = [8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 20, 6, 0, 0, 0, 3]

    boot_info = bytearray(1488)
    boot_info[320:324] = (4).to_bytes(4, "little")
    (args.firmware_dir / "boot-info.bin").write_bytes(boot_info)
    ffboot = (args.firmware_dir / "recovery-card/ffboot.bin").read_bytes()
    dat = (args.firmware_dir / "FWUP0021.DAT").read_bytes()

    definition: dict[str, Any] = {
        "ram_size": 536870912,
        "cores": 4,
        "discovery": False,
        "cbar": 4294901760,
        "memory_regions": memory_regions,
        "initial_registers": [[[{"Arm32": {"R": 15}}, 0]] for _ in range(4)],
        "adc": [adc_samples, 16],
        "gpio": gpio_levels,
        "temperature": [25000, 5000],
        "lcdc": lcdc,
        "movdc": movdc,
        "imaging": imaging,
        # The following contracts are researched below but not yet enabled:
        # their device-owner windows conflict with the page-aligned raw MMIO
        # windows needed to reach the display path.
        "power_spi": power_spi,
        "storage_jedec": storage_jedec,
        "storage_geometry": storage_geometry,
        "storage_irq": storage_irq,
        "storage_dma_routes": storage_dma_routes,
        "sd_hosts": sd_hosts,
        "jpeg_encoder": jpeg_encoder,
    }

    plan = {
        "configuration_id": "xpro3-200-handoff",
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
        "lcdc": len(lcdc),
        "movdc": len(movdc),
        "imaging": imaging is not None,
        "sd_hosts": len(sd_hosts),
        "jpeg_encoder": jpeg_encoder is not None,
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
