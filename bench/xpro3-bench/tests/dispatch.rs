//! The dispatch frontier: where the missing thread creation must come from.
//!
//! `0x114F798` has 90 `BL` call sites. 52 live in the first FFLZ segment
//! (`0x00F21000..0x01650000`), which is the code the stock run actually
//! executes. 38 live in the second segment (`0x01CE3000..0x02527000`), and
//! none of those 38 callers is reachable from `main()`.

use fujimod_xpro3_bench::dispatch::{self, SEGMENTS, THREAD_CREATE_PATH, segment_of};

#[test]
fn the_segment_map_matches_the_catalog_baseline() {
    // Two FFLZ blobs plus one raw image, at the load addresses the catalog
    // baseline declares for FWUP0021.DAT.
    assert_eq!(SEGMENTS.len(), 4);
    assert_eq!(
        segment_of(THREAD_CREATE_PATH),
        Some("first FFLZ segment"),
        "the thread-create path lives in the first segment"
    );
    assert_eq!(
        segment_of(0x0004_C04C),
        Some("raw image"),
        "tx_thread_create lives in the raw image"
    );
    assert_eq!(segment_of(0x0116_3A54), Some("first FFLZ segment"));
    assert_eq!(segment_of(0x0208_269C), Some("second FFLZ segment"));
    assert_eq!(segment_of(0x0000_1000), Some("recovery image, below the raw blob"));
}

#[test]
fn the_unreached_callers_are_all_in_the_second_segment() {
    assert!(
        !dispatch::UNREACHED_CALLERS.is_empty(),
        "the frontier must be named"
    );
    for &caller in dispatch::UNREACHED_CALLERS {
        assert_eq!(
            segment_of(caller),
            Some("second FFLZ segment"),
            "{caller:#010x} must be in the second segment"
        );
    }
    // None of them is in the first segment, which is what makes them
    // unreachable: the run only executes the first segment.
    assert!(
        dispatch::UNREACHED_CALLERS
            .iter()
            .all(|&caller| segment_of(caller) != Some("first FFLZ segment"))
    );
}