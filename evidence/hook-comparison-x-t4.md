# Hook comparison: X-T4

- Target size: `70504448` bytes
- Target SHA-256: `938c8a213673ec8a54856a0d0cea4201248ee05a96d72f9bc569d8bcf256267a`
- Guarded X-T3 hook sites: `371`
- Exact unique matches: `19`
- Ambiguous/multiple matches: `220`
- No exact match: `132`

## Substantial guarded sites (16 bytes or more)

- Unique: `1`
- Multiple: `16`
- None: `36`

A unique byte match is a candidate for manual review, not proof that the
surrounding function, data layout, or behavior is compatible.

## Unique matches

| Recipe op | X-T3 address | Target address | Length |
| ---: | ---: | ---: | ---: |
| 487 | `0x01064285` | `0x0223b881` | `0x4` |
| 2700 | `0x01d4a964` | `0x02051888` | `0x8` |
| 2713 | `0x01d7b410` | `0x04031390` | `0x8` |
| 2756 | `0x01ef2f9c` | `0x02238eb8` | `0x8` |
| 2769 | `0x022006e4` | `0x02063db8` | `0x3` |
| 2773 | `0x02200764` | `0x04116e2b` | `0x3` |
| 2777 | `0x0220191a` | `0x0162446c` | `0x4` |
| 2799 | `0x0344e1c0` | `0x042dd993` | `0x3` |
| 2802 | `0x03455708` | `0x03aec69c` | `0x3` |
| 2806 | `0x0346154c` | `0x039f0500` | `0x3` |
| 2811 | `0x035f703c` | `0x021ad208` | `0x8` |
| 2826 | `0x036cc2b8` | `0x04118620` | `0x4` |
| 2827 | `0x036cced8` | `0x04118620` | `0x4` |
| 2830 | `0x036d052a` | `0x03d2a8c2` | `0x8` |
| 2887 | `0x036d0a3c` | `0x03d2ae08` | `0x8` |
| 2895 | `0x036d0ab4` | `0x03d2ae88` | `0x16` |
| 2911 | `0x036d0b6a` | `0x03d2af3e` | `0x8` |
| 2929 | `0x036d0da8` | `0x04122758` | `0x4` |
| 2931 | `0x036d0ed8` | `0x04122758` | `0x4` |

## Missing substantial sites

| Recipe op | X-T3 address | Length |
| ---: | ---: | ---: |
| 470 | `0x00f2c9a0` | `0x6c` |
| 473 | `0x00f2ca36` | `0x10a` |
| 474 | `0x00f57c30` | `0x80` |
| 477 | `0x00f57ce0` | `0x154` |
| 502 | `0x0129a518` | `0x13` |
| 529 | `0x014e6150` | `0x17` |
| 530 | `0x014e6170` | `0x17` |
| 2720 | `0x01d86a3c` | `0x15` |
| 2730 | `0x01ed7130` | `0x12` |
| 2739 | `0x01ed86f8` | `0x1e` |
| 2745 | `0x01ed873c` | `0x14` |
| 2749 | `0x01ef22b4` | `0x10` |
| 2751 | `0x01ef22cc` | `0x40` |
| 2754 | `0x01ef2e10` | `0x50` |
| 2757 | `0x01ef458c` | `0x46` |
| 2758 | `0x01ef45e4` | `0x15` |
| 2759 | `0x01ef460d` | `0x51` |
| 2761 | `0x01ef4666` | `0xbe` |
| 2828 | `0x036d04f9` | `0x29` |
| 2835 | `0x036d055c` | `0x4e` |
| 2842 | `0x036d05e4` | `0x2c` |
| 2844 | `0x036d0618` | `0x30` |
| 2848 | `0x036d065c` | `0x22` |
| 2856 | `0x036d06b8` | `0x24` |
| 2858 | `0x036d06e4` | `0x22` |
| 2866 | `0x036d0740` | `0x24` |
| 2868 | `0x036d076c` | `0x22` |
| 2875 | `0x036d07c8` | `0x34` |
| 2877 | `0x036d0804` | `0x10` |
| 2885 | `0x036d09fc` | `0x34` |
| 2889 | `0x036d0a4c` | `0x18` |
| 2891 | `0x036d0a74` | `0x24` |
| 2903 | `0x036d0b18` | `0x10` |
| 2909 | `0x036d0b4c` | `0x10` |
| 2915 | `0x036d0b84` | `0x18` |
| 2925 | `0x036d0bf8` | `0x22` |
