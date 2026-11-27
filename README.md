# X-Pro3 2.00 — custom firmware, and the emulator to test it

A project to build a custom firmware for the **Fujifilm X-Pro3 2.00** and to
develop it against an emulator instead of a camera. Everything is about one
file: `FWUP0021.DAT`, 50 087 104 bytes, SHA-256
`30ca22af2e1341c65d8f0637cc5e3ec675628cee8f517de0f1275bb5725c9f39`.

**No Fujifilm firmware is distributed here.** Builds start from the official
update, which you supply; changes are published as recipes that carry only the
bytes their author wrote. The emulator's firmware-dependent tests skip
themselves when the update is absent.

## Where it stands

| piece | state |
| --- | --- |
| [emulator bench](bench/xpro3-bench/README.md) | runs the stock image in FujiMod's XP4 emulator; **15 tests** |
| [recipe format](docs/RECIPE-FORMAT.md), [builder](tools/xpro3_build.py), [validator](tools/verify_recipes.py) | done and tested in both directions |
| [stock base](docs/BUILD.md) from the official update | done, hashes pinned |
| [fast SD loader](docs/BUILD.md) for the X-Pro3 | built, reproduces bit for bit, **never run on a camera** |
| a modification that changes behaviour | not started — see [the roadmap](docs/ROADMAP.md) |

The emulator works and is the development loop. The firmware modification is
the next piece of work, and the roadmap explains why the emulator had to come
first.

## Quick start — run the stock firmware

`firmware-dir` is the output of the first step of
[`docs/BUILD.md`](docs/BUILD.md): the stock base built from your own copy of the
official update. It is not in this repository.

```bash
git clone --recursive https://github.com/justjake/fujimod.git
./scripts/install-bench.sh ./fujimod
cd fujimod

python3 ../tools/assemble_xp4_board.py \
  --fujimod . --firmware-dir ../firmware-dir --output /tmp/xp3-plan.json
python3 ../tools/make_diagnostic_plan.py /tmp/xp3-plan.json /tmp/xp3-run.json

cargo run -p fujimod-xpro3-bench -- \
  --update ../firmware-dir/FWUP0021.DAT \
  --application-plan /tmp/xp3-run.json \
  --discovery --poke 0xa2ec=4 --check
```

`--check` prints a milestone table and exits; drop it and you get a window with
the firmware's own menus, settings and inputs, under their internal names.
`--view settings` (or `menus`, `inputs`, `screen`) opens on a tab.

## What the emulator established

The stock image reaches storage init and, given the wiring its own catalog
declares, finishes it. Three things explain everything after that, and none is
a missing device model — the full argument, with instruction counts and
addresses, is in [`docs/CORRECTIONS-2026-11-27.md`](docs/CORRECTIONS-2026-11-27.md).

1. **The storage stop was a defect in a generated plan.** The firmware arms GIC
   line **207** for its DMA completion; the plan declared `32..47`, so the
   interrupt never arrived. With the catalog's `207..222` — and **no firmware
   patch** — the completion runs on core 1 at 37 404 006 instructions and
   storage init finishes at 52 288 787. A test now pins both directions.
2. **167 application tasks are registered and never created.** The start loop
   calls a registry insert, not `tx_thread_create`, and ignores its result.
   ThreadX holds 11 threads, none of them `TSK_UILIB` or `TSK_LCDEVF`.
3. **The display controller is never programmed**, so no frame exists. The LCDC
   model is complete; the firmware never reaches the code that enables it.

That last point is why the emulator matters: `0x114F798`, the function that
reaches `tx_thread_create`, has **38 call sites in the second segment that
nothing in the image references**. A modification that makes one application
task a real thread is the shortest path to a visible screen — and the only way
to test it is to run it.

## Building a modified image

```bash
# stock base, from the official update
./fujimod/target/release/fujimod-sd-card sd-card-recovery-build \
  xpro3-200 FWUP0021.DAT baseline/

# apply a recipe, with every guard checked
python3 tools/verify_recipes.py recipes/ --base baseline/ffboot.bin
python3 tools/xpro3_build.py \
  --recipe recipes/stock-rebuild.json.xz \
  --base baseline/ffboot.bin --output out/ffboot.bin
```

Steps, hashes and the experimental fast loader are in
[`docs/BUILD.md`](docs/BUILD.md). The recipe operations are in
[`docs/RECIPE-FORMAT.md`](docs/RECIPE-FORMAT.md).

## Layout

```
bench/xpro3-bench/   the Rust bench and its 15 tests
configs/             the xpro3-200-handoff run configuration
recipes/             published recipes: the identity check and the fast loader
docs/                findings, build guide, recipe format, roadmap, porting
evidence/            decompiled excerpts, upstream baseline, hook comparisons
tools/               dependency-free Python that builds and verifies everything
scripts/             install-bench.sh
LICENSES/            MIT texts of the redistributed third-party material
NOTICE               every source, its licence, and what was taken
```

## Reading order

1. [`docs/ROADMAP.md`](docs/ROADMAP.md) — what is built, what is next, what only
   hardware can settle.
2. [`docs/BUILD.md`](docs/BUILD.md) — reproduce the base, the loader, and a run.
3. [`docs/CORRECTIONS-2026-11-27.md`](docs/CORRECTIONS-2026-11-27.md) — the
   current findings, including the three earlier conclusions they replace.
4. [`docs/RECIPE-FORMAT.md`](docs/RECIPE-FORMAT.md) — how a change is published
   without publishing firmware.
5. [`docs/PORTING.md`](docs/PORTING.md) and
   [`docs/SOURCES.md`](docs/SOURCES.md) — what the X-Pro3 shares with the X-T3,
   X-T4 and X100V, and where each upstream project was usable.

## Licences

This project is **GPL-2.0-only**, because the bench links FujiMod's emulator,
which is GPL-2.0-only. Redistributed third-party material is MIT and keeps its
own notice: see [`NOTICE`](NOTICE) and [`LICENSES/`](LICENSES/).

## Safety

Nothing here writes to a camera, an SD card or internal flash. The fast loader
and the recovery-card tools produce offline artifacts that have **not** been
tested on hardware, and say so in their build records. SD boot leaves the
camera's own firmware untouched; keep FujiMod's recovery card as the way back.
