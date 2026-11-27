# X-Pro3 analysis bench (`fujimod-xpro3-bench`)

A Rust desktop bench that runs the stock Fujifilm X-Pro3 2.00 firmware on the
project's real XP4 board (Unicorn-backed Cortex-A7) and shows what the guest
actually does. It is a **workbench, not a camera simulator**: it never invents
a screen, and it never patches the firmware to look healthy.

```
apps/xpro3-bench/                (this crate, installed by scripts/install-bench.sh)
  src/lib.rs         guest runner: open the board, drive bounded slices, copy state out
  src/catalog.rs     read-only views of the firmware's own UI records
  src/main.rs        command line + egui window (screen / menus / settings / inputs)
  tests/advance.rs   the measured storage stop, as a regression test
  tests/catalog.rs   the scene, setting and input counts, pinned
  tests/display.rs   the LCDC stays unprogrammed, so no frame exists
  tests/tasks.rs     the 167 tasks are registered, not created
  src/dispatch.rs    segment map and the thread-create callers no code reaches
  tests/dispatch.rs  pins that segment map and the unreached callers
  tests/window.rs    the tabs actually lay out the stock labels, headless
```

## Why it exists

`crates/emulator-gui` and `apps/emulator-gui` already host EXR II and XP5 runs
over WebRTC with a Tauri/SolidJS window. XP4 profiles cannot use that path:

- `fujimod_emulator_boot::open` returns `XP4 uses the application CLI path and
  cannot be opened as a Camera` for `soc == "xp4"` (`crates/emulator-boot/src/lib.rs:893`);
- the desktop launcher only lists cameras whose run starts from
  `RunStart::Loader | RunStart::Rom` **and** declare a `firmware_profile_id`,
  which `configurations/emulator/xpro3-200-handoff/run.json` does not.

This crate is the small, dependency-free way to get a live window for XP4
without a webview. It uses `eframe`/`egui` with the `glow` renderer, so it needs
no `webkit2gtk` development headers.

## Build and run

The emulator CPU crate vendors Unicorn as a git submodule, so a fresh clone
needs it present:

```bash
git clone --recursive https://github.com/justjake/fujimod.git
./scripts/install-bench.sh ./fujimod
cd fujimod
cargo build -p fujimod-xpro3-bench

./target/debug/fujimod-xpro3-bench \
  --update   /path/to/FWUP0021.DAT \
  --application-plan /path/to/xpro3-emulator-plan.json \
  --discovery --poke 0xa2ec=4
```

`--check` opens the board once, prints the milestone table as JSON and exits —
useful in scripts and CI.

Options:

| option | meaning |
| --- | --- |
| `--update FILE` | the X-Pro3 2.00 `FWUP0021.DAT` |
| `--application-plan FILE` | the XP4 startup plan (images, flash, board definition) |
| `--configuration ID` | run configuration, default `xpro3-200-handoff` |
| `--discovery` | enable the discovery hooks the imaging path needs |
| `--poke ADDRESS=WORD` | one pre-boot write, repeatable (`0xa2ec=4` supplies the core count) |
| `--view NAME` | open on `screen`, `menus`, `settings` or `inputs` |
| `--check` | no window: print the milestone table and exit |

The plan must resolve its `flash` and `images` paths itself. The helpers in
`xpro3-cfw-port/tools` (`make_diagnostic_plan.py`) rewrite them to absolute
paths; the bench does not touch the supplied plan, it writes a labelled copy
next to it.

## What the window shows

The central panel has four tabs.

**screen** — the published LCD frame, or an explicit `no scanout published a
frame` message. On the current X-Pro3 profile the message is the correct
answer: the guest executes but no display output presents a frame.

**menus** — every UI scene whose stock name marks it as a menu screen, grouped
by family, with the firmware's own numeric id. 42 of the 632 named scenes are
menus, including `UILIB_SUB_SCR_RECMENU` (352), `UILIB_SUB_SCR_PLAYMENU` (354),
`UILIB_SUB_SCR_DMENU` (351), `UILIB_SUB_SCR_MENU_MYMENU` (411),
`UILIB_SUB_SCR_RECQMENU` (466) and `UILIB_SUB_SCR_QMENU_CUSTOM_MAIN` (467).

**settings** — all 1872 named settings, grouped by their leading stock token
(301 groups), largest first, with numeric ids.

**inputs** — the 105 scanner rows: event code, debug key where the generator
recorded one, claimed/unclaimed target, and the witness (`physical_key`,
`input_kind`, `source`) it was derived from.

`--view screen|menus|settings|inputs` opens on a given tab. A filter box narrows
whichever catalogue tab is open.

### Why the menus show identifiers, not words

The X-Pro3 image contains **no printed menu label as a string**. `IMAGE QUALITY`,
`FILM SIMULATION`, `MY MENU`, `SHOOTING SETTING`, `AF/MF` and `SET UP` are
absent from `ffboot.bin` in ASCII, UTF-16LE and Shift-JIS. What the image does
hold is the internal string table (`BKUP_DOTLCD_POWOFF_IMAGE_QUAL_FINE`,
`DOT_INFO_FILM_PROVIA`, `DOT_INFO_FILM_ACROS`, …), which is what the setting
names come from.

I checked every other place the words could hide, and they are not there
either:

| search | result |
| --- | --- |
| 5 valid SFNT fonts in `ffboot.bin` (`cmap`/`glyf`/`CFF` table directories validated) | **0** — every `OTTO`/`00010000` hit is ASCII noise inside the string table |
| 1-bpp glyph-atlas blocks (windows with repeating 8-byte rows) | only zero-fill and gradient ramps, no glyph rows |
| type-6 container regions of `FWUP0021.DAT`, read with the same inner-header words `crates/firmware/src/sums.rs` uses | 5 regions: image (50 MB), table (16 KiB), trailer (empty), segment-a (372 B), segment-b (184 B) |
| printed menu words in any of those 5 regions | **0** hits, in ASCII, UTF-16LE or UTF-16BE |
| zlib streams over 4 KiB in the whole DAT | **0** |

So the words are not stored as text at all: they are rendered glyphs inside a
bitmap resource the recovery image does not carry. Producing them needs the
display path itself, or a flash/RAM capture of a real body.

### Why no frame is published

The LCDC starts publishing a frame when the firmware writes `1` to its
output-enable register (`base + 4`); `crates/emulator-xp4-display/src/lcdc.rs`
is explicit about it. Five functions in the image touch the LCDC programming
registers:

| function | role |
| --- | --- |
| `0x1100E9C` | horizontal timing (`+0x14`, `+0x18`), vertical (`+0x20`) |
| `0x11065B8` | horizontal and vertical timing |
| `0x11103B8` | vertical timing |
| `0x110EB94` | output enable (`+4`) |
| `0x110EBC4` | output enable / disable (`+4`) |

Measured on the unlocked run (correct DMA routes, `--discovery`, 120 M
instructions): **none of the five is ever entered**. The device checkpoint
confirms it independently — `outputs: {}` and `frames: 0`, while both LCDC
windows exist as models 11 and 12.

The chain above them is also unentered: `0x10F52F4` (display bring-up) and the
two task bodies `0x1107758` / `0x110782C`, which have no `BL` caller at all —
they are ThreadX task entry points, reached only by the scheduler.
`tests/display.rs` pins all of this, so a future fix that finally programs the
LCDC shows up as a failing assertion rather than as a silently changed screen.

### Why the display task never runs: the tasks are registered but never created

This is the same shape of defect as the DMA routes, one layer deeper.

`TSK_ROOT` (`0x1163500`) runs a start loop at `0x11635E4` over task ids
`1..0xA7`. Measured over that loop:

| what | count |
| --- | --- |
| `0x1150210` (start-task primitive) entered | **167** |
| `0x1150210` returned `0` | **167** |
| `0x4BEF4` and `0x4BE9C` entered | **167** |
| `0x114F798` (the path that reaches `tx_thread_create`) entered | **5** |
| registry `0x7A944` slots filled afterwards | **167** |
| ThreadX `THRD` blocks (`0x655A4 + (id-1)*0x150`) | **5** |

The five threads are the four idles (`0x9b..0x9e`) and `root` (`0x9f`). No
application task — `TSK_UILIB` `0x36` and `TSK_LCDEVF` `0x37` included — owns a
ThreadX block, even though both are registered.

Two things explain it, both read from the image:

1. `0x4BE9C` is **not** a thread creation. It writes the caller's descriptor
   into a table (`0x63168 + (id-1)*0x14`) and stores the pointer in
   `0x7A944[id-1]`. It returns `0`. That is why the primitive reports success
   167 times while nothing becomes a thread.
2. The start loop at `0x11635EC` does `bl 0x1150210`, then `add r4,#1`,
   `cmp r4,#0xA8`, `bne` — it **never inspects the return value**. So even a
   failure would be silent.

Real creation has exactly two call sites for `tx_thread_create` (`0x4C04C`):
`0x4C324` inside `0x4C1E0`, which is the one `0x114F798` uses, and `0x4A2BC`
inside `0x4A19C`, which has **no BL caller at all** — it is reached only by an
indirect path. `0x114F798` itself has 90 BL call sites in the image but is
entered only 5 times on this run.

`tests/tasks.rs` pins this: the registry must hold 167 entries, ThreadX must
hold exactly the five blocks, and task `0x36`/`0x37` must be registered with no
thread. A fix that finally creates the application threads fails that test,
which is the intent.

### Where the missing creation would have to come from

`0x114F798` has **90** `BL` call sites, split by the runtime segment they live
in:

| segment | sites | reached on the stock run |
| --- | ---: | --- |
| `0x00F21000..0x01650000` — first FFLZ blob | 52 | some (the 5 that ran) |
| `0x01CE3000..0x02527000` — second FFLZ blob | 38 | **none** |

The two blobs are the `FWUP0021.DAT` FFLZ segments the catalog baseline
declares. Both are present in the image the emulator runs: `bulk.generated.json`
code checks at `0x01F3E380`, `0x01F3EEE4`, `0x01F3E754` and `0x01F3FD68` match
the live RAM bytes, so the second segment really is loaded and executable.

The 38 callers in it are 38 distinct functions. Measured against the whole
image:

- none is reachable from `main()` (`0x1162F14`);
- **none is referenced anywhere** — not as a 4-byte literal, not through a
  `movw`/`movt` pair, not even with the Thumb bit masked off.

That is the signature of entry points installed from outside the code: a
loader table, a flash-resident dispatcher, or a subsystem that never runs. It
is not something the image can reach on its own, and no amount of emulator
fidelity would change it.

`src/dispatch.rs` records the constants and the segment map, and
`tests/dispatch.rs` pins both facts: the segment boundaries match the catalog
baseline, and every unreached caller sits in the second segment.

### What this means for the project

Three separate defects were found in this session, and all three are in the
declared profile or in the firmware's own dispatch — none is a missing device
model:

1. the DMA interrupt routes (`32..47` declared instead of `207..222`) — **fixed
   by correcting the plan**, no firmware patch;
2. the 167 application tasks are registered but never created — the start loop
   calls a registry insert, not `tx_thread_create`, and ignores its result;
3. the only init that creates threads creates the five `execcpu`, which then
   suspend on a message queue and are never resumed.

Reaching the real GUI therefore does not need a better LCDC model. It needs the
X-Pro3 to run the code path that creates its application threads, and that path
is not referenced from anything inside the loaded image.

The consequence is exactly the measured frontier: no `TSK_UILIB`, no
`TSK_LCDEVF`, so nothing ever writes the LCDC output-enable bit, so no frame is
ever published and the menu words never appear on screen.

## How the run is driven

The bench never runs the guest on the UI thread. `Guest` spawns a worker that
opens the board once, then repeatedly calls `application::Started::run_with`
with a `SLICE`-instruction budget. Each call returns on a quiet scheduler
boundary, the worker copies the state into a `Slice`, and the UI picks up the
newest slice on its next repaint. This is why the window can display 87 M+
instructions of guest work without ever blocking a frame.

`SLICE`, `CYCLE` (the host pause between slices) and the quantum all live in
`src/lib.rs` and `open`; they are tuning knobs, not behaviour.

## Passing the storage stop

The declared X-Pro3 plan routes the DMA controller to interrupt lines `32..47`,
but the firmware arms line `207` (targeting core 1) and leaves line `32`
pending-but-masked. The XP4 catalog already declares the right wiring
(`catalog/soc/xp4/blocks/dma.json`: channels 0..15 on lines 207..222).

With `storage_dma_routes = 207..222` instead of `32..47`, and **no firmware
patch at all**, the completion poster `0x1090BEC` is reached on core 1 and the
run continues past `0x1163754` into the imaging path. That is a plan defect,
not a firmware dispatch problem. The full analysis, with the evidence and the
corrections it forced, is in the companion research project's
`docs/CORRECTIONS-2026-11-27.md`.

The bench reports whichever behaviour the plan produces. It does not silently
correct the wiring.

## Scope

Verified on this machine:

- builds against `eframe 0.37` (`glow`, `x11`, `wayland`) with the system
  `gtk3`, `x11`, `wayland-client` and `xkbcommon` present;
- the window opens, repaints continuously, and shows live counters;
- `tests/advance.rs` asserts the measured behaviour: the guest advances past
  30 M instructions, `main()` is observed, and the `0x400` wait at `0x109099C`
  is reached;
- `tests/display.rs` asserts the display frontier: five LCDC programming
  functions stay unentered over 60 M+ instructions and no frame is published;
- `tests/tasks.rs` asserts the task frontier: 167 registry entries, exactly
  five ThreadX threads, and the display tasks registered with no thread;
- `tests/dispatch.rs` asserts the dispatch frontier: the segment map matches
  the catalog baseline and all 38 unreached thread-create callers sit in the
  second FFLZ segment;
- `tests/catalog.rs` pins 632 scenes, 1872 settings, 105 scanner rows and the
  42 menu screens with their stock ids;
- `tests/window.rs` runs a real `egui::Context` headless and asserts the menu
  table is laid out with stock labels only.

Not done here: simulated camera controls (power, dials, shutter). The X-Pro3
catalog has no declared GPIO/ADC wiring for those yet — `catalog/bodies/xpro3/`
holds the 26 documented controls, while the run profile declares only virtual
startup levels. Wiring them without a measurement would be a guess, so the
bench shows none of them.