#!/usr/bin/env python3
"""Check the assembled X-Pro3 plan against the XP4 catalog contracts.

Each assertion here is a blocker that was found by booting the stock image and
reading the stopped board state; the check keeps a regenerated plan from losing
one silently.

Usage:
  tools/verify_plan.py FIRMWARE_DIR [FUJIMOD_DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def equipment(directory: Path) -> dict:
    return json.loads((directory / "xpro3-emulator-plan.json").read_text())["board"]["definition"]


def catalog_control_groups(fujimod: Path) -> set[int]:
    groups = set()
    for path in (fujimod / "catalog/soc/xp4/blocks").glob("control-group-*.json"):
        groups.add(json.loads(path.read_text())["base"])
    return groups


def page(value: int) -> int:
    return value & ~0xFFF


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware_dir", type=Path)
    parser.add_argument("fujimod_dir", type=Path, nargs="?",
                        default=Path(__file__).resolve().parents[2] / "fujimod-xpro3")
    args = parser.parse_args()

    definition = equipment(args.firmware_dir)
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        print(f"{'ok  ' if condition else 'FAIL'} {message}")
        if not condition:
            failures.append(message)

    check(definition["cores"] == 4, "four Cortex-A7 cores")
    check(definition.get("pmu_cycles_per_tick") == 24,
          "XP4 processor profile supplies MPIDR (pmu_cycles_per_tick)")

    interval = args.fujimod_dir / "catalog/soc/xp4/blocks/interval-timer.json"
    if interval.exists():
        block = json.loads(interval.read_text())
        check(definition.get("timer_base") == block["base"]
              and definition.get("timer_layout") == block["device"]["layout"],
              f"interval timer at {block['base']:#x} in the {block['device']['layout']} layout")
        routed = {channel for channel, _ in definition.get("timer_routes", [])}
        lines = {entry["line"] for entry in block["interrupts"]}
        check(len(routed) == len(block["interrupts"]),
              "every interval-timer channel is routed")
        check({line for _, line in definition["timer_routes"]} == lines,
              "interval-timer interrupt lines match the catalog block")

    groups = catalog_control_groups(args.fujimod_dir)
    posted = {address - 0x80 for address, _ in definition["control_requests"]}
    check(groups <= posted,
          f"control groups posted: catalog {len(groups)}, plan {len(posted)}")
    for base in sorted(groups - posted):
        failures.append(f"control group {base:#x} is not posted")

    windows = [(lo, hi) for lo, hi in definition["register_banks"]]
    overlap = [f"{lo:#x}" for lo, hi in windows
               if any(lo < other_hi and other_lo < hi for other_lo, other_hi in windows if (other_lo, other_hi) != (lo, hi))]
    check(not overlap, "register banks do not overlap")

    raw = [(region["base"], region["base"] + region["size"]) for region in definition["memory_regions"]]
    collisions = []
    for lo, hi in raw:
        if any(bank_lo < hi and lo < bank_hi for bank_lo, bank_hi in windows):
            collisions.append(f"{lo:#x}")
    check(not collisions, "raw memory windows avoid every register bank")

    # Device wiring must agree with the catalog block, including its interrupt
    # lines: a wrong line leaves a device's completion interrupt unrouted.
    def block(identifier: str) -> dict | None:
        path = args.fujimod_dir / f"catalog/soc/xp4/blocks/{identifier}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def lines(entry: dict, front: int) -> list[int]:
        return [item["line"] for item in entry["interrupts"]][:front]

    lcdc0 = block("lcdc0")
    if lcdc0:
        controller = next((row for row in definition["lcdc"] if row[0] == lcdc0["base"]), None)
        check(controller is not None and list(controller[2:4]) == lines(lcdc0, 2),
              "lcdc0 base and interrupt lines match the catalog")

    lcdc1 = block("lcdc1")
    if lcdc1:
        controller = next((row for row in definition["lcdc"] if row[0] == lcdc1["base"]), None)
        check(controller is not None and list(controller[2:4]) == lines(lcdc1, 2),
              "lcdc1 base and interrupt lines match the catalog")

    for index, identifier in enumerate(("sd-host-0", "sd-host-1")):
        host = block(identifier)
        if host:
            wired = definition["sd_hosts"][index]
            check(wired["options"]["base"] == host["base"]
                  and wired["irq"] == host["interrupts"][0]["line"],
                  f"{identifier} base and interrupt line match the catalog")

    jpeg = block("jpeg-encoder")
    if jpeg:
        check(definition["jpeg_encoder"]["base"] == jpeg["base"]
              and definition["jpeg_encoder"]["irq"] == jpeg["interrupts"][0]["line"],
              "jpeg encoder base and interrupt line match the catalog")

    for index, identifier in enumerate(("movdc0", "movdc1")):
        engine = block(identifier)
        if engine:
            wired = definition["movdc"][index]
            check(wired[0] == engine["base"] and wired[1] == engine["interrupts"][0]["line"],
                  f"{identifier} base and interrupt line match the catalog")

    print()
    if failures:
        print(f"{len(failures)} contract(s) missing", file=sys.stderr)
        sys.exit(1)
    print("plan carries every blocker found so far")


if __name__ == "__main__":
    main()