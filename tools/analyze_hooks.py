#!/usr/bin/env python3
"""Compare guarded X-T3 cfw hook sites with one or more XP4 firmware images.

This is an offline portability aid. It never writes firmware, SD cards, USB devices,
or cameras. Fujifilm firmware stays outside the repository and is supplied by path.
"""

from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
import lzma
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_recipe(path: Path) -> dict[str, Any]:
    recipe = json.loads(lzma.decompress(path.read_bytes()))
    if recipe.get("format") != "xt3-recipe-1":
        raise ValueError(f"{path}: expected xt3-recipe-1")
    return recipe


def positions(haystack: bytes, needle: bytes, limit: int = 64) -> list[int]:
    found: list[int] = []
    start = 0
    while len(found) < limit:
        at = haystack.find(needle, start)
        if at < 0:
            break
        found.append(at)
        start = at + 1
    return found


def analyze(recipe: dict[str, Any], xt3_image: bytes, target_name: str, target_image: bytes) -> dict[str, Any]:
    if len(xt3_image) != recipe["base"]["size"] or sha256(xt3_image) != recipe["base"]["sha256"]:
        raise ValueError("X-T3 base does not match the recipe's pinned size and SHA-256")

    rows: list[dict[str, Any]] = []
    counts: collections.Counter[str] = collections.Counter()
    by_length: collections.Counter[tuple[int, str]] = collections.Counter()

    for index, op in enumerate(recipe["ops"]):
        if op.get("op") != "own" or "old" not in op:
            continue
        replacement = base64.b64decode(op["data"])
        at = int(op["at"])
        old = xt3_image[at : at + len(replacement)]
        if len(old) != len(replacement) or sha256(old) != op["old"]:
            raise ValueError(f"op {index}: guarded X-T3 bytes do not match the recipe")
        matches = positions(target_image, old)
        kind = "none" if not matches else "unique" if len(matches) == 1 else "multiple"
        counts[kind] += 1
        by_length[(len(old), kind)] += 1
        rows.append(
            {
                "op": index,
                "xt3_address": at,
                "length": len(old),
                "result": kind,
                "target_matches": matches,
                "old_sha256": op["old"],
                "old_hex": old.hex(),
            }
        )

    substantial = [row for row in rows if row["length"] >= 16]
    substantial_counts = collections.Counter(row["result"] for row in substantial)
    return {
        "target": target_name,
        "target_size": len(target_image),
        "target_sha256": sha256(target_image),
        "counts": dict(counts),
        "substantial_counts": dict(substantial_counts),
        "by_length": [
            {"length": length, "result": kind, "count": count}
            for (length, kind), count in sorted(by_length.items())
        ],
        "rows": rows,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Hook comparison: {report['target']}",
        "",
        f"- Target size: `{report['target_size']}` bytes",
        f"- Target SHA-256: `{report['target_sha256']}`",
        f"- Guarded X-T3 hook sites: `{sum(report['counts'].values())}`",
        f"- Exact unique matches: `{report['counts'].get('unique', 0)}`",
        f"- Ambiguous/multiple matches: `{report['counts'].get('multiple', 0)}`",
        f"- No exact match: `{report['counts'].get('none', 0)}`",
        "",
        "## Substantial guarded sites (16 bytes or more)",
        "",
        f"- Unique: `{report['substantial_counts'].get('unique', 0)}`",
        f"- Multiple: `{report['substantial_counts'].get('multiple', 0)}`",
        f"- None: `{report['substantial_counts'].get('none', 0)}`",
        "",
        "A unique byte match is a candidate for manual review, not proof that the",
        "surrounding function, data layout, or behavior is compatible.",
        "",
        "## Unique matches",
        "",
        "| Recipe op | X-T3 address | Target address | Length |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for row in report["rows"]:
        if row["result"] == "unique":
            lines.append(
                f"| {row['op']} | `{row['xt3_address']:#010x}` | "
                f"`{row['target_matches'][0]:#010x}` | `{row['length']:#x}` |"
            )
    lines.extend(
        [
            "",
            "## Missing substantial sites",
            "",
            "| Recipe op | X-T3 address | Length |",
            "| ---: | ---: | ---: |",
        ]
    )
    for row in report["rows"]:
        if row["result"] == "none" and row["length"] >= 16:
            lines.append(f"| {row['op']} | `{row['xt3_address']:#010x}` | `{row['length']:#x}` |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--xt3-base", type=Path, required=True)
    parser.add_argument("--target", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    recipe = load_recipe(args.recipe)
    xt3_image = args.xt3_base.read_bytes()
    reports = []
    for spec in args.target:
        name, separator, raw_path = spec.partition("=")
        if not separator or not name or not raw_path:
            raise ValueError("--target must be NAME=PATH")
        reports.append(analyze(recipe, xt3_image, name, Path(raw_path).read_bytes()))

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "hook-comparison.json").write_text(json.dumps(reports, indent=2) + "\n")
    for report in reports:
        safe_name = "".join(c.lower() if c.isalnum() else "-" for c in report["target"]).strip("-")
        (args.output / f"hook-comparison-{safe_name}.md").write_text(markdown(report))


if __name__ == "__main__":
    main()
