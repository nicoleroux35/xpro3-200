//! The bench must advance the guest and report real milestones.
//!
//! These tests use the stock X-Pro3 2.00 recovery image when it is present
//! beside the workspace (`../xpro3-firmware`). They are skipped, not failed,
//! when the firmware or the generated plan is absent: the repository holds no
//! Fujifilm firmware.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use fujimod_xpro3_bench::{Guest, Request};

fn workspace() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

fn firmware_dir() -> PathBuf {
    workspace().join("../xpro3-firmware")
}

/// The declared plan with absolute file references, rebuilt the way the
/// helper scripts do so a test does not depend on `/tmp` state.
fn plan() -> Option<PathBuf> {
    let directory = firmware_dir();
    let source = directory.join("xpro3-emulator-plan.json");
    let text = std::fs::read_to_string(&source).ok()?;
    let mut document: serde_json::Value = serde_json::from_str(&text).ok()?;
    if let Some(flash) = document.get("flash").and_then(|value| value.as_str()) {
        document["flash"] = serde_json::json!(directory.join(flash).display().to_string());
    }
    for image in document["images"].as_array_mut()? {
        let file = image["file"].as_str()?.to_owned();
        image["file"] = serde_json::json!(directory.join(file).display().to_string());
    }
    let out = std::env::temp_dir().join(format!(
        "xpro3-bench-plan-{}.json",
        std::process::id()
    ));
    std::fs::write(&out, serde_json::to_vec_pretty(&document).ok()?).ok()?;
    Some(out)
}

fn stock(request: Request) -> Option<Guest> {
    if !firmware_dir().join("FWUP0021.DAT").exists() {
        return None;
    }
    Some(Guest::start(request).expect("the stock board opens"))
}

/// The measured storage stop: the guest executes, reaches the NOR read and
/// then blocks on the 0x400 completion event with the plan as declared.
#[test]
fn the_guest_advances_and_reports_the_storage_stop() {
    let Some(plan) = plan() else {
        eprintln!("skipping: no X-Pro3 recovery image beside the workspace");
        return;
    };
    let request = Request {
        configuration: "xpro3-200-handoff".into(),
        update: firmware_dir().join("FWUP0021.DAT"),
        plan,
        discovery: false,
        pokes: vec![(0xa2ec, 4)],
    };
    let Some(guest) = stock(request) else {
        eprintln!("skipping: no FU21.DAT");
        return;
    };
    let deadline = Instant::now() + Duration::from_secs(600);
    let mut best = None;
    while Instant::now() < deadline {
        let Some(result) = guest.poll() else {
            std::thread::sleep(Duration::from_millis(50));
            continue;
        };
        let slice = result.expect("the guest runs without a model refusal");
        let enough = slice.instructions.iter().sum::<u64>() > 40_000_000;
        best = Some(slice);
        if enough {
            break;
        }
    }
    let slice = best.expect("the guest produced a slice");
    let total: u64 = slice.instructions.iter().sum();
    assert!(total > 30_000_000, "the guest must advance, got {total}");

    // main() is always the first instruction the board can observe.
    assert!(
        slice.milestones.iter().any(|&(_, pc, _)| pc == 0x1162F14),
        "main() must be observed"
    );
    // The transfer engine's wait is where the declared plan stops.
    assert!(
        slice.milestones.iter().any(|&(_, pc, _)| pc == 0x109099C),
        "the 0x400 wait must be observed"
    );
    // The completion poster belongs to the interrupt path that the declared
    // DMA routes never deliver. A regression here means the plan was fixed.
    let posted = slice.milestones.iter().any(|&(_, pc, _)| pc == 0x1090BEC);
    eprintln!("poster 0x1090BEC reached: {posted}");
}