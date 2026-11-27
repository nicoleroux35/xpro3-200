# Recipes

A recipe is how this project ships a firmware change without shipping firmware.
It names the official update it starts from, the exact bytes it replaces, and
the SHA-256 of the result. Anyone holding the official file can rebuild the
image; nobody needs to download one from here.

| file | what it is | licence |
| --- | --- | --- |
| `stock-rebuild.json.xz` | the identity recipe: base and target are the same stock image, zero operations. It validates the format and the builder end to end. | this project (GPL-2.0) |
| `fast-loader-xt3.json.xz` | the X-T3 fast-loader recipe: seven `own` operations, 3 722 bytes of the loader code. `tools/build_xpro3_fast_loader.py` reuses it for the X-Pro3 after verifying that every patch site is byte-identical between the two loaders. | MIT, `johnborillo/xt3-cfw` at `1ac5136` |

Both files are xz-compressed JSON; the builder accepts either form.

## Applying one

```bash
python3 tools/xpro3_build.py \
  --recipe recipes/stock-rebuild.json.xz \
  --base /path/to/recovery-card/ffboot.bin \
  --output /tmp/rebuilt.bin
```

The builder refuses to run unless the base matches the recipe's pinned size and
SHA-256, every guarded operation matches its `old` hash, and the result matches
the pinned target. It writes a `.build.json` beside the output recording what
was applied. It writes nothing else, and it never touches a camera or a card.

## Where the bytes come from

`base` is always an image derived from an official Fujifilm update by
`fujimod-sd-card sd-card-recovery-build`, so it lives on your disk and not in
this repository. `own` carries only code written by a project (this one or
`xt3-cfw`); `copy` and `write` carry no firmware bytes at all. See
[`../docs/RECIPE-FORMAT.md`](../docs/RECIPE-FORMAT.md) for the exact rules and
for the checks that keep firmware bytes out of a submitted recipe.
