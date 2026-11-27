//! The catalogue views must show what the firmware actually declares.
//!
//! Counts are pinned to the X-Pro3 2.00 records so a catalog change that loses
//! the scene, setting or input tables fails here instead of silently emptying
//! the navigator.

use fujimod_xpro3_bench::catalog::Catalog;

#[test]
fn the_xpro3_ui_records_load_with_their_measured_counts() {
    let catalog = Catalog::xpro3().expect("the X-Pro3 UI records load");
    assert_eq!(catalog.firmware, "xpro3-200");
    assert_eq!(catalog.body, "xpro3");
    assert_eq!(catalog.scenes.len(), 632, "named UI scenes");
    assert_eq!(catalog.settings.len(), 1872, "named settings");
    assert_eq!(catalog.inputs.len(), 105, "scanner rows");
}

#[test]
fn the_menu_screens_are_the_ones_the_firmware_names() {
    let catalog = Catalog::xpro3().unwrap();
    let menus: Vec<&str> = catalog.menus().iter().map(|scene| scene.name.as_str()).collect();
    assert_eq!(menus.len(), 42, "scenes whose stock name marks a menu");
    for expected in [
        "UILIB_SUB_SCR_RECMENU",
        "UILIB_SUB_SCR_PLAYMENU",
        "UILIB_SUB_SCR_DMENU",
        "UILIB_SUB_SCR_MENU_MYMENU",
        "UILIB_SUB_SCR_RECQMENU",
        "UILIB_SUB_SCR_QMENU_CUSTOM_MAIN",
    ] {
        assert!(menus.contains(&expected), "{expected} must be listed as a menu");
    }
}

#[test]
fn scene_ids_are_the_stock_numbers() {
    let catalog = Catalog::xpro3().unwrap();
    let id = |name: &str| {
        catalog
            .scenes
            .iter()
            .find(|scene| scene.name == name)
            .map(|scene| scene.id)
            .unwrap_or_else(|| panic!("{name} is missing"))
    };
    assert_eq!(id("UILIB_SUB_SCR_RECMENU"), 352);
    assert_eq!(id("UILIB_SUB_SCR_PLAYMENU"), 354);
    assert_eq!(id("UILIB_SUB_SCR_DMENU"), 351);
    assert_eq!(id("UILIB_SUB_SCR_MENU_MYMENU"), 411);
}

#[test]
fn settings_group_by_their_stock_token() {
    let catalog = Catalog::xpro3().unwrap();
    let groups = catalog.setting_groups();
    assert!(!groups.is_empty(), "settings must group");
    let total: usize = groups.iter().map(|(_, settings)| settings.len()).sum();
    assert_eq!(total, catalog.settings.len(), "every setting lands in one group");
    // The grouping token comes from the stock name, never from a guess.
    for (group, settings) in &groups {
        for setting in settings {
            let expected = setting
                .name
                .strip_prefix("UI_SETP_")
                .unwrap_or(&setting.name)
                .split('_')
                .next()
                .unwrap();
            assert_eq!(group, expected);
        }
    }
}

#[test]
fn scanner_rows_keep_their_stock_identity() {
    let catalog = Catalog::xpro3().unwrap();
    let first = &catalog.inputs[0];
    assert_eq!(first.id, "row-0");
    assert_eq!(first.index, 0);
    assert!(
        first.witness.contains("physical_key"),
        "each row keeps the witness the generator recorded"
    );
    assert!(
        catalog.inputs.iter().all(|row| !row.id.is_empty()),
        "every row carries its identity"
    );
}