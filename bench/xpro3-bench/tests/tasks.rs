//! The 167 application tasks are registered but never become threads.
//!
//! Measured on the stock profile, right after `TSK_ROOT` runs its start loop:
//!
//! - the registry `0x7A944` holds 167 filled slots;
//! - `0x1150210` returns 0 exactly 167 times, and the loop at `0x11635E4`
//!   never inspects that value (`bl` then `add/cmp/bne`);
//! - `0x4BE9C`, the only callee that fills the registry, returns 0 and only
//!   stores into the registry: it never creates a thread;
//! - ThreadX itself holds exactly **five** `THRD` blocks, the four idles and
//!   `root` — no application task has one.
//!
//! This is why the display task never runs, and therefore why the LCDC is
//! never programmed and no frame is ever published.

use fujimod_xpro3_bench::{ReadWord, WATCHES, open, snapshot};

fn workspace() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn firmware_dir() -> std::path::PathBuf {
    workspace().join("../xpro3-firmware")
}

fn plan() -> Option<std::path::PathBuf> {
    let directory = firmware_dir();
    let text = std::fs::read_to_string(directory.join("xpro3-emulator-plan.json")).ok()?;
    let mut document: serde_json::Value = serde_json::from_str(&text).ok()?;
    if let Some(flash) = document.get("flash").and_then(|value| value.as_str()) {
        document["flash"] = serde_json::json!(directory.join(flash).display().to_string());
    }
    for image in document["images"].as_array_mut()? {
        let file = image["file"].as_str()?.to_owned();
        image["file"] = serde_json::json!(directory.join(file).display().to_string());
    }
    if let Some(definition) = document.pointer_mut("/board/definition") {
        definition.as_object_mut()?.remove("discovery_tx_receiver");
        definition.as_object_mut()?.remove("power_spi_command_output");
    }
    let out = std::env::temp_dir().join(format!("xpro3-tasks-{}.json", std::process::id()));
    std::fs::write(&out, serde_json::to_vec_pretty(&document).ok()?).ok()?;
    Some(out)
}

/// Run past the start loop and read the registry and the ThreadX thread table
/// straight out of board RAM.
#[test]
fn the_start_loop_registers_167_tasks_but_creates_no_thread() {
    let Some(plan) = plan() else {
        eprintln!("skipping: no X-Pro3 recovery image beside the workspace");
        return;
    };
    if !firmware_dir().join("FWUP0021.DAT").exists() {
        eprintln!("skipping: no update file");
        return;
    }
    // Only the two addresses the assertion needs.
    let mut document: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&plan).unwrap()).unwrap();
    document["board"]["definition"]["labels"] = serde_json::json!([0x1150210u32, 0x11635E4u32]);
    std::fs::write(&plan, serde_json::to_vec_pretty(&document).unwrap()).unwrap();

    let request = fujimod_xpro3_bench::Request {
        configuration: "xpro3-200-handoff".into(),
        update: firmware_dir().join("FWUP0021.DAT"),
        plan,
        discovery: false,
        pokes: vec![(0xa2ec, 4)],
    };
    let mut started = open(&request).expect("the board opens");
    // Past the 167-iteration loop, before the subsystems start.
    started
        .run_with(Some(26_100_000), None, |_| Ok(None))
        .expect("the guest runs to the start loop");

    let board = &started.board;
    assert!(
        matches!(board, application::Board::Xp4(_)),
        "the bench only runs XP4 profiles"
    );
    let slice = snapshot(&started, None).expect("the board reports state");
    assert!(
        slice.reached(0x11635E4).is_some(),
        "the start loop must have run"
    );
    assert!(
        slice.reached(0x1150210).is_some(),
        "the start-task primitive must have run"
    );

    // The registry: 167 filled slots, none of them a thread.
    let mut filled = 0;
    for id in 1..=0xa8u32 {
        if board.read_word(0x7A944 + (id - 1) * 4) != 0 {
            filled += 1;
        }
    }
    assert_eq!(filled, 167, "the start loop registers 167 entries");

    // ThreadX: only the four idles and root own a THRD block.
    let mut threads = Vec::new();
    for id in 1..=0xa8u32 {
        let block = 0x655A4u64 + u64::from(id - 1) * 0x150;
        if u32::from_be_bytes(*b"THRD") == board.read_word(block as u32) {
            threads.push(id);
        }
    }
    assert_eq!(
        threads,
        vec![0x9b, 0x9c, 0x9d, 0x9e, 0x9f],
        "only the idles and root have ThreadX threads"
    );
    // The display task ids are registered and have no thread.
    for id in [0x36u32, 0x37] {
        assert!(
            board.read_word(0x7A944 + (id - 1) * 4) != 0,
            "task {id:#x} must be registered"
        );
        assert!(
            !threads.contains(&id),
            "task {id:#x} must not have a thread"
        );
    }

    // The records are copies, not identities. `0x1150210` builds a three-word
    // stack record `{0, b, b}` and the loop passes its own counter as `b`, so
    // 0x4BE9C writes `{src[0], src[4], src[8], src[4], 0}` into every slot.
    // Hence: uniform records, and each slot pointing at its own copy.
    let mut patterns = std::collections::BTreeSet::new();
    let mut self_referential = 0;
    for id in 1..=0xa7u32 {
        let own = 0x63168 + (id - 1) * 0x14;
        if board.read_word(0x7A944 + (id - 1) * 4) == own {
            self_referential += 1;
        }
        patterns.insert((0..5).map(|i| board.read_word(own + i * 4)).collect::<Vec<_>>());
    }
    assert_eq!(
        self_referential, 167,
        "every registry slot points at its own record"
    );
    assert_eq!(
        patterns.len(),
        2,
        "the records carry no per-task identity: {patterns:?}"
    );
    // The fourth word mirrors the second rather than reading a new one.
    let first: Vec<u32> = (0..5).map(|i| board.read_word(0x63168 + i * 4)).collect();
    assert_eq!(first[1], first[3], "the copy duplicates src[4] into +0xc");
    assert_eq!(first[4], 0, "the copy zero-fills the last word");

    let _ = WATCHES;
}

use fujimod_emulator_boot::application;