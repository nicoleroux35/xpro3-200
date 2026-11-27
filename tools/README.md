# Tools

Dependency-free Python 3 unless noted. Every script takes the Fujifilm update as
an argument; none reads a camera.

| tool | purpose |
| --- | --- |
| `generate_xpro3_plan.py` | build an emulator application plan from the FujiMod catalog |
| `make_diagnostic_plan.py` | the same, plus the declarations and patch a runnable diagnostic plan needs |
| `add_labels.py` | add passive observation points to a plan copy |
| `verify_baseline.py` | compare the update against the upstream baseline |
| `verify_plan.py` | check a plan against the catalog |
| `analyze_hooks.py` | the guarded-hook comparison behind `evidence/hook-comparison-*.md` |
| `match_functions.py` | cross-version function matching |
| `extract_task_names.py` | pull ThreadX task ids and names |
| `read_snapshot.py` | read a portable emulator snapshot (registers, memory) |
| `run_xpro3_emulator.sh` | one-shot emulator invocation |
| `build_xpro3_baseline.sh` | build a stock-derived recovery card (offline artifact) |
| `build_xpro3_fast_loader.py` | build the experimental fast loader from the X-T3 recipe |
| `xpro3_build.py` | shared build helpers |

## `generate_xpro3_plan.py` — known limitation

It emits a **starting** plan, not a bootable one.

It does derive the DMA interrupt lines from
`catalog/soc/xp4/blocks/dma.json` (channels 0..15 on lines `207..222`, which is
what the firmware actually arms — see
[`../docs/CORRECTIONS-2026-11-27.md`](../docs/CORRECTIONS-2026-11-27.md)), and
it refuses a catalog block that does not declare 16 channels.

But the plan that boots also carries per-device window declarations that this
generator does not emit: `timer_base`, `timer_layout`, `timer_routes`,
`register_banks`, `control_requests` and `pmu_cycles_per_tick`. Without them
the board refuses to start with `Overlapping ARM32 physical owners`.

Those values are not measured on an X-Pro3; they are carried from the X100V XP4
harness that the working profile adapted. Reproducing them here would mean
publishing an unmeasured declaration as if it were derived, so they are left to
the profile instead.

## `make_diagnostic_plan.py` — the runnable path

This is the supported way to get a plan that progresses past the storage stop.
It adds the two declarations the later refusals need and optionally a firmware
patch, and it rewrites the plan's file references to absolute paths:

```bash
python3 tools/make_diagnostic_plan.py \
  /path/to/firmware-dir/xpro3-emulator-plan.json \
  /tmp/xp3-diag-plan.json \
  --patch-out /tmp/xp3-diag-patch.toml
```

The two declarations are:

- `power_spi_command_output = {bank: false, register: 17, value: 4096}` — the
  power controller treats register 17 as a writable command output, which the
  model already supports once it is declared;
- `discovery_tx_receiver = {address, request, capacity, offer_at, offer_bytes}`
  — needed for the fixed-destination DMA the imaging path performs. **The
  address and request id are borrowed from the X-T3 profile** and are not
  measured on an X-Pro3. Treat them as a hypothesis.

The patch is diagnostic only and is not needed once the plan declares the DMA
routes correctly; it masks the wiring defect rather than fixing it.
