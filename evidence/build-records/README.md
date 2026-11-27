# Build records

The reports the builders wrote, kept because they are the evidence behind
claims made elsewhere. Neither contains firmware bytes: only addresses,
lengths, booleans and SHA-256 values.

## `fast-loader.json`

Written by `tools/build_xpro3_fast_loader.py` when it built the experimental
X-Pro3 fast loader. Two things in it are worth reading:

- `"camera_tested": false` — it has never run on a body. Every description of
  the loader says so.
- `checks` — seven records, one per operation of the X-T3 recipe. Six are
  `"same": true`, `"applied": true`: at those addresses the X-T3 and X-Pro3
  loaders hold identical bytes, which is what allows the code to be reused.
  The seventh (`op 6`, `0x4785`, 10 bytes) is `"same": false` but
  `"metadata": true`, `"applied": false`: it is the field the X-T3 recipe
  stores its own image size in. The X-Pro3 baseline already holds the right
  value, so the builder leaves it alone and fills the sparse size and rolling
  checksum instead.

`docs/BUILD.md` reproduces this build; the output hashes are pinned there.

## `stock-rebuild.json`

Written by `tools/xpro3_build.py` when it applied `recipes/stock-rebuild.json.xz`
to the stock base. The recipe has zero operations, so base and result are the
same hash: it is the check that the format, the pins and the builder agree. A
builder that silently changed a byte would fail its own target pin.

```bash
python3 tools/xpro3_build.py \
  --recipe recipes/stock-rebuild.json.xz \
  --base baseline/ffboot.bin --output out/ffboot.bin
```
