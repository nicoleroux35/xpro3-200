# Source inventory for the X-Pro3 port

> The "Where" column records where each source was read during this research.
> None of those checkouts is part of this project; only the citations and the
> MIT-licensed `xpro3-2.00-baseline.json` are redistributed here (see
> checked out locally).

Search performed 2026-11-25 across GitHub, GitLab, Codeberg, SourceHut and the
public web. The goal was to find the missing FujiMod mod source, an X-Pro3 mod
target, or a reusable custom-firmware implementation.

## GitHub

| Repository | Use | Where | Limitation |
| --- | --- | --- | --- |
| `justjake/fujimod` | Official tools, emulator, catalog, recovery builder | checked out locally | Mod firmware is explicitly not open source; no X-Pro3 mod target |
| `justjake/fujimod` branches | Checked all 137 branches | remote | No `mods/`, no X-Pro3 patch source; only UI/recovery branches |
| `johnborillo/xt3-cfw` | Source-available X-T3 5.11 custom firmware | checked out locally | X-T3-specific; fast loader code is reusable after verification |
| `Yiliiiiiiii/fujifilm-xt3-r6-firmware` | Pure-Python X-T3 delta patcher and patch format | checked out locally | X-T3 5.11 only |
| `cdeschenes/fujifilm-xFW` | FWUP decoder/repacker, X-Pro3 baseline | checked out locally | Analysis tool, not a mod runtime |
| `tiredboffin/fffw` | `ff80`, `ffun`, firmware manifests and symbols | checked out locally | Most advanced tools unpublished; no X-Pro3 port |
| `fujihack/fujihack` | RTOS headers, body metadata, generic research | checked out locally | No XP4 X-Pro3 implementation |
| `ssmit523/fujimod-xpro2-research` | Source-only X-Pro2 WB research | checked out locally | X-Pro2, not camera-ready, no firmware |
| `weaksignals-lab/fujimod` | X-Pro3 emulator delivery plan | checked out locally | Fork is 2,269 commits behind upstream; issues only |
| `anxiousdev-200k/xe2-cfw` | Repository claiming Jake's work | checked out locally | Empty repository |
| `petabyt/libfuji` | USB/Wi-Fi/BLE/PTP library | – | Host-side, not firmware |
| `ILFforever/fujifilm-ptp-recipes` | PTP recipe documentation | – | X-Pro3 explicitly fails and needs diagnostics |
| `cisla66/Provino` | X-Pro3 import tool | – | Host-side, read-only |

## GitLab, Codeberg, SourceHut

No public FujiMod mod source or X-Pro3 custom-firmware repository was found.

- GitLab project search for `fujimod` returned no relevant project; the public
  search API requires authentication for full search.
- Codeberg search for `fujimod` returned unrelated Fujifilm photo tools.
- SourceHut search found no FujiMod camera-firmware project.

## Web

Public pages and release notes consistently state that the FujiMod firmware
modification itself is not open source. The published 0.2.2 patch index contains
only X70 1.10. No X-Pro3 patch or mod target is published.

## Conclusion

The missing pieces are not available in another public source tree:

1. FujiMod mod runtime/compiler source.
2. An X-Pro3 mod target.
3. A qualified X-Pro3 emulator.
4. A published X-Pro3 feature patch.

The reusable public material is limited to tooling, X-T3 source as a porting
reference, firmware decoders, and X-Pro3 catalog/recovery data.

## Second sweep, 2026-11-25

A later pass over GitHub and the Chinese platforms (Gitee, GitCode/AtomGit,
CSDN, Bing zh) found several repositories missing above, including an X-Pro3
baseline and the ThreadX task enumeration. See
[UPSTREAM-2026-11-25.md](UPSTREAM-2026-11-25.md) for the list, the Chinese
platform result (no public X-Pro3 work there) and the still-missing items.
