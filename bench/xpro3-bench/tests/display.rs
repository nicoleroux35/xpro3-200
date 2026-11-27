//! The display path is unreachable in the stock profile, and that is a
//! measurement, not an opinion.
//!
//! The LCDC publishes a frame only when the firmware writes `1` into its
//! output-enable register (`base + 4`). Five functions in the X-Pro3 image
//! touch the LCDC programming registers; none of them is ever entered on the
//! stock run, so no write ever reaches the enable bit and `bank0-status.json`
//! stays `enabled: false` with zero frames.

use fujimod_xpro3_bench::{Guest, Request, WATCHES};

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
    let out = std::env::temp_dir().join(format!("xpro3-lcdc-{}.json", std::process::id()));
    std::fs::write(&out, serde_json::to_vec_pretty(&document).ok()?).ok()?;
    Some(out)
}

/// Even on the unlocked run — correct DMA routes, discovery, 120 M
/// instructions — the display programming functions stay unentered and the
/// board publishes no frame.
#[test]
fn no_frame_is_published_because_the_lcdc_is_never_programmed() {
    let Some(plan) = plan() else {
        eprintln!("skipping: no X-Pro3 recovery image beside the workspace");
        return;
    };
    if !firmware_dir().join("FWUP0021.DAT").exists() {
        eprintln!("skipping: no update file");
        return;
    }
    let request = Request {
        configuration: "xpro3-200-handoff".into(),
        update: firmware_dir().join("FWUP0021.DAT"),
        plan,
        discovery: true,
        pokes: vec![(0xa2ec, 4)],
    };
    let guest = Guest::start(request).expect("the board opens");
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(900);
    let mut slice = None;
    while std::time::Instant::now() < deadline {
        let Some(result) = guest.poll() else {
            std::thread::sleep(std::time::Duration::from_millis(100));
            continue;
        };
        let current = result.expect("the guest runs");
        let enough = current.instructions.iter().sum::<u64>() > 60_000_000;
        slice = Some(current);
        if enough {
            break;
        }
    }
    let slice = slice.expect("the guest produced state");
    assert!(slice.total() > 60_000_000, "the guest must run far enough");

    // The five LCDC programming functions must all stay unentered.
    for address in [0x1100E9C, 0x11065B8, 0x11103B8, 0x110EB94, 0x110EBC4] {
        let name = WATCHES
            .iter()
            .find(|watch| watch.address == address)
            .map(|watch| watch.name)
            .unwrap_or("LCDC");
        assert!(
            slice.reached(address).is_none(),
            "{name} ({address:#x}) must not be entered in the stock profile"
        );
    }
    // And no frame exists to show, which is what the window reports.
    assert!(slice.frame.is_none(), "no scanout frame may be published");
}