# Building an image

Every step here runs offline and writes files. None of them writes a camera, an
SD card or internal flash. Two steps are camera-tested (the stock baseline and
FujiMod's own recovery build, both upstream work); the fast loader is **not**.

Hashes below are the ones this repository's tools produce from the official
X-Pro3 2.00 update. They are pins: if your build differs, something changed.

## 0. What you need

- The official **X-Pro3 2.00** update, `FWUP0021.DAT`, 50 087 104 bytes, SHA-256
  `30ca22af2e1341c65d8f0637cc5e3ec675628cee8f517de0f1275bb5725c9f39`.
  From Fujifilm only. Not distributed here.
- A FujiMod checkout, for its recovery builder and (to test) its emulator:

  ```bash
  git clone --recursive https://github.com/justjake/fujimod.git
  cd fujimod && cargo build --release -p fujimod-recovery --bin fujimod-sd-card
  ```

## 1. The stock base

The base image is FujiMod's recovery build of the official update. It is
reproducible and it is the `base` every recipe pins.

```bash
./fujimod/target/release/fujimod-sd-card \
  sd-card-recovery-build xpro3-200 \
  FWUP0021.DAT \
  baseline/            # must not exist yet
```

Produces:

| file | size | SHA-256 |
| --- | ---: | --- |
| `baseline/ffboot.bin` | 66 535 424 | `4806038ec4f727364e9a610b853c00b52fd8de134411b39d4875f314580475a5` |
| `baseline/ffinit.bin` | 40 808 | `2ffa7d99ca1077aeae4657b12bfa5a4e4efdf3b9866fbd3cddc30b711109a063` |
| `baseline/FWUP0021.DAT` | 50 087 104 | the update, copied unchanged |

`scripts/` does not wrap this because the command is one line and the argument
order matters: `xpro3-200` is a recipe id from
`catalog/recovery/recipes.generated.json`, not a body name.

## 2. A modified image, through a recipe

A change is published as a recipe, never as an image. The builder applies it to
your own base and verifies every guard:

```bash
python3 tools/verify_recipes.py recipes/ --base baseline/ffboot.bin
python3 tools/xpro3_build.py \
  --recipe recipes/stock-rebuild.json.xz \
  --base baseline/ffboot.bin \
  --output out/ffboot.bin
```

`stock-rebuild.json.xz` has zero operations, so this reproduces the base byte
for byte — the check that the format, the pins and the builder agree. A real
recipe changes bytes; `docs/RECIPE-FORMAT.md` defines the operations and
`recipes/README.md` lists what is published today.

## 3. The fast SD loader (experimental)

FujiMod's loaders for the X-T3 and the X-Pro3 share code at every fast-loader
patch site. `build_xpro3_fast_loader.py` verifies that, applies the X-T3
recipe's `own` payload to the X-Pro3 loader, and fills the sparse segment table
and rolling checksum from the X-Pro3 image.

```bash
python3 tools/build_xpro3_fast_loader.py \
  --recipe     recipes/fast-loader-xt3.json.xz \
  --xt3-loader <X-T3 ffinit.bin> \
  --xpro3-loader baseline/ffinit.bin \
  --xpro3-image  baseline/ffboot.bin \
  --output out/fast-loader/
```

The X-T3 loader is itself reproducible: build FujiMod's X-T3 5.11 recovery with
recipe id `xt3-511` and the official X-T3 5.11 update, and its `ffinit.bin` is
`c51adc5290e776a38112e2549ff6c6928883d8557a223f210bcf48e75d4a0808`.

Produces:

| file | size | SHA-256 |
| --- | ---: | --- |
| `out/fast-loader/ffinit.bin` | 40 808 | `f6238da1de1a93cf99ebd06dda51f03037ddc18e1dc4c91558776492a701528f` |
| `out/fast-loader/ffboot.bin` | 33 898 496 | `4c27bc0fc0a8a864608226da2b0a037b5f8c2344add765c22fb63d4744ce8d5e` |

**This pair has never been run on a camera.** The build report it writes says
so. Treat it as a development artifact.

## 4. Testing it in the emulator

The bench runs a stock-derived image in FujiMod's XP4 emulator and reports
milestones. Assemble a plan, make it runnable, and drive it:

```bash
python3 tools/assemble_xp4_board.py \
  --fujimod ./fujimod --firmware-dir . --output /tmp/xp3-plan.json
python3 tools/make_diagnostic_plan.py /tmp/xp3-plan.json /tmp/xp3-run.json

cd fujimod
cargo run -p fujimod-xpro3-bench -- \
  --update FWUP0021.DAT \
  --application-plan /tmp/xp3-run.json \
  --discovery --poke 0xa2ec=4 --check
```

`--check` prints the milestone table as JSON and exits. On the stock image the
run reaches storage init and, with the DMA routes the catalog declares,
continues past it:

| milestone | core | instructions |
| --- | ---: | ---: |
| `main()` | 0 | 3 324 610 |
| transfer wait `0x109099C` | 0 | 37 397 417 |
| completion poster `0x1090BEC` | 1 | 37 404 006 |
| after storage init `0x1163754` | 0 | 52 288 787 |

Declare `32..47` instead of `207..222` and the poster never fires: the run sits
on the wait for all 60 000 000 instructions. That difference is a test
(`tests/dma_routes.rs`), not a footnote.

To test a modified image rather than the stock one, point the plan's
`images[0].file` at your `ffboot.bin` and read the same table. A change that
moves a milestone is a change the emulator can see.

## 5. What is not established

- The fast loader is untested on hardware.
- The imaging path's DMA receiver address and request id are borrowed from the
  X-T3 and are not measured here; see `tools/README.md`.
- No application task is ever created, so nothing after the start loop reflects
  a working menu. `docs/CORRECTIONS-2026-11-27.md` records why and what would
  settle it.
