# X-Pro3 2.00 emulator — corrections to the 2026-11-26 findings

Supersedes the parts of `EMULATOR-2026-11-26.md` listed below. Everything here
is measured on the stock `FWUP0021.DAT` with the plan named in each section, and
pinned by tests in `apps/xpro3-bench/tests/`.

The 26 November report is kept unchanged as a session record. Three of its
conclusions did not survive further measurement, and one of its premises was
wrong in a way that changed the diagnosis.

## 1. The storage stop was a defect in the *declared plan*, not in the firmware

The 26 November report concluded (§5, §8) that the storage engine "is designed
to be driven by a secondary (EXEC CPU) thread" and that "changing those numbers
will not unblock anything".

Both are wrong. The X-Pro3 firmware arms **GIC line 207** for the storage DMA
completion, targeting core 1. The generated plan declared
`storage_dma_routes = range(32, 48)`, so the emulated DMA controller raised its
completion interrupt on line 32, which this firmware never enables. The
interrupt stayed pending and the completion callback was never dispatched.

The XP4 catalog already declares the correct wiring
(`catalog/soc/xp4/blocks/dma.json`: channels 0..15 on lines **207..222**). The
generator hardcoded `range(32, 48)` instead of reading it.

Measured A/B, plans identical except for that one field, `--execution-policy
exact`, **no firmware patch**:

| `storage_dma_routes` | result |
| --- | --- |
| `32..47` | blocked at `0x109099C` @ 37 397 417 instructions; `0x1090BEC` never entered |
| `207..222` | `0x1090BEC` entered on **core 1** @ 37 404 006; `0x1163754` ("after storage init") @ 52 288 787 |

With the routes corrected, and only declarations added for the two later
refusals (`power_spi_command_output` register 17, `discovery_tx_receiver`), the
run reaches 200 M instructions with `failure: null` and zero aborts, and
425 M guest ticks with 187 M instructions on core 0 and 180 M on core 3.

Consequences for the 26 November report:

- §5's "firmware dispatch design" conclusion is replaced by this one.
- §8's "changing those numbers will not unblock anything" is false; it is
  exactly what unblocks.
- §6's diagnostic patch (forcing the synchronous polling path) is unnecessary.
  It masked the wiring defect.
- §10 item 1 ("make the engine's service thread exist") is withdrawn: nothing
  needed a service thread.

## 2. `0x1090C0C` is not a thread spawner, and `FUN_010916A4` is not a function

The 26 November report listed `0x1090C0C` as the function that "spawns the
engine's service thread through `FUN_0108B118`/`FUN_0108B550`", and listed four
"callers": `0x1091000`, `0x1091098`, `0x10911A0`, `0x1091254`.

Real A32 decoding shows:

- `0x1090C0C` is a three-mode transfer primitive:
  - `current_task_id() != 0 && param_2 != 0` → registers a progress handler
    (`0x1134B94`) and **waits on event `0x100`**;
  - `current_task_id() == 0` → polling loop around `0x1092AD0` / `0x1092E98`;
  - `current_task_id() != 0 && param_2 == 0` → object command through
    `0x108BEEC` / `0x108B118` / `0x108B550`, then **also waits on `0x100`**.
  None of the three creates a thread. `0x108B118` is an object start,
  `0x108B550` an object command; `0x108BEEC` indexes an object table at
  `0x1437D68 + id*16`.
- The four "callers" are four `BL` **sites**, not four functions. They live
  inside `0x1090F70` (two sites), `0x10910B4` (one) and `0x10911D8` (one).
- `0x10916A4` is not a function entry. It falls between the prologues at
  `0x1091598` and `0x109194C`, and no `BL` targets it. The enclosing function
  of the sites the report attributed to "`FUN_010916A4`" is `0x1091598`.

Ghidra had created functions at instruction addresses; the report took those
boundaries as real. That is what produced both the "service thread" reading and
the confusion about which code was reached.

## 3. The queue consumer exists and is interrupt-driven

The completion callback `0x1090BEC` — the only poster of event `0x400` — is
invoked from the soft-interrupt dispatcher, not from a thread:

```
0x1098DEC(line)      ; per-line handler dispatch, reads handler table 0x16A31F0
   -> blx handler
      -> 0x1097DF0(ch)  ; per-channel request consumer: 0x1097B40, 0x1096FD4
         -> blx callback ; == 0x1090BEC
```

Recorded at the moment it fired: `pc = 0x1090BEC`, `core = 1`,
`lr = 0x1098E38` — i.e. back inside `0x1098DEC` after `blx`. That is the
interrupt path the corrected DMA routes deliver on line 207.

## 4. The application tasks are registered but never created

This is the real remaining blocker, and it is in the firmware's own dispatch.

`TSK_ROOT` (`0x1163500`) runs a start loop at `0x11635E4` over ids `1..0xA7`.
Measured across that loop:

| quantity | value |
| --- | ---: |
| `0x1150210` (start-task primitive) entered | 167 |
| `0x1150210` returned `0` | 167 |
| `0x4BEF4` and `0x4BE9C` entered | 167 |
| `0x114F798` (path reaching `tx_thread_create`) entered | 5 |
| registry `0x7A944` slots filled afterwards | 167 |
| ThreadX `THRD` blocks | 11 |

`0x4BE9C` is **not** a thread creation. It writes the caller's descriptor into
`0x63168 + (id-1)*0x14` and stores the pointer in `0x7A944[id-1]`, then
returns `0`. And the loop does `bl`, `add`, `cmp`, `bne` — it never inspects
the return value, so a failure would be silent anyway.

The eleven threads, read from `0x655A4 + (id-1)*0x150`:

| id | name | state |
| --- | --- | --- |
| `0x2B` | `timer` | 3 = SUSPENDED |
| `0x71`..`0x75` | `execcpu` | 3 = SUSPENDED, suspend count 1 |
| `0x9B`..`0x9E` | `idle0..3` | 0 = READY |
| `0x9F` | `root` | 0 = READY |

No application task has a thread. `TSK_UILIB` (`0x36`) and `TSK_LCDEVF`
(`0x37`) are registered and have none.

Of the 23 subsystem init calls that follow the start loop
(`0x11635FC..0x1163744`), exactly **one** reaches `tx_thread_create`:
`0x1163A54`, which calls `0x1143C10`. That function walks a five-entry table at
`0x164C420` holding ids `0x71..0x75` and creates one thread per entry — the
five `execcpu`. No other init creates a thread.

## 5. No frame is published because the LCDC is never programmed

The model publishes a frame when the firmware writes `1` to the LCDC
output-enable register (`base + 4`). Five functions touch the LCDC programming
registers:

| function | role |
| --- | --- |
| `0x1100E9C` | horizontal timing (`+0x14`, `+0x18`), vertical (`+0x20`) |
| `0x11065B8` | horizontal and vertical timing |
| `0x11103B8` | vertical timing |
| `0x110EB94` | output enable (`+4`) |
| `0x110EBC4` | output enable / disable (`+4`) |

None is entered on the unlocked run. The device checkpoint agrees
independently: `outputs: {}` and `frames: 0`, while both LCDC windows exist as
models 11 and 12. The chain above them — `0x10F52F4` (display bring-up) and the
task bodies `0x1107758` / `0x110782C` — is also unentered; those two bodies
have no `BL` caller at all, being ThreadX task entries.

So this is not a missing device model: the LCDC is modelled, its windows are
declared, its registers are recognised, and capture is implemented and tested
in `crates/emulator-xp4-display`.

## 6. The printed menu labels are not in the image

`IMAGE QUALITY`, `FILM SIMULATION`, `MY MENU`, `SHOOTING SETTING`, `AF/MF` and
`SET UP` do not occur in `ffboot.bin` in ASCII, UTF-16LE, UTF-16BE or
Shift-JIS. Neither does any font or glyph atlas:

| search | result |
| --- | --- |
| valid SFNT fonts (table directories validated) | 0 |
| 1-bpp glyph-atlas blocks | none; only zero fill and gradient ramps |
| printed words in any of the five type-6 container regions | 0 |
| zlib streams over 4 KiB in the whole DAT | 0 |

What the image does hold is the internal string table
(`BKUP_DOTLCD_POWOFF_IMAGE_QUAL_FINE`, `DOT_INFO_FILM_PROVIA`,
`DOT_INFO_FILM_ACROS`, …), which is where the setting names come from. The
displayed words are rendered glyphs in a bitmap resource the recovery image
does not carry.

The image *does* contain 632 named UI scenes, 1872 named settings and 105
scanner rows, all extracted and browsable. 42 of the scenes are menus,
including `UILIB_SUB_SCR_RECMENU` (352), `UILIB_SUB_SCR_PLAYMENU` (354),
`UILIB_SUB_SCR_DMENU` (351), `UILIB_SUB_SCR_MENU_MYMENU` (411),
`UILIB_SUB_SCR_RECQMENU` (466) and `UILIB_SUB_SCR_QMENU_CUSTOM_MAIN` (467).

## 7. What remains, and what only hardware can settle

`0x114F798` has 90 `BL` call sites. 52 are in the first FFLZ segment
(`0x00F21000..0x01650000`), which the run executes. 38 are in the second FFLZ
segment (`0x01CE3000..0x02527000`). Both segments are present and executable
in the image: catalog code checks at `0x01F3E380`, `0x01F3EEE4`, `0x01F3E754`
and `0x01F3FD68` match the live RAM bytes.

The 38 callers in the second segment are 38 distinct functions, and none is
reachable from `main()`. None is referenced anywhere in the image either — not
as a 32-bit literal, not through a `movw`/`movt` pair, not with the Thumb bit
masked. That is the shape of entry points installed from outside the loaded
image: a loader table, a flash-resident dispatcher, or a subsystem that never
runs.

No further analysis of `FWUP0021.DAT` can settle who installs them. It needs
one of:

- a RAM dump from a body that boots (JIG `ff80`), which would show the complete
  thread table and who filled it;
- the loader (`ffinit.bin`), if it installs a dispatch table;
- `boot_rom` and `generated_facts.observation` in the catalog, which only a
  capture can produce.

## 8. Reproducing

Tests in `apps/xpro3-bench/tests/` pin every measurement above and skip
themselves when the firmware is absent:

| test | asserts |
| --- | --- |
| `advance.rs` | the guest advances and reaches the `0x400` wait |
| `tasks.rs` | 167 registry entries, 5 threads at that point, `0x36`/`0x37` with none |
| `execcpu.rs` | only `0x1163A54` creates threads; 11 threads total |
| `display.rs` | the five LCDC functions stay unentered; no frame exists |
| `dispatch.rs` | segment map matches the catalog; all 38 unreached callers are in the second segment |
| `catalog.rs` | 632 scenes, 1872 settings, 105 rows, 42 menus with stock ids |
| `window.rs` | the bench draws stock labels only, headless |

```bash
cargo test -p fujimod-xpro3-bench
```

The firmware is not part of this repository. Place `FWUP0021.DAT` beside it and
the tests run; without it they print a skip notice and pass.
