# The recipe format

A recipe is a JSON document, optionally xz-compressed, with the format id
`xpro3-recipe-1`. It describes one firmware image as a list of edits to a
starting image. It is the unit of contribution: a change to the firmware is
published as a recipe, never as an image.

## Document

```jsonc
{
  "format": "xpro3-recipe-1",
  "name": "what this produces, in one line",
  "base":   { "size": 66535424, "sha256": "4806…" },
  "target": { "size": 66535424, "sha256": "…" },
  "ops": [ /* see below, applied in order */ ]
}
```

- `base.size` and `base.sha256` pin the image the recipe starts from. The
  builder refuses any other file. On this camera the base is produced by
  `fujimod-sd-card sd-card-recovery-build xpro3-200 FWUP0021.DAT OUT`, so it is
  reproducible from the official update and is never redistributed here.
- `target.size` and `target.sha256` pin the result. If the rebuilt bytes do not
  match, the builder writes nothing.
- `name` is for humans. It is not parsed.

## Operations

Each operation edits the base at a byte offset and is applied in list order.
Offsets are absolute in the image.

### `own` — code written by a project

```jsonc
{
  "op": "own",
  "at": 12290,
  "data": "base64 of the replacement bytes",
  "old": "optional: sha256 of the bytes being replaced"
}
```

Use `own` only for bytes a person wrote: a hook, a patch, a loader. When `old`
is present the builder checks that the bytes currently at `at` hash to it, so a
recipe cannot silently apply to a different base.

`own` is the only operation that carries payload bytes, which makes it the one
that can be abused to smuggle firmware into a repository. The validator
(`tools/verify_recipes.py`) enforces the policy:

- the total `own` payload may not exceed 8 MiB;
- no single `own` operation may exceed 4 MiB;
- when a base image is supplied, no `own` payload may be equal to the base
  bytes it overwrites — that would be stock content wearing a patch's name.

### `copy` — bytes taken from the base at run time

```jsonc
{ "op": "copy", "at": 4096, "src": 2048, "n": 16, "sha256": "…" }
```

Copies `n` bytes from `src` in the base to `at`. The source is hashed before
use, so a recipe that relies on a stock byte sequence proves which sequence it
expects without containing it. This is how a modification can move a stock
table or duplicate stock code without publishing it.

### `write` — a literal byte sequence

```jsonc
{ "op": "write", "at": 0x200, "bytes": [1, 0, 0, 0] }
```

For short, self-evident values: a length, a flag, a checksum seed. Not for
code — use `own` so the payload can be validated and attributed.

## Applying

```bash
python3 tools/xpro3_build.py --recipe R.xz --base BASE.bin --output OUT.bin
```

The builder refuses to overwrite an existing output, verifies every guard, and
writes `OUT.build.json` with the recipe name, the base and result hashes, and
the list of applied operations. A refusal leaves the filesystem unchanged.

## Validating without firmware

```bash
python3 tools/verify_recipes.py recipes/
```

This checks the format, the pins, the operation shapes, the payload limits and
the overlap rules, and needs neither the official update nor a base image. It is
what CI runs. With `--base BASE.bin` it also checks that the base matches every
pinned size and hash and that no `own` payload duplicates stock bytes.

## Why not just publish the image

Because the image is Fujifilm's firmware, and distributing it is redistribution
of proprietary code. The recipe is the part that is yours: the addresses, the
patches, the code an author wrote. It is also smaller, diffable and reviewable,
which is what makes a change to a camera's firmware something other people can
audit before flashing it.
