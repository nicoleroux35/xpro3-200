//! X-Pro3 XP4 analysis bench: guest runner.
//!
//! The bench is a workbench, not a camera simulator. It runs the stock X-Pro3
//! 2.00 firmware on the real XP4 board and reports what the guest actually
//! does — counters, per-core state, interrupt counts, and the passive
//! milestone trace. When the guest has not entered an address, or no display
//! output presents a frame, the bench says so instead of drawing something
//! plausible.
//!
//! Everything here is host-side observation of a stopped board boundary. The
//! guest itself is never modified, patched or repaired by the bench.

pub mod catalog;
pub mod dispatch;

use std::path::PathBuf;
use std::sync::mpsc::{Receiver, TryRecvError, channel};
use std::time::{Duration, Instant};

use fujimod_catalog_resolution::ResolvedConfiguration;
use fujimod_emulator_boot::application;
use fujimod_emulator_boot::host::Memory;

/// Instructions per slice: small enough that pause and the window stay
/// responsive, large enough that the per-slice cost stays invisible.
pub const SLICE: u64 = 250_000;
/// Host pause between slices, so the window breathes.
pub const CYCLE: Duration = Duration::from_millis(16);

/// An address the bench watches, with the name this session gave it.
pub struct Watch {
    pub address: u32,
    pub name: &'static str,
}

/// The boot chain measured in `reports/EMULATOR-2026-11-26.md`, plus the
/// addresses decoded from the image during this session.
pub const WATCHES: &[Watch] = &[
    Watch { address: 0x1162F14, name: "main()" },
    Watch { address: 0x114F798, name: "thread create path" },
    Watch { address: 0x1163500, name: "TSK_ROOT body" },
    Watch { address: 0x1150210, name: "start task" },
    Watch { address: 0x1163744, name: "storage init" },
    Watch { address: 0x1163754, name: "after storage init" },
    Watch { address: 0x113A7BC, name: "configuration read" },
    Watch { address: 0x1163760, name: "TSK_ROOT continues" },
    Watch { address: 0x1093410, name: "NOR read via 0xFFFD80xx" },
    Watch { address: 0x10907AC, name: "transfer submit" },
    Watch { address: 0x109099C, name: "wait on event 0x400" },
    Watch { address: 0x10908C0, name: "poll instead of wait" },
    Watch { address: 0x10908E8, name: "wait returned" },
    Watch { address: 0x1090BEC, name: "post event 0x400" },
    Watch { address: 0x1090BA8, name: "post event 0x100" },
    Watch { address: 0x1090B64, name: "progress IRQ handler" },
    Watch { address: 0x1090C0C, name: "engine 3-mode primitive" },
    Watch { address: 0x1090F70, name: "transfer loop (block)" },
    Watch { address: 0x10910B4, name: "transfer loop (buffered)" },
    Watch { address: 0x1090AFC, name: "register progress callback" },
    Watch { address: 0x10913D8, name: "synchronous NOR read" },
    Watch { address: 0x10914F8, name: "real submit site" },
    Watch { address: 0x10973DC, name: "enqueue request" },
    Watch { address: 0x1097DF0, name: "request queue consumer" },
    Watch { address: 0x1098DEC, name: "softirq dispatcher" },
    Watch { address: 0x1134B94, name: "register IRQ handler" },
    Watch { address: 0x108BEEC, name: "object lookup" },
    Watch { address: 0x108B118, name: "object start" },
    Watch { address: 0x108B550, name: "object command" },
    Watch { address: 0x114FC44, name: "current task id" },
    // The display path. These functions program the LCDC, including the
    // output-enable write that starts frame capture; they are never entered,
    // which is why no frame is ever published.
    Watch { address: 0x1100E9C, name: "LCDC timing programming" },
    Watch { address: 0x11065B8, name: "LCDC timing (second path)" },
    Watch { address: 0x11103B8, name: "LCDC vertical timing" },
    Watch { address: 0x110EB94, name: "LCDC output enable" },
    Watch { address: 0x110EBC4, name: "LCDC output disable" },
    Watch { address: 0x1107758, name: "display task body (A)" },
    Watch { address: 0x110782C, name: "display task body (B)" },
    Watch { address: 0x10F52F4, name: "display bring-up" },
];

/// A copy of one published LCD frame.
pub struct Image {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
    pub sequence: u64,
}

/// Everything the UI shows, copied out of the board at a quiet boundary.
pub struct Slice {
    pub instructions: Vec<u64>,
    pub ticks: u64,
    pub waiting: Vec<bool>,
    pub irq_entries: Vec<u64>,
    pub data_aborts: Vec<u64>,
    pub failure: Option<String>,
    /// Entered addresses as `(core, address, instructions_at_entry)`,
    /// ordered by the count so the table reads as the guest's own history.
    pub milestones: Vec<(usize, u32, u64)>,
    pub frame: Option<Image>,
}

impl Slice {
    pub fn total(&self) -> u64 {
        self.instructions.iter().sum()
    }
    pub fn reached(&self, address: u32) -> Option<(usize, u64)> {
        self.milestones
            .iter()
            .find(|&&(_, pc, _)| pc == address)
            .map(|&(core, _, count)| (core, count))
    }
}

/// A bench run, as the command line describes it.
pub struct Request {
    pub configuration: String,
    pub update: PathBuf,
    pub plan: PathBuf,
    pub discovery: bool,
    /// Words written before the guest starts.
    pub pokes: Vec<(u64, u32)>,
}

/// The guest runs on its own thread and hands finished slices to the caller.
pub struct Guest {
    slices: Receiver<Result<Slice, String>>,
    stop: std::sync::mpsc::Sender<()>,
}

impl Guest {
    pub fn start(request: Request) -> Result<Self, String> {
        let (ready, wait) = channel::<Result<(), String>>();
        let (out, slices) = channel();
        let (stop, stopped) = channel();
        std::thread::Builder::new()
            .name("xpro3-bench-guest".into())
            .spawn(move || run(request, ready, out, stopped))
            .map_err(|error| error.to_string())?;
        match wait.recv() {
            Ok(Ok(())) => Ok(Self { slices, stop }),
            Ok(Err(error)) => Err(error),
            Err(_) => Err("the guest thread exited before starting".into()),
        }
    }

    /// The newest finished slice, if the guest produced one since the last
    /// call. Never blocks, so the UI keeps drawing while the guest runs.
    pub fn poll(&self) -> Option<Result<Slice, String>> {
        let mut newest = None;
        loop {
            match self.slices.try_recv() {
                Ok(slice) => newest = Some(slice),
                Err(TryRecvError::Empty) => return newest,
                Err(TryRecvError::Disconnected) => {
                    return newest.or(Some(Err("the guest thread stopped".into())));
                }
            }
        }
    }
}

impl Drop for Guest {
    fn drop(&mut self) {
        let _ = self.stop.send(());
    }
}

fn run(
    request: Request,
    ready: std::sync::mpsc::Sender<Result<(), String>>,
    out: std::sync::mpsc::Sender<Result<Slice, String>>,
    stop: Receiver<()>,
) {
    let mut started = match open(&request) {
        Ok(started) => {
            let _ = ready.send(Ok(()));
            started
        }
        Err(error) => {
            let _ = ready.send(Err(error.clone()));
            let _ = out.send(Err(error));
            return;
        }
    };
    loop {
        if stop.try_recv().is_ok() {
            return;
        }
        let began = Instant::now();
        // `run_with` drives the guest until the instruction budget is spent,
        // so each call is one bounded slice ending on a quiet boundary.
        let frame = std::cell::RefCell::new(None);
        let outcome = started.run_with(Some(SLICE), None, |board| {
            if let Some(published) = board.display_frames().into_iter().next() {
                *frame.borrow_mut() = Some(Image {
                    width: published.width,
                    height: published.height,
                    rgba: published.rgba,
                    sequence: published.sequence,
                });
            }
            Ok(None)
        });
        if let Err(error) = outcome {
            let _ = out.send(Err(error));
            return;
        }
        let Some(slice) = snapshot(&started, frame.into_inner()) else {
            let _ = out.send(Err("the board reports no XP4 state".into()));
            return;
        };
        let _ = out.send(Ok(slice));
        if let Some(rest) = CYCLE.checked_sub(began.elapsed()) {
            std::thread::sleep(rest);
        }
    }
}

/// Open the configured board exactly as the CLI would, but keep it live.
pub fn open(request: &Request) -> Result<application::Started, String> {
    let resolved = ResolvedConfiguration::with_overlays(&request.configuration, &[])?;
    // The X-Pro3 handoff profile declares no `inputs` block: the CLI selects
    // the application path on the SoC identity, so the bench does the same.
    if resolved.reference.soc.id != "xp4" {
        return Err(format!(
            "{} is not an XP4 profile (soc {})",
            request.configuration, resolved.reference.soc.id
        ));
    }
    let labelled = labelled(&request.plan)?;
    let startup = application::Startup {
        update: request.update.clone(),
        plan: labelled.clone(),
        discovery: request.discovery,
        // One scheduler turn stays tiny: the bench never parks a core inside
        // a long quantum.
        quantum: Some(1_000),
        card_image: None,
        card_files: Vec::new(),
        // No settings are placed in the NOR journal: the X-Pro3 layout has not
        // been located, so the bench leaves the firmware to its own defaults
        // rather than writing guessed values.
        camera_settings: std::collections::BTreeMap::new(),
    };
    let opened = application::open(&resolved, startup);
    // The board reads the plan once, at open time, so the observation copy is
    // no longer needed and must not linger in the caller's directory.
    let _ = std::fs::remove_file(&labelled);
    let started = opened?;
    for (address, word) in &request.pokes {
        started
            .board
            .write(*address, &word.to_le_bytes())
            .map_err(|error| format!("poke {address:#x}: {error}"))?;
    }
    Ok(started)
}

/// A copy of the plan whose board definition carries every watched address.
///
/// Labels are passive observation points: the board records the first
/// instruction count at which each is entered and changes nothing else. The
/// supplied plan is never modified, and the copy sits beside it so its
/// relative file references keep resolving.
fn labelled(plan: &std::path::Path) -> Result<PathBuf, String> {
    let text = std::fs::read(plan).map_err(|error| format!("{}: {error}", plan.display()))?;
    let mut document: serde_json::Value = serde_json::from_slice(&text)
        .map_err(|error| format!("{}: {error}", plan.display()))?;
    let definition = document
        .pointer_mut("/board/definition")
        .filter(|value| value.is_object())
        .ok_or_else(|| format!("{} has no XP4 board definition", plan.display()))?;
    let mut labels: std::collections::BTreeSet<u64> = definition
        .get("labels")
        .and_then(|value| value.as_array())
        .into_iter()
        .flatten()
        .filter_map(|value| value.as_u64())
        .collect();
    labels.extend(WATCHES.iter().map(|watch| u64::from(watch.address)));
    definition["labels"] = serde_json::json!(labels.into_iter().collect::<Vec<_>>());
    let directory = plan.parent().unwrap_or_else(|| std::path::Path::new("."));
    let name = plan
        .file_stem()
        .and_then(|stem| stem.to_str())
        .unwrap_or("plan");
    let out = directory.join(format!(
        ".{name}.bench-{}.json",
        std::process::id()
    ));
    std::fs::write(&out, serde_json::to_vec_pretty(&document).map_err(|error| error.to_string())?)
        .map_err(|error| format!("{}: {error}", out.display()))?;
    Ok(out)
}

pub fn snapshot(started: &application::Started, frame: Option<Image>) -> Option<Slice> {
    let application::Board::Xp4(board) = &started.board else {
        return None;
    };
    let state = board.state(true);
    let mut milestones: Vec<(usize, u32, u64)> = state
        .history
        .as_ref()
        .map(|history| {
            history
                .milestones
                .iter()
                .map(|&(core, pc, count)| (core, pc, count))
                .collect()
        })
        .unwrap_or_default();
    milestones.sort_by_key(|&(_, pc, count)| (count, pc));
    let (instructions, ticks) = started.progress();
    Some(Slice {
        instructions,
        ticks,
        waiting: state.waiting.clone(),
        irq_entries: state.irq_entries.clone(),
        data_aborts: state.data_aborts.clone(),
        failure: state.failure.clone(),
        milestones,
        frame,
    })
}
/// Read one physical RAM word from an XP4 board, through the board's own
/// memory interface. Used by the analysis tests to inspect ThreadX tables.
pub trait ReadWord {
    fn read_word(&self, address: u32) -> u32;
}

impl ReadWord for application::Board {
    fn read_word(&self, address: u32) -> u32 {
        let application::Board::Xp4(board) = self else {
            return 0;
        };
        let mut bytes = [0u8; 4];
        if board.read(usize::try_from(address).unwrap_or(usize::MAX), &mut bytes).is_err() {
            return 0;
        }
        u32::from_le_bytes(bytes)
    }
}
