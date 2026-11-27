# Tools

Dependency-free Python 3 unless noted. Every script takes the Fujifilm update as
an argument; none reads or writes a camera.

## Building an image

| tool | purpose |
| --- | --- |
| `xpro3_build.py` | apply a recipe to a base image, verifying every guard |
| `verify_recipes.py` | validate recipes structurally and enforce the payload policy |
| `build_xpro3_baseline.sh` | wrap `fujimod-sd-card sd-card-recovery-build` to produce the stock base |
| `build_xpro3_fast_loader.py` | build the experimental fast SD loader from the X-T3 recipe |

## Emulating it

| tool | purpose |
| --- | --- |
| `assemble_xp4_board.py` | assemble a complete XP4 board definition (the path that runs) |
| `make_diagnostic_plan.py` | add the two declarations the runnable path needs, and absolute paths |
| `generate_xpro3_plan.py` | catalog-only plan; kept for cross-checking, does not run (see below) |
| `add_labels.py` | add passive observation points to a plan copy |
| `verify_plan.py` | check an assembled plan against the XP4 catalog contracts |

## Evidence

| tool | purpose |
| --- | --- |
| `verify_baseline.py` | cross-check the update against the published baseline |
| `analyze_hooks.py` | the guarded-hook comparison behind `evidence/hook-comparison-*.md` |
| `match_functions.py` | cross-version function matching |
| `extract_task_names.py` | pull the `TSK_*` task-name table |
| `read_snapshot.py` | read a stopped XP4 snapshot (registers, memory) |
| `run_xpro3_emulator.sh` | one-shot emulator invocation |

## Assembling a plan that runs

Two tools produce a board definition, and only one of them runs.

`generate_xpro3_plan.py` declares the catalog devices this run needs and fills
the rest with raw memory windows, but those windows overlap the pages owned by
devices, so the board refuses to start with `Overlapping ARM32 physical owners`.
It is kept because it is the only tool that derives every device from
`catalog/soc/xp4/blocks`, which makes it useful for cross-checking a hand
assembled board. It reads the DMA lines from the catalog and refuses a block
that does not declare sixteen.

`assemble_xp4_board.py` is the one that runs. It takes the same device contracts
and computes the raw windows as the page-aligned complement of the device
owners, with register banks covering the gaps inside an owned page. It also
reads the DMA lines from the catalog (`207..222`), so a plan it emits carries
the wiring the firmware actually arms.

```bash
python3 tools/assemble_xp4_board.py \
  --fujimod ./fujimod \
  --firmware-dir /path/to/firmware-dir \
  --output /tmp/xp3-plan.json

python3 tools/make_diagnostic_plan.py \
  /tmp/xp3-plan.json /tmp/xp3-run.json \
  --patch-out /tmp/xp3-patch.toml
```

`make_diagnostic_plan.py` adds two declarations and rewrites the file references
to absolute paths. Only one of them is a measurement:

- `power_spi_command_output = {bank: false, register: 17, value: 4096}` — the
  stock image writes 4096 to the power controller's command-output register,
  which the model supports once the register is declared writable. The write is
  observed; the declaration only tells the model the register exists.
- `discovery_tx_receiver = {address, request, capacity, offer_at, offer_bytes}`
  — needed by the imaging path's fixed-destination DMA. **The address and the
  request id are borrowed from the X-T3 profile** and are not measured on an
  X-Pro3. Treat them as a hypothesis, not a fact.

The shared `--patch-out` is diagnostic only. It is not needed once a plan
declares the DMA routes correctly, and it masks the wiring defect rather than
fixing it; the repository keeps it so the older runs stay reproducible, not
because it is the recommended route.

## The recipe validator

```bash
python3 tools/verify_recipes.py recipes/
python3 tools/verify_recipes.py recipes/ --base /path/to/base.bin
```

Without `--base` it checks the format, the pins, the operation shapes, the
payload limits and the overlap rules, and needs no firmware — that is what CI
runs. With `--base` it adds the two checks that need an image: that the base
matches every pinned size and hash, and that no `own` payload is byte-identical
to the stock bytes it overwrites. The second check is the one that matters: it
refuses a recipe that carries firmware content under the name of a patch.
