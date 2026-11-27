//! Where the missing thread creation would have to come from.
//!
//! `0x114F798` is the only function in the image that reaches
//! `tx_thread_create` for application tasks. It has 90 `BL` call sites,
//! split in two groups by the runtime segment they live in:
//!
//! | segment | sites | reached on this run |
//! | --- | ---: | --- |
//! | `0x00F21000..0x01650000` (first FFLZ) | 52 | some |
//! | `0x01CE3000..0x02527000` (second FFLZ) | 38 | **none** |
//!
//! The 38 callers in the second segment are 38 distinct functions, and none of
//! them is reachable from `main()`. None is referenced anywhere in the image
//! either: not as a literal word, not through a `movw`/`movt` pair. They are
//! code with no in-image referrer — the shape of entry points that something
//! outside the loaded image must install (a loader table, a flash-resident
//! dispatcher, or a subsystem that never runs).
//!
//! `tests` in this crate pin the reachable facts; this module documents the
//! unreachable half so the frontier is explicit.

/// `tx_thread_create` in the ARM image.
pub const TX_THREAD_CREATE: u32 = 0x0004_C04C;
/// The wrapper the application path uses.
pub const TX_THREAD_CREATE_WRAPPER: u32 = 0x0004_C1E0;
/// The registration helper used by the start-task primitive.
pub const REGISTRY_INSERT: u32 = 0x0004_BE9C;
/// The one function that reaches thread creation for application tasks.
pub const THREAD_CREATE_PATH: u32 = 0x0114_F798;
/// The single init that creates threads, and the loop it calls.
pub const EXEC_CPU_INIT: u32 = 0x0116_3A54;
pub const EXEC_CPU_LOOP: u32 = 0x0114_3C10;

/// Runtime segments of the X-Pro3 2.00 update, as the catalog baseline
/// declares them. File offset equals address in the recovery image; these are
/// the RAM ranges the two FFLZ blobs land in.
pub const SEGMENTS: &[(u32, u32, &str)] = &[
    (0x0000_0000, 0x0004_0000, "recovery image, below the raw blob"),
    (0x0004_0000, 0x0005_B0C0, "raw image"),
    (0x00F2_1000, 0x0165_0000, "first FFLZ segment"),
    (0x01CE_3000, 0x0252_7000, "second FFLZ segment"),
];

/// Which declared segment owns an address.
pub fn segment_of(address: u32) -> Option<&'static str> {
    SEGMENTS
        .iter()
        .find(|&&(lo, hi, _)| lo <= address && address < hi)
        .map(|&(_, _, name)| name)
}

/// The 38 functions in the second segment that call the thread-create path and
/// are reachable from nothing inside the image. Collected by scanning every
/// `BL 0x114F798` site and its enclosing function.
pub const UNREACHED_CALLERS: &[u32] = &[
    0x01E5_5288, 0x01F4_0208, 0x01F8_9378, 0x01FA_3988, 0x0208_269C, 0x020B_A4A8,
    0x020C_3038, 0x020D_52C8, 0x0212_39BC, 0x021B_50E8, 0x0223_ADAC, 0x0228_7ED0,
    0x022B_BC38, 0x0230_7808, 0x0231_8DA0,
];