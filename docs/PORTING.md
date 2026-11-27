# X-Pro3 custom-firmware porting workspace

This directory is an offline research workspace for evaluating a port of the
X-T3 custom firmware to the Fujifilm X-Pro3. It is **not** a firmware release and
contains no Fujifilm firmware bytes.

See [SOURCES.md](SOURCES.md) for the GitHub/GitLab/Codeberg/SourceHut/web search
results and the local copy of every useful source tree.

## Current conclusion

The X-Pro3, X-T3, X-T4 and X100V share the X-Processor 4 SoC family, 32-bit ARM
firmware, the type-6 update container and the same broad SD-boot mechanism. That
makes shared emulator work and data extraction useful, but their firmware images
are not interchangeable.

The public FujiMod catalog records different RAM layouts, section sizes and code
hashes for every body. The X-T3 custom firmware recipe contains 3,889 operations
and 371 guarded hook sites tied to X-T3 5.11 bytes and addresses. Direct reuse on
the X-Pro3 is therefore not possible.

One component is reusable: the X-T3 and X-Pro3 FujiMod `ffinit.bin` loaders are
40,808 bytes each and differ in only 150 bytes. Every code patch site used by the
X-T3 fast-loader recipe is byte-identical; only the loader's image-size,
checksum and segment-table fields differ. An experimental X-Pro3 fast loader was
built offline with those fields regenerated from the X-Pro3 image. It has not
been tested on a camera.

## Verified inputs

All files are stored outside this repository under `../xpro3-firmware/`:

| Input | Size | SHA-256 |
| --- | ---: | --- |
| X-Pro3 2.00 `FWUP0021.DAT` | 50,087,104 | `30ca22af2e1341c65d8f0637cc5e3ec675628cee8f517de0f1275bb5725c9f39` |
| X-T3 5.11 `FWUP0019.DAT` | 50,136,252 | `9f2c75fd8a16a1d71b9218f6dbd3144b1f11820bcecd3a9608c8cda9f25f95a3` |
| X-T4 2.12 `FWUP0024.DAT` | 51,278,280 | `853d273b5603d3a2b93493f0ebd6a762b0b4b6bdc70317777775ae5f8ed93bc5` |
| X100V 3.01 `FPUPDATE.DAT` | 50,137,164 | `18351a9a552c06ec9c70483abca1b74ab2a29fa139f19aef244e178045323591` |

The X-T3 reference custom firmware was rebuilt successfully from
`johnborillo/xt3-cfw` and matches its camera-tested output hashes.

## Reproduce the hook comparison

```sh
python3 tools/analyze_hooks.py \
  --recipe ../xt3-cfw/firmware/recipes/firmware.json.xz \
  --xt3-base ../xpro3-firmware/compare/xt3-recovery/ffboot.bin \
  --target X-Pro3=../xpro3-firmware/recovery-card/ffboot.bin \
  --target X-T4=../xpro3-firmware/compare/xt4-recovery/ffboot.bin \
  --target X100V=../xpro3-firmware/compare/x100v-recovery/ffboot.bin \
  --output reports
```

The generated JSON and Markdown are in `reports/`.

## Emulator status

A new `xpro3-200-handoff` run configuration and application plan let the shared
XP4 emulator execute the stock X-Pro3 2.00 recovery image for 2,000,000 virtual
ticks on four Cortex-A7 cores without aborts. The plan uses declared memory
windows for the peripheral space; these are execution aids, not device models.
No display frame or menu is qualified yet.

## Implemented offline tooling

- `tools/xpro3_build.py` applies guarded `own`/`copy`/`write` operations to a
  pinned X-Pro3 base image and refuses any output that does not match its target
  hash. A stock rebuild recipe reproduces the recovery image byte for byte.
- `tools/build_xpro3_fast_loader.py` reuses the verified XP4 loader code and
  regenerates X-Pro3 image fields and sparse segment table.
- `tools/generate_xpro3_plan.py` derives an XP4 board definition from catalog
  block facts, installs LCDC/MOVDC/ADC/GPIO/temperature/imaging devices and fills
  the remaining peripheral gaps with raw memory windows.
- `tools/analyze_hooks.py` compares the X-T3 recipe's guarded sites against
  several XP4 firmwares.
- `tools/match_functions.py` builds an ARM32 function-family index and reports
  candidate X-Pro3 functions for guarded X-T3 code hooks. The current pass found
  51 code hooks, 16 with an exact normalized match and 8 with a unique function
  candidate. Hook addresses remain ambiguous, so none is accepted as a port.

## Experimental fast-loader artifact

`../xpro3-firmware/xpro3-fast-loader-experimental/` contains an offline-built
sparse `ffboot.bin` and matching `ffinit.bin`. The loader code is reused from the
X-T3 project only after verifying every patch site against the X-Pro3 loader.
The image fields and sparse segment table are generated from the stock X-Pro3
image. This is a development artifact, not a camera-tested release.

## Porting order

1. Establish a reproducible X-Pro3 emulator boot to menus and a saved stock JPEG.
2. Locate the X-Pro3 equivalents of each X-T3 hook and verify the surrounding
   function, not only a short byte sequence.
3. Relocate the custom code and data, fixing every absolute pointer and table.
4. Rebuild X-Pro3 menu rows, text, icons and settings storage.
5. Compare stock behavior before and after each patch in the emulator.
6. Build an SD-boot image only after the emulator gates pass.
7. Hardware testing remains a separate, explicitly authorized step with a
   recovery card and backups. No tool in this workspace writes to a camera.

## Safety

Do not flash an X-T3, X-T4 or X100V firmware to an X-Pro3. Do not treat a stock
X-Pro3 recovery card as a FujiMod feature release. The recovery card only proves
the SD-boot baseline; it does not contain the closed-source FujiMod mods.

## Emulator progress (this pass)

Four missing board contracts were found by reading the stopped board state
rather than the PC trace, because the trace keeps the start of a run:

| Contract | Symptom | Fix in the plan |
| --- | --- | --- |
| XP4 interval timer | core 1 polled `0xFFF3C310` forever measuring a delay | `timer_base` 0xFFF3C300, `timer_layout` `xp4`, eight routed channels |
| ARMv7-A identity profile | every core read MPIDR 0, so none parked and all ran the boot sequence | `pmu_cycles_per_tick: 24` from the catalog `xp4` processor |
| posted control groups | requests to `0xFF701200`..`0xFF701C00` and `0xFFFAE000` never acknowledged | all 20 catalog control groups device-owned and posted |
| core count word | the image's own `0xa2ec` is 1, so the secondaries are never parked | the run supplies the real core count (`--poke 0xa2ec=4`) |

The stock image now leaves the `0x200..0x900` loader region: the boot core
reaches the kernel and the secondaries run their cache-maintenance prologue and
then wait in the kernel's release loop. No scanout frame is published yet.

`tools/read_snapshot.py` decodes a saved CBOR checkpoint (register banks plus
sparse page images), and `tools/verify_plan.py` re-checks every contract above
against a regenerated plan.

### Wiring check

`tools/verify_plan.py` compares the assembled plan with the XP4 catalog blocks:
processor profile, interval timer base/layout/routes, every posted control
group, and the base plus interrupt lines of LCDC0/1, MOVDC0/1, both SD hosts and
the JPEG encoder. It caught `lcdc1` on lines 118/119 (catalog: 117/118) and
`sd-host-1` with no interrupt (catalog: 237).

### Still open

Corrected by reading the board state rather than the PC trace: the cores never
leave the first-stage loader. Both application segments are decompressed into
RAM at their load addresses, but the loader's ThreadX bank holds only four
threads (three idle plus `TSK_FLASH`) out of the image's 152 tasks, and
`TSK_LCDEVF` is never created. The remaining blocker is the loader-to-application
handover, not the display driver and not another bus owner.

`tools/extract_task_names.py` recovers the X-Pro3 task enum from the firmware
(152 names; `TSK_UILIB` 0x36, `TSK_LCDEVF` 0x37) — the ids differ from X100V
3.01 and X-T4 2.12, so the table has to be extracted per version.
