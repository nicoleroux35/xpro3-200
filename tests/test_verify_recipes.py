"""The recipe validator must refuse firmware content and malformed recipes.

No firmware is used: the "stock" base here is a synthetic image, so these tests
run anywhere. Their job is to keep `tools/verify_recipes.py` honest, because it
is the rule that stops a recipe from smuggling a firmware image into a commit.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import verify_recipes  # noqa: E402

BASE = bytes((index * 7) & 0xFF for index in range(0x2000))
SIZE = len(BASE)
DIGEST = hashlib.sha256(BASE).hexdigest()


def document(ops, *, target: str = "0" * 64, base_digest: str = DIGEST):
    return {
        "format": "xpro3-recipe-1",
        "name": "test recipe",
        "base": {"size": SIZE, "sha256": base_digest},
        "target": {"size": SIZE, "sha256": target},
        "ops": ops,
    }


class Validator(unittest.TestCase):
    def check(self, doc, base=BASE):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipe.json"
            path.write_text(json.dumps(doc))
            return verify_recipes.validate(path, base)

    def test_a_small_patch_is_accepted(self):
        data = base64.b64encode(b"\xde\xad\xbe\xef").decode()
        problems = self.check(document([{"op": "own", "at": 0x100, "data": data}]))
        self.assertEqual([], problems)

    def test_writing_stock_bytes_back_is_refused(self):
        # The whole point: a payload identical to the bytes it replaces is
        # firmware content, whatever the recipe calls it. `old` is omitted on
        # purpose — that is what a recipe carrying stock bytes would do.
        data = base64.b64encode(BASE[0x100:0x200]).decode()
        problems = self.check(document([{"op": "own", "at": 0x100, "data": data}]))
        self.assertTrue(any("firmware content" in problem for problem in problems), problems)

    def test_writing_stock_bytes_back_is_refused_when_a_base_is_given(self):
        data = base64.b64encode(BASE[0x100:0x200]).decode()
        problems = self.check(document([{"op": "own", "at": 0x100, "data": data}]), base=BASE)
        self.assertTrue(problems)

    def test_an_oversized_payload_is_refused(self):
        data = base64.b64encode(b"\x90" * (verify_recipes.MAX_OWN_OP + 1)).decode()
        problems = self.check(document([{"op": "own", "at": 0x100, "data": data}]), base=None)
        self.assertTrue(any("over the" in problem for problem in problems), problems)

    def test_an_unknown_operation_is_refused(self):
        problems = self.check(document([{"op": "flash", "at": 0}]))
        self.assertTrue(any("unknown operation" in problem for problem in problems), problems)

    def test_a_target_equal_to_the_base_with_operations_is_refused(self):
        problems = self.check(
            document([{"op": "write", "at": 0x10, "bytes": [1, 2, 3]}], target=DIGEST)
        )
        self.assertTrue(any("target equals base" in problem for problem in problems), problems)

    def test_a_write_past_the_end_is_refused(self):
        problems = self.check(
            document([{"op": "own", "at": SIZE - 2, "data": base64.b64encode(b"\x01" * 8).decode()}])
        )
        self.assertTrue(any("past the end" in problem for problem in problems), problems)

    def test_overlapping_operations_are_refused(self):
        first = {"op": "write", "at": 0x100, "bytes": [1] * 8}
        second = {"op": "write", "at": 0x104, "bytes": [2] * 8}
        problems = self.check(document([first, second]))
        self.assertTrue(any("overlapping" in problem for problem in problems), problems)

    def test_a_copy_without_a_source_hash_is_refused(self):
        problems = self.check(document([{"op": "copy", "at": 0x10, "src": 0x20, "n": 4}]))
        self.assertTrue(any("SHA-256 of its source" in problem for problem in problems), problems)

    def test_a_wrong_base_hash_is_refused_when_a_base_is_given(self):
        problems = self.check(document([]), base=b"\x00" * SIZE)
        self.assertTrue(any("base" in problem for problem in problems), problems)

    def test_a_foreign_format_is_checked_but_not_reformatted(self):
        doc = document([])
        doc["format"] = "xt3-recipe-1"
        self.assertEqual([], self.check(doc))

    def test_an_unknown_format_is_refused(self):
        doc = document([])
        doc["format"] = "something-else"
        problems = self.check(doc)
        self.assertTrue(any("expected format" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
