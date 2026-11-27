# Roadmap

The goal is a custom firmware for the X-Pro3 that boots from an SD card and
changes something visible, plus an emulator good enough to develop it without
touching a camera. This page states how far each half has got and what the next
step actually requires, separating what was measured from what is a guess.

## Where it stands

| piece | state |
| --- | --- |
| build the stock base from the official update | **done**, hashes pinned |
| recipe format, guarded builder, validator | **done**, tested both ways |
| fast SD loader for the X-Pro3 | **built**, reproduces bit for bit, **never run on a camera** |
| emulator that runs the stock image | **done**, reaches storage init and beyond |
| emulator that can show a menu | **no**: no application task is created |
| a firmware modification that changes behaviour | **not started** |

The two halves are independent, and the second is the one that gates the first.

## Stage A — a boot mechanism

*Built.* The X-Pro3 loader shares code with the X-T3 at every fast-loader patch
site, and `build_xpro3_fast_loader.py` transfers the X-T3 recipe's 3 722 bytes of
loader code after verifying that identity. The output is pinned by hash in
`docs/BUILD.md`.

What is missing is not code but a run. Nothing here has been tried on a body,
and the build record says so. The honest next step is a camera and a recovery
card, not more source analysis.

## Stage B — make the firmware's own tasks run

This is the lever that unlocks everything visible, and it is the part the
emulator exists for.

Measured on the stock image:

- `TSK_ROOT` registers **167** task descriptors through `0x4BE9C`, which writes
  into the registry at `0x7A944` and returns 0. It is a registry insert, not
  `tx_thread_create`.
- The start loop at `0x11635E4` calls it with `bl`, then `add`, `cmp`, `bne` —
  it never reads the result.
- ThreadX ends up with **11** threads: `timer`, five `execcpu`, four idles and
  `root`. `TSK_UILIB` (`0x36`) and `TSK_LCDEVF` (`0x37`) are registered and have
  none.
- `0x114F798` is the function that reaches `tx_thread_create`. It has 90 call
  sites; **38 are in the second FFLZ segment and referenced by nothing in the
  image**, which is the shape of entry points installed from outside it.

A candidate modification follows directly: make one of the registered tasks
become a thread, and watch the emulator. But which entry point, with which
stack and priority, is not established. The descriptor written by `0x4BE9C` is
`0x63168 + (id-1)*0x14`, and nothing has yet decoded that structure. Patching it
blind would produce a crash loop, which is why the emulator has to come first.

The experiment, in order:

1. Decode the 20-byte descriptor `0x4BE9C` stores, from the stock run.
2. Find which fields `0x114F798` consumes, and in what order.
3. Patch the start loop so one id — `TSK_UILIB` (`0x36`) — reaches
   `tx_thread_create`.
4. Run it in the emulator and read the milestone table: does the LCDC get
   programmed? Does `outputs` stop being empty?

Step 4 is the whole point of `bench/`. `docs/CORRECTIONS-2026-11-27.md` §4–5
records why no other path reaches the display code.

## Stage C — something a user can see

Only meaningful once Stage B runs, because every visible mod needs a task that
draws. Two families are worth planning for, and the X-T3 custom firmware
(`johnborillo/xt3-cfw`, MIT) shows both are achievable on an XP4 body:

- **film rows**: extra entries in the film lists, backed by 16×16×16 colour
  tables, with the official pipeline left intact;
- **text and icons**: wrappers that answer ids past the official range and pass
  everything else through.

The X-Pro3 side of that work is a porting problem, and its scale is measured:
`evidence/hook-comparison-x-pro3.md` compares all 371 guarded X-T3 hook sites
against this image. Of the whole set, **26 match at exactly one address** and
**126 do not match at all**. Restricted to the substantial sites — 16 bytes or
more, the ones that actually identify a function — **1 matches uniquely, 16 have
several candidates, and 36 are absent**. So a direct port covers a fraction of a
hook set and nothing more; the rest has to be found in the X-Pro3's own code.

What Stage C needs before any code is written:

- the X-Pro3 addresses of the film-list tables and the colour pipeline's
  per-row tables;
- a free RAM region equivalent to the X-T3's `0x1509000` room;
- the text and icon lookup functions, and the range check each performs.

None of the three is established for this body yet. `docs/PORTING.md` records
what is shared and what is not.

## What only hardware can settle

The 38 unreachable callers in the second segment. If a RAM dump from a booting
body shows a dispatch table holding them, then Stage B is a matter of pointing
the start loop at that table. If it does not, they belong to a subsystem the
recovery image never starts, and the start loop is the only route. Either way
the answer is a capture, not more static reading: JIG `ff80`, the loader
(`ffinit.bin`), or the `boot_rom` and observation facts the catalog cannot
derive.

## Contributing

A change is a recipe plus a test, not an image:

1. build the stock base (`docs/BUILD.md` §1);
2. write the change as a recipe, with `own` carrying only your code and `copy`
   pointing at stock bytes;
3. `python3 tools/verify_recipes.py recipes/ --base baseline/ffboot.bin`;
4. reproduce a milestone shift in the bench, and pin it in a test;
5. open a pull request with the recipe, the test and the evidence.

Nothing that carries Fujifilm bytes will be merged. That rule is enforced by
the validator, not by trust.

## Safety

Every tool here works on files. Nothing flashes a camera, writes internal
flash, or touches a card. SD boot leaves the camera's own firmware intact, and
FujiMod's recovery card is the way back. A modification that has only been run
in the emulator is labelled as such everywhere it is described.
