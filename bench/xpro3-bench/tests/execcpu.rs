//! Only one subsystem creates threads, and it creates the five EXEC CPUs.
//!
//! `TSK_ROOT` runs 167 registry inserts, then 23 subsystem init calls in a
//! fixed order (`0x11635FC..0x1163744`). Of those 23, exactly **one** reaches
//! `tx_thread_create`: `0x1163A54`. It calls `0x1143C10`, which walks a
//! five-entry table at `0x164C420` and creates one thread per entry.
//!
//! That table holds ids `0x71..0x75` — the five `execcpu` threads. So the
//! application tasks, `TSK_UILIB` and `TSK_LCDEVF` included, are never turned
//! into threads by any init that actually runs.
//!
//! Measured at 34.8 M instructions the ThreadX thread table holds exactly
//! eleven blocks: the five EXEC CPUs, the loader's `timer` thread `0x2b`, the
//! four idles and `root`. No application task owns one.

use fujimod_xpro3_bench::{ReadWord, open, snapshot};
use fujimod_emulator_boot::application;

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
        definition["labels"] = serde_json::json!([
            0x1163A54u32, // the only init that reaches tx_thread_create
            0x1143C10u32, // its thread-creating loop
            0x1163AE0u32, // a later init, for contrast
        ]);
    }
    let out = std::env::temp_dir().join(format!("xpro3-execcpu-{}.json", std::process::id()));
    std::fs::write(&out, serde_json::to_vec_pretty(&document).ok()?).ok()?;
    Some(out)
}

#[test]
fn only_the_exec_cpu_init_creates_threads() {
    let Some(plan) = plan() else {
        eprintln!("skipping: no X-Pro3 recovery image beside the workspace");
        return;
    };
    if !firmware_dir().join("FWUP0021.DAT").exists() {
        eprintln!("skipping: no update file");
        return;
    }
    let request = fujimod_xpro3_bench::Request {
        configuration: "xpro3-200-handoff".into(),
        update: firmware_dir().join("FWUP0021.DAT"),
        plan,
        discovery: false,
        pokes: vec![(0xa2ec, 4)],
    };
    let mut started = open(&request).expect("the board opens");
    started
        .run_with(Some(34_800_000), None, |_| Ok(None))
        .expect("the guest runs past the subsystem init sequence");
    let slice = snapshot(&started, None).expect("the board reports state");

    // The one thread-creating init runs...
    assert!(
        slice.reached(0x1163A54).is_some(),
        "the EXEC CPU init must run"
    );
    assert!(
        slice.reached(0x1143C10).is_some(),
        "its thread-creating loop must run"
    );

    // ...and the threads it creates are the five EXEC CPUs 0x71..0x75, all
    // still suspended because nothing signals them.
    let board = &started.board;
    assert!(matches!(board, application::Board::Xp4(_)));
    let mut created = Vec::new();
    for id in 1..=0xa8u32 {
        let block = 0x655A4u64 + u64::from(id - 1) * 0x150;
        if u32::from_be_bytes(*b"THRD") == board.read_word(block as u32) {
            created.push(id);
        }
    }
    // Measured: the five EXEC CPUs, the `timer` loader thread 0x2b, the four
    // idles and root. Nothing else — and no application task.
    assert_eq!(
        created,
        vec![0x2b, 0x71, 0x72, 0x73, 0x74, 0x75, 0x9b, 0x9c, 0x9d, 0x9e, 0x9f],
        "the five EXEC CPUs, the timer thread, the four idles and root"
    );
    // The display tasks are not among them.
    for id in [0x36u32, 0x37] {
        assert!(
            !created.contains(&id),
            "task {id:#x} must not have a thread"
        );
    }
}