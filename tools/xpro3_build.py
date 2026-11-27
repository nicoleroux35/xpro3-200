#!/usr/bin/env python3
"""Guarded X-Pro3 firmware image builder.

Offline only. It never writes firmware, SD cards, USB devices or cameras.
A recipe may contain `own` ops with the SHA-256 of the bytes they replace and
`copy` ops with the SHA-256 of their source. Every op is checked before use and
the final image must match the recipe's pinned target hash.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_recipe(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    data = lzma.decompress(raw) if raw[:6] == b"\xfd7zXZ\x00" else raw
    recipe = json.loads(data)
    if recipe.get("format") != "xpro3-recipe-1":
        raise ValueError(f"{path}: expected xpro3-recipe-1")
    return recipe


def build(recipe: dict[str, Any], base: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    if len(base) != recipe["base"]["size"] or sha256(base) != recipe["base"]["sha256"]:
        raise ValueError("base does not match the recipe's pinned size and SHA-256")
    output = bytearray(base)
    applied: list[dict[str, Any]] = []
    for index, op in enumerate(recipe["ops"]):
        at = int(op["at"])
        kind = op["op"]
        if kind == "own":
            data = base64.b64decode(op["data"])
            if "old" in op:
                old = base[at : at + len(data)]
                if len(old) != len(data) or sha256(old) != op["old"]:
                    raise ValueError(f"op {index}: guarded bytes differ at {at:#x}")
            output[at : at + len(data)] = data
            applied.append({"op": index, "kind": kind, "at": at, "size": len(data)})
        elif kind == "copy":
            src = int(op["src"])
            size = int(op["n"])
            data = base[src : src + size]
            if len(data) != size or sha256(data) != op["sha256"]:
                raise ValueError(f"op {index}: copy source differs at {src:#x}")
            output[at : at + size] = data
            applied.append({"op": index, "kind": kind, "at": at, "src": src, "size": size})
        elif kind == "write":
            data = bytes(int(x) & 0xFF for x in op["bytes"])
            output[at : at + len(data)] = data
            applied.append({"op": index, "kind": kind, "at": at, "size": len(data)})
        else:
            raise ValueError(f"op {index}: unsupported operation {kind}")
    result = bytes(output)
    if len(result) != recipe["target"]["size"] or sha256(result) != recipe["target"]["sha256"]:
        raise ValueError("result does not match the pinned target; nothing written")
    return result, applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recipe = load_recipe(args.recipe)
    image = args.base.read_bytes()
    result, applied = build(recipe, image)
    if args.output.exists():
        raise ValueError(f"output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    report = {
        "recipe": str(args.recipe),
        "base_sha256": sha256(image),
        "result_sha256": sha256(result),
        "result_size": len(result),
        "applied_ops": applied,
        "camera_tested": False,
    }
    args.output.with_suffix(".build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
