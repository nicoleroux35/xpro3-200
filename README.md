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

## What works, and what does not

This is published unfinished on purpose: the measurements are real, the code
runs, and the parts that are missing are named rather than implied.

### Works

- **The emulator runs the stock firmware.** FujiMod's XP4 emulator boots
  `FWUP0021.DAT`, runs the ThreadX kernel, and reaches storage init. It then
  continues past it — with **no firmware patch** — once the plan declares the
  DMA lines the firmware actually arms. `--check` prints the milestone table as
  JSON; without it you get a window with the firmware's own menus, settings and
  input records, under their internal names.
- **The stock base is reproducible.** `fujimod-sd-card sd-card-recovery-build`
  turns the official update into `ffboot.bin` (`4806…`) and `ffinit.bin`
  (`2ffa…`). Both hashes reproduce here; `tools/verify_baseline.py` re-checks
  the update against the published baseline, container and both segments.
- **A change can be published without publishing firmware.** Recipes carry
  their author's bytes and point at the official image for everything else. The
  builder refuses any unguarded input and any result that misses its pinned
  hash; the validator refuses a payload that duplicates stock bytes.
- **The fast loader is built and reproducible**, bit for bit, from the X-T3
  recipe after verifying that both loaders hold identical code at every patch
  site.
- **15 tests pin the measurements**, and they skip themselves when the firmware
  is absent, so CI is green without it.

### Does not work yet

- **No custom firmware modification exists.** Nothing changes the camera's
  behaviour. The build chain can produce one; the change itself is not written.
- **The emulator cannot show a menu of its own**, because the firmware never
  creates its application tasks — see below. The window browses the firmware's
  own records, not a rendered screen.
- **The fast loader has never been run on a camera.** Every description says so,
  and its build record says `camera_tested: false`.
- **The full run stops at two refusals** unless the plan declares them: the
  power controller's command-output register (observed, only the declaration is
  missing) and the imaging path's fixed-destination DMA receiver, whose address
  is **borrowed from the X-T3 and not measured here**.
- **No frames are produced** (`frames: 0`, `outputs: {}`).

### Why the tasks are never created — decoded

This was an open question in the earlier reports; the chain is now readable in
the image.

- `TSK_ROOT` calls `0x1150210(id, b)` for ids `1..0xA7`, passing **the loop
  counter itself** as `b` (`mov r5, r4` then `mov r1, r5` at `0x11635E0`).
- `0x1150210` builds a **three-word record** on the stack — `{0, b, b}` at
  `fp-0x18` — and hands `&record` to the validator `0x4BEF4`, which reads
  `[r1]` (base), `[r1+4]` (size) and `[r1+8]` (end). Nothing else is read.
- `0x4BEF4` returns **0 on success** and a negative code on refusal. It passes,
  and `0x4BE9C` runs 167 times: it copies `src` into `0x63168+(id-1)*0x14`,
  zero-fills `+0x10`, and stores the pointer in the registry `0x7A944`.
- `0x4BE9C` writes the destination from that source as
  `{src[0], src[4], src[8], src[4], 0}` — note the fourth word mirrors the
  second rather than reading a new one. With `b = 1` that is `{0,1,1,1,0}`.
- So every record holds the *same* `b` it was given, and 166 of the 167 are
  byte-identical. Measured: 2 distinct records out of 167, each slot pointing at
  its own copy.
- **`0x4BEF4` never creates a thread.** It calls only `0x48E14`, `0x48DE8`,
  `0x48EAC`, `0x48F30` and — on success — `0x4BE9C`, a pure copy. The only
  thread-creation path, `0x114F798`, is `tx_thread_create` by name, and it is
  entered exactly **5** times, all through `0x1143C10` for the `execcpu` ids.
  Nothing the start loop calls reaches `0x114F798`.
- The 38 unreachable callers of `0x114F798` remain unreachable: they are in the
  second segment and nothing in the image references them.

The honest reading: the start loop registers records, not threads, and the
thing that would turn a record into a thread is not reached. **No patch is
included for it**, because none has been written and tested. That is the first
real task, and [`docs/ROADMAP.md`](docs/ROADMAP.md) states what it requires.

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
evidence/            decompiled excerpts, upstream baseline, hook comparisons,
                     and the builders' own reports
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
