#!/usr/bin/env python3
"""Validate X-Pro3 recipes without touching firmware.

Two jobs:

1. Structural: every recipe in the given paths has the right format, pins its
   base and target, and uses only known operations with well-formed fields.
2. Policy: the payload a recipe carries stays code-sized, and no `own` operation
   rewrites base bytes with themselves. That is the rule that keeps Fujifilm's
   firmware out of the repository while still allowing patches.

Needs no update file and no base image. `--base` adds the checks that require
one: that the base matches every pin, and that no `own` payload duplicates the
stock bytes it overwrites.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
from pathlib import Path
from typing import Any

FORMAT = "xpro3-recipe-1"
# Recipes redistributed from other projects keep their own format id. They are
# validated for pins and payload policy, but their operation vocabulary is not
# this project's to define.
FOREIGN_FORMATS = {"xt3-recipe-1"}

# A patch is code. Anything larger than this is a payload that should be a
# pointer into the base (`copy`) or should not be published at all.
MAX_OWN_TOTAL = 8 * 1024 * 1024
MAX_OWN_OP = 4 * 1024 * 1024

OPS = {"own", "copy", "write"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    data = lzma.decompress(raw) if raw[:6] == b"\xfd7zXZ\x00" else raw
    return json.loads(data)


def pin(problems: list[str], path: Path, where: str, value: Any) -> tuple[int, str]:
    if not isinstance(value, dict):
        problems.append(f"{path}: {where} must be an object")
        return 0, ""
    size, digest = value.get("size"), value.get("sha256")
    if not isinstance(size, int) or size <= 0:
        problems.append(f"{path}: {where}.size must be a positive integer")
        size = 0
    if not isinstance(digest, str) or len(digest) != 64:
        problems.append(f"{path}: {where}.sha256 must be a 64-character hex string")
        digest = ""
    elif any(c not in "0123456789abcdef" for c in digest):
        problems.append(f"{path}: {where}.sha256 must be lowercase hex")
    return size, digest


def validate(path: Path, base: bytes | None) -> list[str]:
    problems: list[str] = []
    try:
        recipe = load(path)
    except Exception as error:  # noqa: BLE001 - any parse failure is a finding
        return [f"{path}: not readable as a recipe: {error}"]

    if not isinstance(recipe, dict):
        return [f"{path}: the document must be a JSON object"]
    native = recipe.get("format") == FORMAT
    if not native and recipe.get("format") not in FOREIGN_FORMATS:
        problems.append(
            f"{path}: expected format {FORMAT!r}, got {recipe.get('format')!r}"
        )
    if not isinstance(recipe.get("name"), str) or not recipe.get("name"):
        problems.append(f"{path}: name must be a non-empty string")

    base_size, base_digest = pin(problems, path, "base", recipe.get("base"))
    target_size, target_digest = pin(problems, path, "target", recipe.get("target"))
    if base_size and target_size and base_size != target_size:
        problems.append(
            f"{path}: target.size {target_size} differs from base.size {base_size}; "
            "a recipe may only replace bytes in place"
        )
    if base_digest and target_digest == base_digest and recipe.get("ops"):
        problems.append(
            f"{path}: target equals base but the recipe has operations; the target hash is wrong"
        )

    if base is not None:
        if len(base) != base_size:
            problems.append(f"{path}: base is {len(base)} bytes, recipe pins {base_size}")
        elif sha256(base) != base_digest:
            problems.append(f"{path}: base SHA-256 does not match the pin")

    ops = recipe.get("ops")
    if not isinstance(ops, list):
        return problems + [f"{path}: ops must be a list"]

    own_total = 0
    written: list[tuple[int, int]] = []
    for index, op in enumerate(ops):
        label = f"{path}: op {index}"
        if not isinstance(op, dict):
            problems.append(f"{label}: must be an object")
            continue
        kind = op.get("op")
        if kind not in OPS:
            if native:
                problems.append(f"{label}: unknown operation {kind!r}; known are {sorted(OPS)}")
            continue
        at = op.get("at")
        if not native and kind != "own":
            # A foreign recipe's other operations are not this project's format
            # to police; only their carried payload matters here.
            continue
        if not isinstance(at, int) or at < 0:
            problems.append(f"{label}: at must be a non-negative integer")
            continue

        if kind == "own":
            payload = op.get("data")
            if not isinstance(payload, str):
                problems.append(f"{label}: own needs base64 data")
                continue
            try:
                data = base64.b64decode(payload, validate=True)
            except Exception:  # noqa: BLE001
                problems.append(f"{label}: data is not valid base64")
                continue
            if not data:
                problems.append(f"{label}: own payload is empty")
                continue
            if len(data) > MAX_OWN_OP:
                problems.append(
                    f"{label}: own payload is {len(data)} bytes, over the {MAX_OWN_OP} limit; "
                    "publish a pointer (copy) or the code"
                )
            own_total += len(data)
            if at + len(data) > base_size:
                problems.append(f"{label}: writes past the end of the base")
            old = op.get("old")
            if old is not None:
                if not isinstance(old, str) or len(old) != 64:
                    problems.append(f"{label}: old must be a 64-character SHA-256")
                elif base is not None and at + len(data) <= len(base):
                    if sha256(base[at : at + len(data)]) != old:
                        problems.append(f"{label}: base bytes at {at:#x} do not match old")
            # Tested whether or not `old` is present: omitting the guard is
            # exactly what a recipe carrying stock bytes would do.
            if base is not None and at + len(data) <= len(base):
                if base[at : at + len(data)] == data:
                    problems.append(
                        f"{label}: own payload is identical to the stock bytes at {at:#x}; "
                        "this is firmware content, not a patch"
                    )
            written.append((at, at + len(data)))

        elif kind == "copy":
            for field in ("src", "n"):
                if not isinstance(op.get(field), int) or op.get(field) < 0:
                    problems.append(f"{label}: {field} must be a non-negative integer")
            size = op.get("n")
            if isinstance(size, int):
                if size == 0:
                    problems.append(f"{label}: copy length is zero")
                if at + size > base_size:
                    problems.append(f"{label}: copies past the end of the base")
                if isinstance(op.get("src"), int) and op["src"] + size > base_size:
                    problems.append(f"{label}: source runs past the end of the base")
                written.append((at, at + size))
            if not isinstance(op.get("sha256"), str) or len(op.get("sha256", "")) != 64:
                problems.append(f"{label}: copy needs the SHA-256 of its source bytes")

        else:  # write
            values = op.get("bytes")
            if not isinstance(values, list) or not values:
                problems.append(f"{label}: write needs a non-empty byte list")
                continue
            if any(not isinstance(v, int) or not 0 <= v <= 0xFF for v in values):
                problems.append(f"{label}: every written byte must be 0..255")
                continue
            if at + len(values) > base_size:
                problems.append(f"{label}: writes past the end of the base")
            written.append((at, at + len(values)))

    if own_total > MAX_OWN_TOTAL:
        problems.append(
            f"{path}: own payload totals {own_total} bytes, over the {MAX_OWN_TOTAL} limit"
        )

    # Overlapping writes are legal only if they are ordered deliberately, and an
    # overlap is almost always a range mistake. Report it rather than guess.
    for (index, (lo_a, hi_a)), (other, (lo_b, hi_b)) in _pairs(written):
        if lo_a < hi_b and lo_b < hi_a:
            problems.append(
                f"{path}: operations {index} and {other} write overlapping ranges "
                f"{lo_a:#x}..{hi_a:#x} and {lo_b:#x}..{hi_b:#x}"
            )

    return problems


def _pairs(items: list[tuple[int, int]]):
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            yield (a, items[a]), (b, items[b])


def files(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(p for p in path.rglob("*") if p.is_file()))
        else:
            found.append(path)
    return [p for p in found if p.suffix in {".json", ".xz"}]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="recipe files or directories")
    parser.add_argument("--base", type=Path, help="a base image, to check the pins against")
    parser.add_argument("--quiet", action="store_true", help="print only failures")
    args = parser.parse_args()

    base = args.base.read_bytes() if args.base else None
    targets = files(args.paths)
    if not targets:
        print("no recipe files found")
        return 2

    total = 0
    for path in targets:
        problems = validate(path, base)
        if problems:
            total += len(problems)
            for problem in problems:
                print(f"FAIL {problem}")
        elif not args.quiet:
            recipe = load(path)
            carried = sum(
                len(base64.b64decode(op["data"]))
                for op in recipe["ops"]
                if op.get("op") == "own" and "data" in op
            )
            print(
                f"ok   {path}: {len(recipe['ops'])} operations, "
                f"{carried} payload bytes, {recipe['name']}"
            )

    if total:
        print(f"\n{total} problem(s) in {len(targets)} recipe file(s)")
        return 1
    print(f"\n{len(targets)} recipe file(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())