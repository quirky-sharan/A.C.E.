//! Global hotkeys (D-29, §14.6). The core owns the settings; the shell registers what the latest
//! snapshot asks for and reports what it could not register (another app holds the combination,
//! or the text is not a valid shortcut), each with a suggested alternative.
//!
//! Registration goes through the global-shortcut plugin, which runs it on the main thread. Never
//! hold `Registry`'s lock while calling the plugin: the hotkey handler takes it on that thread.

use std::collections::{BTreeMap, HashMap};
use std::sync::Mutex;
use std::sync::mpsc::Sender;

use tauri::AppHandle;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutEvent, ShortcutState};

use crate::protocol::{Action, Phase, ShellMessage, Source};
use crate::status::{HotkeyStatus, lock};
use crate::supervisor::Msg;

pub type Wanted = BTreeMap<Action, Option<String>>;

#[derive(Default)]
pub struct Registry {
    by_id: HashMap<u32, Action>,
    registered: Vec<Shortcut>,
    applied: Option<Wanted>,
    statuses: Vec<HotkeyStatus>,
}

/// Called by the plugin for every press and release of a registered shortcut.
pub fn on_event(
    registry: &Mutex<Registry>,
    tx: &Sender<Msg>,
    shortcut: &Shortcut,
    event: ShortcutEvent,
) {
    let Some(action) = lock(registry).by_id.get(&shortcut.id()).copied() else {
        return;
    };
    let phase = match event.state() {
        ShortcutState::Pressed => Phase::Pressed,
        ShortcutState::Released => Phase::Released,
    };
    // Only push-to-talk is held (D-29); for the others a press is the whole gesture.
    if phase == Phase::Released && action != Action::PushToTalk {
        return;
    }
    shell_log!("hotkey {} {phase:?}", action.name());
    let _ = tx.send(Msg::Send(ShellMessage::Input {
        action,
        source: Source::Hotkey,
        phase,
    }));
}

/// Register exactly the shortcuts in `wanted`. Does nothing if they are already applied.
pub fn apply(app: &AppHandle, registry: &Mutex<Registry>, wanted: &Wanted) -> Vec<HotkeyStatus> {
    let previous = {
        let mut current = lock(registry);
        if current.applied.as_ref() == Some(wanted) {
            return current.statuses.clone();
        }
        current.by_id.clear(); // stop dispatching while the set changes
        std::mem::take(&mut current.registered)
    };

    let plugin = app.global_shortcut();
    for shortcut in previous {
        let _ = plugin.unregister(shortcut);
    }

    let mut by_id = HashMap::new();
    let mut registered = Vec::new();
    let mut statuses = Vec::new();
    for action in Action::ALL {
        let text = wanted.get(&action).cloned().flatten();
        let mut status = HotkeyStatus {
            action,
            shortcut: text.clone(),
            registered: false,
            error: None,
            suggestion: None,
        };
        if let Some(text) = text {
            match text.parse::<Shortcut>() {
                Err(err) => status.error = Some(format!("not a valid shortcut: {err}")),
                Ok(shortcut) => {
                    if let Some(other) = by_id.get(&shortcut.id()) {
                        let other: &Action = other;
                        status.error = Some(format!("already used for {} in ACE", other.name()));
                        status.suggestion = suggest(&text);
                    } else {
                        match plugin.register(shortcut) {
                            Ok(()) => {
                                by_id.insert(shortcut.id(), action);
                                registered.push(shortcut);
                                status.registered = true;
                            }
                            Err(err) => {
                                status.error = Some(describe(&err.to_string()));
                                status.suggestion = suggest(&text);
                            }
                        }
                    }
                }
            }
        }
        statuses.push(status);
    }

    let mut current = lock(registry);
    current.by_id = by_id;
    current.registered = registered;
    current.applied = Some(wanted.clone());
    current.statuses = statuses.clone();
    statuses
}

/// The plugin's error text, phrased for Sharan when Windows reports a taken combination.
fn describe(error: &str) -> String {
    if error.contains("already registered") {
        "another app already uses this combination".to_string()
    } else {
        error.to_string()
    }
}

/// An alternative to offer when a shortcut is taken: the same keys plus Shift.
pub fn suggest(shortcut: &str) -> Option<String> {
    let parts: Vec<&str> = shortcut.split('+').map(str::trim).collect();
    if parts.iter().any(|part| part.eq_ignore_ascii_case("shift")) {
        return None;
    }
    let (key, modifiers) = parts.split_last()?;
    if key.is_empty() || modifiers.is_empty() {
        return None;
    }
    let mut keys = modifiers.to_vec();
    keys.push("Shift");
    keys.push(key);
    Some(keys.join("+"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn suggestions_add_shift() {
        assert_eq!(
            suggest("Ctrl+Alt+Escape").as_deref(),
            Some("Ctrl+Alt+Shift+Escape")
        );
        assert_eq!(
            suggest("Ctrl + Alt + A").as_deref(),
            Some("Ctrl+Alt+Shift+A")
        );
        assert_eq!(suggest("Ctrl+Shift+A"), None);
        assert_eq!(suggest("F9"), None);
    }

    #[test]
    fn the_d29_defaults_parse() {
        for text in [
            "Ctrl+Alt+Shift+Space",
            "Ctrl+Alt+A",
            "Ctrl+Alt+Escape",
            "Ctrl+Alt+H",
            "Ctrl+Alt+Shift+M",
        ] {
            assert!(text.parse::<Shortcut>().is_ok(), "{text}");
        }
        assert!("Ctrl+Alt+NotAKey".parse::<Shortcut>().is_err());
    }

    #[test]
    fn taken_combinations_are_explained() {
        assert_eq!(
            describe("HotKey already registered: HotKey { .. }"),
            "another app already uses this combination"
        );
        assert_eq!(describe("something else"), "something else");
    }
}
