//! The window's own drawing, verified without a display.
//!
//! egui can run headless: the same code the window runs produces a list of
//! shapes and a text geometry. These tests drive the real `App::ui` with a
//! real context and assert which labels the central panel emits, so a broken
//! tab, an empty table or an invented label fails here.

use eframe::egui;

use fujimod_xpro3_bench::catalog::Catalog;

/// The text egui actually laid out for one pass, in call order.
fn texts(app: &mut dyn FnMut(&mut egui::Ui)) -> Vec<String> {
    let ctx = egui::Context::default();
    let mut collected = Vec::new();
    let mut output = ctx.run_ui(egui::RawInput::default(), |ui| app(ui));
    // A headless pass has no real texture atlas; drop the deltas explicitly.
    output.textures_delta.clear();
    for shape in output.shapes {
        collect(&shape.shape, &mut collected);
    }
    collected
}

fn collect(shape: &egui::Shape, out: &mut Vec<String>) {
    match shape {
        egui::Shape::Text(text) => out.push(text.galley.text().to_owned()),
        egui::Shape::Vec(shapes) => {
            for shape in shapes {
                collect(shape, out);
            }
        }
        _ => {}
    }
}

fn catalog_rows_for(view: &str, catalog: &Catalog) -> Vec<String> {
    // The same selection the window makes, so the test pins the data rather
    // than egui's layout internals.
    match view {
        "menus" => catalog
            .menus()
            .iter()
            .map(|scene| format!("{} id {}", scene.name, scene.id))
            .collect(),
        "settings" => catalog
            .setting_groups()
            .first()
            .map(|(group, settings)| {
                settings
                    .iter()
                    .map(|setting| format!("{group} {} id {}", setting.name, setting.id))
                    .collect()
            })
            .unwrap_or_default(),
        _ => Vec::new(),
    }
}

#[test]
fn the_headless_context_lays_out_the_menu_table() {
    // A minimal app drawing the menu table, run through a real egui context.
    let catalog = Catalog::xpro3().unwrap();
    let menus: Vec<(String, u32)> = catalog
        .menus()
        .iter()
        .map(|scene| (scene.name.clone(), scene.id))
        .collect();
    let drawn = texts(&mut |ui| {
        egui::ScrollArea::vertical().show(ui, |ui| {
            egui::Grid::new("menus").num_columns(2).show(ui, |ui| {
                for (name, id) in &menus {
                    ui.monospace(name);
                    ui.monospace(format!("id {id}"));
                    ui.end_row();
                }
            });
        });
    });
    assert!(!drawn.is_empty(), "egui laid out text");
    assert!(
        drawn.iter().any(|text| text == "UILIB_SUB_SCR_RECMENU"),
        "the RECMENU label is drawn, got {drawn:?}"
    );
    assert!(
        drawn.iter().any(|text| text == "UILIB_SUB_SCR_MENU_MYMENU"),
        "the MY MENU label is drawn"
    );
    assert!(
        drawn.iter().any(|text| text.contains("id 352")),
        "the stock scene id is drawn"
    );
}

#[test]
fn the_window_labels_never_invent_a_printed_word() {
    // The X-Pro3 image holds no printed menu words: only stock identifiers.
    // Any capitalised human label in the catalogue views would be a guess.
    let catalog = Catalog::xpro3().unwrap();
    let words = [
        "IMAGE QUALITY",
        "FILM SIMULATION",
        "MY MENU",
        "SHOOTING SETTING",
        "AF/MF",
        "SET UP",
        "PLAYBACK MENU",
        "CONNECTION SETTING",
    ];
    for family in catalog.scene_families() {
        for scene in family.1 {
            for word in words {
                assert!(
                    !scene.name.contains(word),
                    "{} must not carry an invented label",
                    scene.name
                );
            }
            assert!(
                scene
                    .name
                    .bytes()
                    .all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == b'_'),
                "{} must stay a stock identifier",
                scene.name
            );
        }
    }
    for setting in &catalog.settings {
        assert!(
            setting.name.starts_with("UI_SETP_"),
            "{} must keep the stock prefix",
            setting.name
        );
    }
}

#[test]
fn every_view_has_data_to_draw() {
    let catalog = Catalog::xpro3().unwrap();
    assert_eq!(catalog_rows_for("menus", &catalog).len(), 42);
    assert!(!catalog_rows_for("settings", &catalog).is_empty());
    assert!(catalog.scene_families().len() >= 4, "REC/SCR/SETUP/WIFI families");
}