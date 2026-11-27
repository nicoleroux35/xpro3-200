//! Command line for the X-Pro3 XP4 analysis bench.

use std::path::PathBuf;
use std::time::Instant;

use fujimod_xpro3_bench::{CYCLE, Guest, Request, SLICE, WATCHES, open};

fn main() {
    fujimod_emulator_exr2_board::register_board_builder();
    fujimod_emulator_models::register();
    match parse(std::env::args().skip(1).collect()) {
        Ok(Command::Window(request, initial)) => {
            if let Err(error) = window(request, initial) {
                eprintln!("fujimod-xpro3-bench: {error}");
                std::process::exit(1);
            }
        }
        Ok(Command::Check(request)) => match open(&request) {
            Ok(mut started) => match check(&request, &mut started) {
                Ok(report) => println!("{report}"),
                Err(error) => {
                    eprintln!("fujimod-xpro3-bench: {error}");
                    std::process::exit(1);
                }
            },
            Err(error) => {
                eprintln!("fujimod-xpro3-bench: {error}");
                std::process::exit(1);
            }
        },
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(2);
        }
    }
}

fn check(
    request: &Request,
    started: &mut fujimod_emulator_boot::application::Started,
) -> Result<serde_json::Value, String> {
    // `--check` runs a fixed guest budget so the table is a measurement, not
    // an empty plan read. One slice at a time keeps it interruptible.
    let mut ran = 0;
    while ran < CHECK.0 {
        started.run_with(Some(CHECK.1), None, |_| Ok(None))?;
        ran += CHECK.1;
    }
    let (instructions, ticks) = started.progress();
    let slice = fujimod_xpro3_bench::snapshot(started, None);
    let milestones = slice
        .as_ref()
        .map(|slice| {
            slice
                .milestones
                .iter()
                .map(|&(core, pc, count)| {
                    serde_json::json!({
                        "address": format!("{pc:#010x}"),
                        "name": WATCHES.iter().find(|watch| watch.address == pc).map(|watch| watch.name),
                        "core": core,
                        "instructions": count,
                    })
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    Ok(serde_json::json!({
        "configuration": request.configuration,
        "engine": started.engine,
        "ticks_per_second": started.ticks_per_second,
        "instructions": instructions.iter().sum::<u64>(),
        "guest_ticks": ticks,
        "milestones": milestones,
        "scanned": ran,
    }))
}

/// Guest budget `--check` spends before printing: total, per slice.
const CHECK: (u64, u64) = (60_000_000, 250_000);

enum Command {
    Window(Request, Option<View>),
    Check(Request),
}

fn parse(args: Vec<String>) -> Result<Command, String> {
    let mut check = false;
    let mut initial = None;
    let mut configuration = None;
    let mut update = None;
    let mut plan = None;
    let mut discovery = false;
    let mut pokes = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let arg = args[index].clone();
        index += 1;
        let mut take = |name: &str| -> Result<String, String> {
            let value = args
                .get(index)
                .cloned()
                .ok_or_else(|| format!("{name} needs a value"))?;
            index += 1;
            Ok(value)
        };
        match arg.as_str() {
            "--check" => check = true,
            "--view" => {
                initial = Some(match take("--view")?.as_str() {
                    "screen" => View::Screen,
                    "menus" => View::Menus,
                    "settings" => View::Settings,
                    "inputs" => View::Inputs,
                    other => {
                        return Err(format!(
                            "--view wants screen, menus, settings or inputs, not {other}"
                        ));
                    }
                })
            }
            "--discovery" => discovery = true,
            "--configuration" => configuration = Some(take("--configuration")?),
            "--update" => update = Some(PathBuf::from(take("--update")?)),
            "--application-plan" => plan = Some(PathBuf::from(take("--application-plan")?)),
            "--poke" => {
                let text = take("--poke")?;
                let (address, word) = text
                    .split_once('=')
                    .ok_or_else(|| format!("--poke wants ADDRESS=WORD, not {text}"))?;
                let address = parse_number(address)?;
                let word = u32::try_from(parse_number(word)?)
                    .map_err(|_| format!("--poke word exceeds 32 bits: {text}"))?;
                pokes.push((address, word));
            }
            "-h" | "--help" => return Err(usage()),
            other => return Err(format!("unknown option {other}\n\n{}", usage())),
        }
    }
    let request = Request {
        configuration: configuration.unwrap_or_else(|| "xpro3-200-handoff".into()),
        update: update.ok_or("required option: --update")?,
        plan: plan.ok_or("required option: --application-plan")?,
        discovery,
        pokes,
    };
    Ok(if check {
        Command::Check(request)
    } else {
        Command::Window(request, initial)
    })
}

fn usage() -> String {
    "Usage: fujimod-xpro3-bench --update FWUP0021.DAT --application-plan PLAN.json\n\
     \x20        [--configuration xpro3-200-handoff] [--discovery]\n\
     \x20        [--poke ADDRESS=WORD]... [--check]\n\
     \x20        [--view screen|menus|settings|inputs]\n\n\
     Runs the stock X-Pro3 firmware and shows its execution state.\n\
     --check opens the board once, prints the milestone table as JSON and exits.\n\
     The plan is a research input: fix its declared DMA interrupt routes rather\n\
     than patching the firmware."
        .into()
}

fn parse_number(text: &str) -> Result<u64, String> {
    match text.strip_prefix("0x").or_else(|| text.strip_prefix("0X")) {
        Some(hex) => u64::from_str_radix(hex, 16).map_err(|error| error.to_string()),
        None => text
            .parse()
            .map_err(|error: std::num::ParseIntError| error.to_string()),
    }
}

fn window(request: Request, initial: Option<View>) -> Result<(), String> {
    let options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_title("X-Pro3 2.00 analysis bench")
            .with_inner_size([1180.0, 760.0]),
        ..Default::default()
    };
    eframe::run_native(
        "fujimod-xpro3-bench",
        options,
        Box::new(|_cc| Ok(Box::new(Bench::new(request, initial)))),
    )
    .map_err(|error| error.to_string())
}

struct Bench {
    guest: Option<Guest>,
    startup_error: Option<String>,
    texture: Option<eframe::egui::TextureHandle>,
    slice: Option<fujimod_xpro3_bench::Slice>,
    failure: Option<String>,
    paused: bool,
    paused_at: Option<Instant>,
    started: Instant,
    /// What the stock firmware declares about its own UI, loaded once.
    catalog: Result<fujimod_xpro3_bench::catalog::Catalog, String>,
    view: View,
    /// Free-text filter applied to whichever view is open.
    filter: String,
    /// Scene family expanded in the tree, or the settings group selected.
    selected: Option<String>,
}

/// Which reference view fills the central panel.
#[derive(Clone, Copy, PartialEq, Eq)]
enum View {
    Screen,
    Menus,
    Settings,
    Inputs,
}

impl Bench {
    fn new(request: Request, initial: Option<View>) -> Self {
        let (guest, startup_error) = match Guest::start(request) {
            Ok(guest) => (Some(guest), None),
            Err(error) => (None, Some(error)),
        };
        Self {
            guest,
            startup_error,
            texture: None,
            slice: None,
            failure: None,
            paused: false,
            paused_at: None,
            started: Instant::now(),
            catalog: fujimod_xpro3_bench::catalog::Catalog::xpro3(),
            view: initial.unwrap_or(View::Menus),
            filter: String::new(),
            selected: None,
        }
    }

    fn poll(&mut self) {
        if self.paused || self.failure.is_some() {
            return;
        }
        let Some(guest) = &self.guest else { return };
        if let Some(result) = guest.poll() {
            match result {
                Ok(slice) => self.slice = Some(slice),
                Err(error) => self.failure = Some(error),
            }
        }
    }
}

impl eframe::App for Bench {
    fn ui(&mut self, ui: &mut eframe::egui::Ui, _frame: &mut eframe::Frame) {
        self.poll();
        ui.ctx().request_repaint_after(CYCLE);
        use eframe::egui;
        egui::Panel::left("status")
            .resizable(true)
            .default_size(400.0)
            .show(ui, |ui| self.draw_status(ui));
        egui::CentralPanel::default().show(ui, |ui| self.draw_center(ui));
    }
}

impl Bench {
    /// The central panel: the LCD, or one of the catalogue views.
    fn draw_center(&mut self, ui: &mut eframe::egui::Ui) {
        use eframe::egui;
        ui.horizontal(|ui| {
            ui.selectable_value(&mut self.view, View::Screen, "screen");
            ui.selectable_value(&mut self.view, View::Menus, "menus");
            ui.selectable_value(&mut self.view, View::Settings, "settings");
            ui.selectable_value(&mut self.view, View::Inputs, "inputs");
            if self.view != View::Screen {
                ui.separator();
                ui.add(
                    egui::TextEdit::singleline(&mut self.filter)
                        .hint_text("filter")
                        .desired_width(200.0),
                );
            }
        });
        ui.separator();
        match self.view {
            View::Screen => self.draw_screen(ui),
            View::Menus => self.draw_menus(ui),
            View::Settings => self.draw_settings(ui),
            View::Inputs => self.draw_inputs(ui),
        }
    }

    /// Every scene whose stock name marks it as a menu screen.
    fn draw_menus(&mut self, ui: &mut eframe::egui::Ui) {
        use eframe::egui;
        let catalog = match &self.catalog {
            Ok(catalog) => catalog,
            Err(error) => {
                ui.colored_label(egui::Color32::RED, error.clone());
                return;
            }
        };
        ui.label(
            egui::RichText::new(format!(
                "{} menu screens of {} named UI scenes · firmware {}",
                catalog.menus().len(),
                catalog.scenes.len(),
                catalog.firmware
            ))
            .weak(),
        );
        ui.add_space(4.0);
        let filter = self.filter.to_uppercase();
        egui::ScrollArea::both().show(ui, |ui| {
            for family in catalog.scene_families() {
                let scenes: Vec<_> = family
                    .1
                    .iter()
                    .filter(|scene| scene.menu)
                    .filter(|scene| filter.is_empty() || scene.name.contains(&filter))
                    .copied()
                    .collect();
                if scenes.is_empty() {
                    continue;
                }
                let title = format!("{} ({})", family.0, scenes.len());
                egui::CollapsingHeader::new(title)
                    .default_open(family.0 == "SCR")
                    .show(ui, |ui| {
                        egui::Grid::new(format!("menus-{}", family.0))
                            .num_columns(2)
                            .striped(true)
                            .show(ui, |ui| {
                                for scene in scenes {
                                    ui.monospace(&scene.name);
                                    ui.monospace(format!("id {}", scene.id));
                                    ui.end_row();
                                }
                            });
                    });
            }
        });
    }

    /// All settings, grouped by their leading stock token.
    fn draw_settings(&mut self, ui: &mut eframe::egui::Ui) {
        use eframe::egui;
        let catalog = match &self.catalog {
            Ok(catalog) => catalog,
            Err(error) => {
                ui.colored_label(egui::Color32::RED, error.clone());
                return;
            }
        };
        let groups = catalog.setting_groups();
        let filter = self.filter.to_uppercase();
        ui.label(
            egui::RichText::new(format!(
                "{} named settings in {} groups · firmware {}",
                catalog.settings.len(),
                groups.len(),
                catalog.firmware
            ))
            .weak(),
        );
        ui.add_space(4.0);
        ui.horizontal_wrapped(|ui| {
            for (group, _) in &groups {
                let label = format!("{group}");
                let selected = self.selected.as_deref() == Some(group.as_str());
                if ui.selectable_label(selected, label).clicked() {
                    self.selected = Some(group.clone());
                }
            }
        });
        ui.separator();
        let selected = self.selected.clone();
        egui::ScrollArea::vertical().show(ui, |ui| {
            for (group, settings) in &groups {
                if let Some(chosen) = &selected {
                    if chosen != group {
                        continue;
                    }
                }
                let shown: Vec<_> = settings
                    .iter()
                    .filter(|setting| filter.is_empty() || setting.name.contains(&filter))
                    .collect();
                if shown.is_empty() {
                    continue;
                }
                ui.label(
                    egui::RichText::new(format!("{group} — {} entries", shown.len())).strong(),
                );
                egui::Grid::new(format!("settings-{group}"))
                    .num_columns(2)
                    .striped(true)
                    .show(ui, |ui| {
                        for setting in shown {
                            ui.monospace(&setting.name);
                            ui.monospace(format!("id {}", setting.id));
                            ui.end_row();
                        }
                    });
                ui.add_space(6.0);
            }
        });
    }

    /// The 105 scanner rows: what each physical input maps to.
    fn draw_inputs(&mut self, ui: &mut eframe::egui::Ui) {
        use eframe::egui;
        let catalog = match &self.catalog {
            Ok(catalog) => catalog,
            Err(error) => {
                ui.colored_label(egui::Color32::RED, error.clone());
                return;
            }
        };
        let filter = self.filter.to_uppercase();
        let unclaimed = catalog.inputs.iter().filter(|row| row.unclaimed).count();
        ui.label(
            egui::RichText::new(format!(
                "{} scanner rows · {unclaimed} still unclaimed · firmware {}",
                catalog.inputs.len(),
                catalog.firmware
            ))
            .weak(),
        );
        ui.add_space(4.0);
        egui::ScrollArea::both().show(ui, |ui| {
            egui::Grid::new("inputs")
                .num_columns(5)
                .striped(true)
                .show(ui, |ui| {
                    ui.strong("row");
                    ui.strong("event");
                    ui.strong("debug key");
                    ui.strong("target");
                    ui.strong("witness");
                    ui.end_row();
                    for row in &catalog.inputs {
                        if !filter.is_empty()
                            && !row.id.contains(&filter)
                            && !row.witness.to_uppercase().contains(&filter)
                            && !row
                                .debug_key
                                .as_deref()
                                .unwrap_or_default()
                                .contains(&filter)
                        {
                            continue;
                        }
                        ui.monospace(&row.id);
                        ui.monospace(format!("{}", row.event));
                        ui.monospace(row.debug_key.as_deref().unwrap_or("—"));
                        ui.monospace(if row.unclaimed { "unclaimed" } else { "claimed" });
                        ui.monospace(&row.witness);
                        ui.end_row();
                    }
                });
        });
    }
}

impl Bench {
    fn draw_status(&mut self, ui: &mut eframe::egui::Ui) {
        use eframe::egui;
        ui.heading("Guest");
        if let Some(error) = &self.startup_error {
            ui.colored_label(egui::Color32::RED, error);
            ui.add_space(8.0);
            ui.label(
                egui::RichText::new(
                    "The board did not open. Check --update, --application-plan and the \
                     configuration name.",
                )
                .weak(),
            );
            return;
        }
        ui.horizontal(|ui| {
            let label = if self.paused { "resume" } else { "pause" };
            if ui.button(label).clicked() {
                self.paused = !self.paused;
                self.paused_at = self.paused.then(Instant::now);
            }
            let ran = match self.paused_at {
                Some(at) => at.duration_since(self.started),
                None => self.started.elapsed(),
            };
            ui.label(format!("{:.0} s wall", ran.as_secs_f32()));
        });
        if let Some(failure) = &self.failure {
            ui.colored_label(egui::Color32::RED, format!("guest stopped: {failure}"));
        }
        ui.separator();
        let Some(slice) = &self.slice else {
            ui.label("starting the guest…");
            return;
        };
        ui.monospace(format!("instructions {:>14}", slice.total()));
        ui.monospace(format!("guest ticks  {:>14}", slice.ticks));
        if let Some(failure) = &slice.failure {
            ui.colored_label(egui::Color32::RED, format!("board failure: {failure}"));
        }
        ui.separator();
        ui.label("cores");
        egui::Grid::new("cores")
            .num_columns(5)
            .striped(true)
            .show(ui, |ui| {
                ui.strong("core");
                ui.strong("instructions");
                ui.strong("state");
                ui.strong("irq");
                ui.strong("aborts");
                ui.end_row();
                for (core, count) in slice.instructions.iter().enumerate() {
                    let wait = slice.waiting.get(core).copied().unwrap_or(false);
                    ui.monospace(format!("{core}"));
                    ui.monospace(format!("{count}"));
                    ui.monospace(if wait { "waiting" } else { "running" });
                    ui.monospace(format!(
                        "{}",
                        slice.irq_entries.get(core).copied().unwrap_or(0)
                    ));
                    ui.monospace(format!(
                        "{}",
                        slice.data_aborts.get(core).copied().unwrap_or(0)
                    ));
                    ui.end_row();
                }
            });
        ui.separator();
        ui.label("watched addresses");
        ui.label(
            egui::RichText::new("reached, in the order the guest entered them")
                .small()
                .weak(),
        );
        egui::ScrollArea::vertical()
            .max_height(340.0)
            .show(ui, |ui| {
                for watch in WATCHES {
                    match slice.reached(watch.address) {
                        Some((core, count)) => ui.monospace(format!(
                            "{:>12}  c{core}  {:#010x}  {}",
                            count, watch.address, watch.name
                        )),
                        None => ui.monospace(egui::RichText::new(format!(
                            "{:>12}  --  {:#010x}  {}",
                            "never", watch.address, watch.name
                        ))
                        .weak()),
                    };
                }
            });
        let unreached = WATCHES
            .iter()
            .filter(|watch| slice.reached(watch.address).is_none())
            .count();
        ui.separator();
        ui.label(format!(
            "{unreached} of {} watched addresses never entered",
            WATCHES.len()
        ));
        ui.add_space(4.0);
        ui.label(
            egui::RichText::new(format!(
                "slice {SLICE} instructions · host cycle {CYCLE:?}"
            ))
            .small()
            .weak(),
        );
    }

    fn draw_screen(&mut self, ui: &mut eframe::egui::Ui) {
        use eframe::egui;
        let Some(slice) = &self.slice else {
            ui.centered_and_justified(|ui| ui.label("no guest state yet"));
            return;
        };
        let Some(image) = &slice.frame else {
            ui.centered_and_justified(|ui| {
                ui.vertical_centered(|ui| {
                    ui.label(egui::RichText::new("no scanout published a frame").size(22.0));
                    ui.add_space(10.0);
                    ui.label(
                        egui::RichText::new(
                            "The guest is executing, but no display output presents a frame \
                             in this configuration.\nThis is the measured state of the profile, \
                             not a bench failure.",
                        )
                        .weak(),
                    );
                });
            });
            return;
        };
        let size = [image.width as usize, image.height as usize];
        if size[0] == 0 || size[1] == 0 || image.rgba.len() != size[0] * size[1] * 4 {
            ui.label("the published frame does not match its declared size");
            return;
        }
        let color = egui::ColorImage::from_rgba_unmultiplied(size, &image.rgba);
        match &mut self.texture {
            Some(texture) => texture.set(color, egui::TextureOptions::LINEAR),
            None => {
                self.texture =
                    Some(ui.ctx().load_texture("lcd", color, egui::TextureOptions::LINEAR));
            }
        }
        if let Some(texture) = &self.texture {
            let available = ui.available_size();
            let scale = (available.x / image.width as f32)
                .min(available.y / image.height as f32)
                .max(0.01);
            ui.image((
                texture.id(),
                egui::vec2(image.width as f32 * scale, image.height as f32 * scale),
            ));
        }
        ui.label(format!(
            "frame {} — {}x{}",
            image.sequence, image.width, image.height
        ));
    }
}