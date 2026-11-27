#!/usr/bin/env python3
"""Find candidate X-Pro3 functions for guarded X-T3 cfw code hooks.

Offline analysis only. It never writes firmware, cards, USB devices or cameras.
Results are candidates for manual reverse engineering, not accepted ports.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN, Cs
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG

MD = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
MD.detail = True

# Little-endian stmdb sp!, {..., lr}: reglist high byte has bit 14 set.
PROLOGUE = re.compile(rb".[\x40-\x7f\xc0-\xff]\x2d\xe9")
# str fp, [sp, #-4]! is the frame-pointer prologue used by older ARM code.
STR_FP = re.compile(rb"\x04\xb0\x2d\xe5")
MAX_FUNCTION = 0x4000
MAX_BACK = 0x2000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized(data: bytes, address: int) -> tuple[str, list[str]] | None:
    tokens: list[str] = []
    total = 0
    for insn in MD.disasm(data, address):
        if insn.size == 0:
            return None
        kinds = []
        for op in insn.operands:
            if op.type == ARM_OP_REG:
                kinds.append("r")
            elif op.type == ARM_OP_IMM:
                # Small constants are semantic; large ones are usually addresses.
                kinds.append(f"i{op.imm:#x}" if 0 <= op.imm < 0x10000 else "iA")
            elif op.type == ARM_OP_MEM:
                kinds.append("m")
            else:
                kinds.append("?")
        tokens.append(f"{insn.mnemonic}:{':'.join(kinds)}:{insn.size}")
        total += insn.size
        if insn.mnemonic in {"bx", "pop", "ldmia"} and ("pc" in insn.op_str or "lr" in insn.op_str):
            break
        if total >= MAX_FUNCTION:
            break
    if len(tokens) < 4:
        return None
    return sha256("\n".join(tokens).encode()), tokens


def is_prologue(data: bytes, address: int) -> bool:
    for insn in MD.disasm(data[address : address + 4], address):
        if insn.mnemonic in {"stmdb", "stmfd", "push"} and "lr" in insn.op_str and "sp" in insn.op_str:
            return True
        if insn.mnemonic == "str" and "fp" in insn.op_str and "sp" in insn.op_str:
            return True
    return False


def function_start(image: bytes, at: int) -> int | None:
    low = max(0, at - MAX_BACK)
    for pos in range(at, low - 1, -4):
        if is_prologue(image, pos):
            return pos
    return None


def build_index(image: bytes, ranges: list[tuple[int, int]]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for address, size in ranges:
        region = image[address : address + size]
        starts = [address + match.start() for pattern in (PROLOGUE, STR_FP) for match in pattern.finditer(region)]
        for start in sorted(set(starts)):
            if start % 4:
                continue
            if not is_prologue(image, start):
                continue
            result = normalized(image[start : start + MAX_FUNCTION], start)
            if result:
                out[result[0]].append(start)
    return out


def trigrams(tokens: list[str]) -> set[tuple[str, str, str]]:
    return set(zip(tokens, tokens[1:], tokens[2:]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--xt3-base", type=Path, required=True)
    parser.add_argument("--xpro3-base", type=Path, required=True)
    parser.add_argument("--xpro3-recipes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    recipe = json.loads(lzma.decompress(args.recipe.read_bytes()))
    xt3 = args.xt3_base.read_bytes()
    xpro3 = args.xpro3_base.read_bytes()
    recipes = json.loads(args.xpro3_recipes.read_text())
    entry = next(r for r in recipes if r["firmware_id"] == "xpro3-200")
    ranges = [(int(r["address"]), int(r["source"]["decoded_size"])) for r in entry["plan"]["regions"]]

    functions: list[dict[str, Any]] = []
    for index, op in enumerate(recipe["ops"]):
        if op.get("op") != "own" or "old" not in op:
            continue
        raw = base64.b64decode(op["data"])
        if len(raw) < 8 or len(raw) % 4:
            continue
        at = int(op["at"])
        old = xt3[at : at + len(raw)]
        if sha256(old) != op["old"]:
            continue
        # The hook bytes must decode completely as ARM instructions.
        decoded = list(MD.disasm(old, at))
        if len(decoded) * 4 != len(old):
            continue
        start = function_start(xt3, at)
        if start is None:
            continue
        result = normalized(xt3[start : start + MAX_FUNCTION], start)
        if not result:
            continue
        digest, tokens = result
        functions.append(
            {
                "op": index,
                "hook_address": at,
                "hook_length": len(old),
                "function_start": start,
                "normalized_sha256": digest,
                "trigrams": sorted(trigrams(tokens)),
            }
        )

    index = build_index(xpro3, ranges)
    rows = []
    for function in functions:
        candidates = index.get(function["normalized_sha256"], [])
        start = function["function_start"]
        hook = function["hook_address"]
        instruction_offset = sum(1 for insn in MD.disasm(xt3[start:hook], start))
        hook_candidates = []
        for candidate in candidates:
            instructions = list(MD.disasm(xpro3[candidate : candidate + MAX_FUNCTION], candidate))
            if len(instructions) <= instruction_offset:
                continue
            hook_candidates.append(instructions[instruction_offset].address)
        rows.append(
            {
                **{k: v for k, v in function.items() if k != "trigrams"},
                "instruction_offset": instruction_offset,
                "xpro3_candidates": candidates,
                "xpro3_hook_candidates": hook_candidates,
            }
        )

    exact = sum(1 for row in rows if row["xpro3_candidates"])
    unique = sum(1 for row in rows if len(row["xpro3_candidates"]) == 1)
    report = {
        "status": "candidate-analysis",
        "camera_tested": False,
        "guarded_code_hooks": len(rows),
        "hooks_with_exact_normalized_match": exact,
        "hooks_with_unique_candidate": unique,
        "hooks_with_unique_hook_address": sum(1 for row in rows if len(row["xpro3_hook_candidates"]) == 1),
        "xpro3_functions_indexed": sum(len(v) for v in index.values()),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
