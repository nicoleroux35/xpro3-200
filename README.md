# X-Pro3 2.00 — emulator bench, findings and tooling

Everything here is about one camera and one file: the **Fujifilm X-Pro3 2.00**
firmware, `FWUP0021.DAT`, 50 087 104 bytes, SHA-256
`30ca22af2e1341c65d8f0637cc5e3ec675628cee8f517de0f1275bb5725c9f39`.

The project has three parts:

| part | what it is |
| --- | --- |
| [`bench/`](bench/xpro3-bench/README.md) | a desktop bench that runs the stock firmware in the FujiMod XP4 emulator and shows what it does |
| [`docs/`](docs/CORRECTIONS-2026-11-27.md) | the findings, including corrections to earlier conclusions |
| [`evidence/`](evidence/) + [`tools/`](tools/) | the decompiled evidence and the dependency-free scripts that regenerate every number |

**No Fujifilm firmware is distributed here.** Every tool and test takes the
update file as an argument, and the bench's firmware-dependent tests skip
themselves when it is absent.

## What was measured

The stock X-Pro3 2.00 firmware runs its ThreadX kernel in the emulator, reaches
storage init, and then stops. Three defects explain why, and none of them is a
missing device model:

1. **The storage stop was a wiring mistake in a generated plan.** The X-Pro3
   firmware arms GIC line **207** for its storage DMA completion; the plan
   generator declared lines `32..47`. The completion interrupt therefore stayed
   pending forever. With the routes corrected to the catalog's `207..222` — and
   **no firmware patch** — the completion callback runs on core 1 at
   37 404 006 instructions and storage init finishes at 52 288 787.
2. **The application tasks are registered but never created.** `TSK_ROOT`
   inserts 167 task descriptors into the registry at `0x7A944`, and the
   function that does it (`0x4BE9C`) is a registry insert, not a thread create.
   ThreadX ends up with 11 threads: `timer`, five `execcpu`, four idles and
   `root`. `TSK_UILIB` and `TSK_LCDEVF` are registered and have none.
3. **The display controller is never programmed.** Five functions touch the
   LCDC; none is entered, so the output-enable bit is never written and no
   frame is published. The LCDC model itself is complete.

The five `execcpu` threads exist but suspend on a message queue and are never
resumed. Of the 23 subsystem initialisers that run after the start loop,
exactly one creates threads (`0x1163A54` → `0x1143C10`), and it creates only
those five.

### What remains, and what only hardware can settle

`0x114F798` is the function that turns a descriptor into a thread. It has 90
call sites. 52 live in the first FFLZ segment, which the run executes; **38
live in the second segment and are referenced by nothing** — not as a literal,
not through a `movw`/`movt` pair, not with the Thumb bit masked. They are the
shape of entry points installed from outside the loaded image.

No further analysis of the file can settle who installs them. That needs a RAM
dump from a body that boots, or the loader, or catalog facts only a capture can
produce.

## The interface, honestly

The menu **structure** is in the image and is browsable: 632 named UI scenes,
1872 named settings, 105 scanner rows, of which 42 scenes are menus
(`UILIB_SUB_SCR_RECMENU` 352, `PLAYMENU` 354, `DMENU` 351, `MENU_MYMENU` 411,
`RECQMENU` 466, `QMENU_CUSTOM_MAIN` 467, …).

The menu **words** are not. `IMAGE QUALITY`, `FILM SIMULATION`, `MY MENU`,
`SHOOTING SETTING` and `SET UP` do not occur in the image in ASCII, UTF-16LE,
UTF-16BE or Shift-JIS, and there is no font or glyph atlas either. What exists
is the internal string table (`BKUP_DOTLCD_POWOFF_IMAGE_QUAL_FINE`,
`DOT_INFO_FILM_PROVIA`, …), which is where the setting names come from.

So the bench shows identifiers, never a translation. A test enforces that no
view can carry an invented printed word.

## Using the bench

The bench is a workspace member of the emulator it drives, so it is installed
into a FujiMod checkout rather than duplicating the emulator:

```bash
git clone --recursive https://github.com/justjake/fujimod.git
./scripts/install-bench.sh ./fujimod
```

Then, with the X-Pro3 update and a plan generated from the catalog:

```bash
cd fujimod
cargo run -p fujimod-xpro3-bench -- \
  --update /path/to/FWUP0021.DAT \
  --application-plan /tmp/xpro3-plan.json \
  --discovery --poke 0xa2ec=4
```

`--view menus` (or `settings`, `inputs`, `screen`) opens on a given tab;
`--check` prints the milestone table as JSON without a window.

Generate the plan first:

```bash
python3 tools/generate_xpro3_plan.py \
  --fujimod ./fujimod \
  --firmware-dir /path/to/firmware-dir \
  --output /tmp/xpro3-plan.json
```

See [`tools/README.md`](tools/README.md) for the plan generator's known
limitation and for `make_diagnostic_plan.py`, which produces a runnable plan.

## Layout

```
bench/xpro3-bench/     the Rust bench and its 13 tests
configs/               the xpro3-200-handoff run configuration
docs/                  findings, corrections, porting notes, source inventory
evidence/              decompiled excerpts, upstream baseline, comparisons
tools/                 dependency-free Python that regenerates the evidence
scripts/               install-bench.sh
LICENSES/              MIT texts of the redistributed third-party material
NOTICE                 every source, its licence, and what was taken
```

## Reading order

1. [`docs/CORRECTIONS-2026-11-27.md`](docs/CORRECTIONS-2026-11-27.md) — the
   current findings.
2. [`docs/SESSION-2026-11-26.md`](docs/SESSION-2026-11-26.md) — the earlier
   session report, kept as a record with a banner listing what was withdrawn.
3. [`docs/PORTING.md`](docs/PORTING.md) — what the X-Pro3 shares with the
   X-T3, X-T4 and X100V, and what it does not.
4. [`docs/SOURCES.md`](docs/SOURCES.md) — the upstream search, and what each
   repository was usable for.
5. [`docs/DUAL-BOOT.md`](docs/DUAL-BOOT.md) — the dual-boot question and its
   preconditions.

## Licences

This project is **GPL-2.0-only**, because the bench links FujiMod's emulator,
which is GPL-2.0-only. Redistributed third-party material is MIT and keeps its
own notice: see [`NOTICE`](NOTICE) and [`LICENSES/`](LICENSES/).

## Safety

Nothing here writes to a camera, an SD card or internal flash. The
recovery-card and fast-loader tools in `tools/` produce offline artifacts that
have **not** been tested on hardware, and say so in their build records.
