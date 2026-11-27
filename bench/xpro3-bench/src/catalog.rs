//! Read-only views of what the stock firmware actually declares about its UI.
//!
//! These are structural views, not screenshots. The X-Pro3 image contains 632
//! named UI scenes, 1872 named settings and 105 physical input rows, all
//! located and executed by the catalog's generators. The *words the camera
//! prints* are not in the image as strings — there is no `IMAGE QUALITY` or
//! `MY MENU` anywhere in `ffboot.bin`, in ASCII, UTF-16 or Shift-JIS — so this
//! module never invents one. Every label below is a stock firmware identifier.

use std::collections::BTreeMap;

use fujimod_catalog::reference::ReferenceCatalog;

/// One named UI scene, with its stock identifier and numeric id.
pub struct Scene {
    /// The full name the firmware returns, e.g. `UILIB_SUB_SCR_RECMENU`.
    pub name: String,
    /// The firmware's own numeric id for this scene.
    pub id: u32,
    /// The screen family, taken from the name itself: `REC`, `SCR`, `SETUP`, `WIFI`.
    pub family: String,
    /// Whether the stock name marks this scene as a menu screen.
    pub menu: bool,
}

/// One named setting, with its stock identifier and numeric id.
pub struct Setting {
    pub name: String,
    pub id: u32,
    /// The first token after `UI_SETP_`, used to group the list.
    pub group: String,
}

/// One physical input row from the scanner table.
pub struct Input {
    pub id: String,
    pub event: u32,
    pub debug_key: Option<String>,
    pub index: u32,
    /// The witness the generator recorded, as `physical_key`/`kind`/`source`.
    pub witness: String,
    /// `true` when the row's target is still unclaimed.
    pub unclaimed: bool,
}

/// Everything the UI navigator shows, loaded once from the catalog.
pub struct Catalog {
    pub firmware: String,
    pub body: String,
    /// SHA-256 of the update the names were located in.
    pub firmware_sha256: String,
    pub scenes: Vec<Scene>,
    pub settings: Vec<Setting>,
    pub inputs: Vec<Input>,
}

impl Catalog {
    /// Load the X-Pro3 2.00 records from the bundled reference catalog.
    pub fn xpro3() -> Result<Self, String> {
        let catalog = ReferenceCatalog::bundled()?;
        let resolved = catalog.resolve("xpro3", "xpro3-200")?;
        Self::from_selection(&resolved)
    }

    fn from_selection(
        selection: &fujimod_catalog::reference::ResolvedSelection,
    ) -> Result<Self, String> {
        let scenes = selection
            .ui_scene_names
            .as_ref()
            .ok_or("the X-Pro3 firmware declares no UI scene names")?;
        let settings = selection
            .ui_setting_names
            .as_ref()
            .ok_or("the X-Pro3 firmware declares no UI setting names")?;
        let scenes = scenes
            .ui_scene_names
            .iter()
            .map(|(name, &id)| Scene {
                family: family(name),
                menu: name.contains("MENU"),
                name: name.clone(),
                id,
            })
            .collect();
        let mut settings: Vec<Setting> = settings
            .ui_setting_names
            .iter()
            .map(|(name, &id)| Setting {
                group: name
                    .strip_prefix("UI_SETP_")
                    .unwrap_or(name)
                    .split('_')
                    .next()
                    .unwrap_or(name)
                    .to_owned(),
                name: name.clone(),
                id,
            })
            .collect();
        settings.sort_by(|a, b| (&a.group, &a.name).cmp(&(&b.group, &b.name)));
        let inputs = selection
            .control_ids
            .as_ref()
            .map(inputs)
            .unwrap_or_default();
        Ok(Self {
            firmware: selection.firmware.id.clone(),
            body: selection.firmware.body_id.clone(),
            firmware_sha256: selection
                .firmware
                .update
                .as_ref()
                .map(|update| update.sha256.clone())
                .unwrap_or_default(),
            scenes,
            settings,
            inputs,
        })
    }

    /// Scene families in catalogue order, for the tree's top level.
    pub fn scene_families(&self) -> Vec<(String, Vec<&Scene>)> {
        let mut groups: BTreeMap<&str, Vec<&Scene>> = BTreeMap::new();
        for scene in &self.scenes {
            groups.entry(scene.family.as_str()).or_default().push(scene);
        }
        groups
            .into_iter()
            .map(|(family, scenes)| (family.to_owned(), scenes))
            .collect()
    }

    /// The menu screens only: the scenes whose stock name marks them as menus.
    pub fn menus(&self) -> Vec<&Scene> {
        self.scenes.iter().filter(|scene| scene.menu).collect()
    }

    /// Settings grouped by their leading token, largest group first.
    pub fn setting_groups(&self) -> Vec<(String, Vec<&Setting>)> {
        let mut groups: BTreeMap<&str, Vec<&Setting>> = BTreeMap::new();
        for setting in &self.settings {
            groups.entry(setting.group.as_str()).or_default().push(setting);
        }
        let mut groups: Vec<(String, Vec<&Setting>)> = groups
            .into_iter()
            .map(|(group, settings)| (group.to_owned(), settings))
            .collect();
        groups.sort_by(|a, b| b.1.len().cmp(&a.1.len()).then(a.0.cmp(&b.0)));
        groups
    }
}

/// The screen family token in a scene name.
fn family(name: &str) -> String {
    let stripped = name.strip_prefix("UILIB_SUB_").unwrap_or(name);
    stripped
        .split('_')
        .next()
        .unwrap_or(stripped)
        .to_owned()
}

fn inputs(control_ids: &serde_json::Value) -> Vec<Input> {
    let rows = control_ids
        .get("inputs")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    rows.iter()
        .enumerate()
        .map(|(fallback, row)| {
            let witness = row
                .get("scanner")
                .and_then(|scanner| scanner.get("witness"))
                .map(|witness| {
                    format!(
                        "physical_key {} · {} · source {}",
                        witness.get("physical_key").and_then(|v| v.as_u64()).unwrap_or(0),
                        witness
                            .get("input_kind")
                            .and_then(|v| v.as_str())
                            .unwrap_or("-"),
                        witness
                            .get("source")
                            .and_then(|v| v.as_u64())
                            .map(|value| format!("{value:#x}"))
                            .unwrap_or_else(|| "-".into()),
                    )
                })
                .unwrap_or_else(|| "no witness".into());
            Input {
                id: row
                    .get("id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("row-?")
                    .to_owned(),
                event: row
                    .get("event")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0) as u32,
                debug_key: row
                    .get("debug_key")
                    .and_then(|v| v.as_str())
                    .map(str::to_owned),
                index: row
                    .get("scanner")
                    .and_then(|scanner| scanner.get("index"))
                    .and_then(|v| v.as_u64())
                    .unwrap_or(fallback as u64) as u32,
                witness,
                unclaimed: row
                    .pointer("/target/kind")
                    .and_then(|v| v.as_str())
                    .is_some_and(|kind| kind == "unclaimed"),
            }
        })
        .collect()
}