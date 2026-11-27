//! Correct DMA completion routes are what let storage init finish.
//!
//! The stock X-Pro3 firmware arms GIC lines 207..222 for its sixteen DMA
//! channels; the catalog declares the same numbers. A plan that declares
//! 32..47 instead never delivers the completion, so the transfer wait at
//! `0x109099C` spins and the poster at `0x1090BEC` is never reached.
//!
//! This test asserts both directions on the same image, with no firmware
//! patch: the wiring alone decides. It is skipped when the stock recovery
//! image or the generated plan is absent, because the repository holds no
//! Fujifilm firmware.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use fujimod_xpro3_bench::{Guest, Request};

const POSTER: u32 = 0x0109_0BEC; // completion posted on core 1
const WAIT: u32 = 0x0109_099C; // the transfer wait that spins when unwired

fn workspace() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

fn firmware_dir() -> PathBuf {
    workspace().join("../xpro3-firmware")
}

/// The stock plan with one board field replaced, and absolute file references.
fn plan(routes: [u32; 16], tag: &str) -> Option<PathBuf> {
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
    let definition = document.pointer_mut("/board/definition")?;
    definition.as_object_mut()?.insert(
        "storage_dma_routes".into(),
        serde_json::json!(routes.to_vec()),
    );
    let out = std::env::temp_dir().join(format!(
        "xpro3-dma-{}-{tag}.json",
        std::process::id()
    ));
    std::fs::write(&out, serde_json::to_vec_pretty(&document).ok()?).ok()?;
    Some(out)
}

/// Run to a budget, returning every milestone the board observed.
fn run(plan: PathBuf) -> Vec<u32> {
    let request = Request {
        configuration: "xpro3-200-handoff".into(),
        update: firmware_dir().join("FWUP0021.DAT"),
        plan,
        discovery: false,
        pokes: vec![(0xa2ec, 4)],
    };
    let guest = Guest::start(request).expect("the board opens");
    let deadline = Instant::now() + Duration::from_secs(600);
    let mut seen = Vec::new();
    while Instant::now() < deadline {
        match guest.poll() {
            None => std::thread::sleep(Duration::from_millis(50)),
            Some(Ok(slice)) => {
                seen.extend(slice.milestones.iter().map(|&(_, pc, _)| pc));
                // 40 M is past the poster (37.4 M) and short of the first
                // refusal the stock plan reaches, so both wirings get a fair
                // comparison without needing the diagnostic declarations.
                if slice.instructions.iter().sum::<u64>() > 40_000_000 {
                    break;
                }
            }
            Some(Err(error)) => panic!("the guest refused: {error}"),
        }
    }
    seen
}

#[test]
fn the_dma_routes_decide_whether_storage_init_completes() {
    if !firmware_dir().join("FWUP0021.DAT").exists() {
        eprintln!("skipping: no X-Pro3 update beside the workspace");
        return;
    }
    let some_routes = |start: u32| {
        let mut routes = [0u32; 16];
        for (index, line) in routes.iter_mut().enumerate() {
            *line = start + index as u32;
        }
        routes
    };

    let Some(catalog_plan) = plan(some_routes(207), "catalog") else {
        eprintln!("skipping: no generated plan beside the workspace");
        return;
    };
    let Some(guessed_plan) = plan(some_routes(32), "guessed") else {
        eprintln!("skipping: no generated plan beside the workspace");
        return;
    };

    let catalog = run(catalog_plan);
    let guessed = run(guessed_plan);

    assert!(
        guessed.contains(&WAIT),
        "the guessed wiring must still reach the transfer wait"
    );
    assert!(
        !guessed.contains(&POSTER),
        "the guessed wiring must never deliver the completion"
    );
    assert!(
        catalog.contains(&POSTER),
        "lines 207..222 must deliver the completion to the interrupt handler"
    );
}
