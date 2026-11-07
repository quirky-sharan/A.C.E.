//! The control channel to the core (D-52), mirroring `core/src/ace_core/ipc/desktop_link.py`:
//! lines the core prints on stdout, and JSON lines the shell writes to the core's stdin.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::geometry::Edge;

pub const READY_PREFIX: &str = "ACE_READY port=";
pub const SNAPSHOT_PREFIX: &str = "ACE_DESKTOP ";
/// The core accepts error texts up to this many characters.
pub const MAX_ERROR_CHARS: usize = 300;

/// What a hotkey (D-29) or tray item asks for.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Summon,
    PushToTalk,
    EmergencyStop,
    ToggleOverlay,
    MicMute,
}

impl Action {
    pub const ALL: [Action; 5] = [
        Action::Summon,
        Action::PushToTalk,
        Action::EmergencyStop,
        Action::ToggleOverlay,
        Action::MicMute,
    ];

    /// The name used on the wire and in settings keys (`hotkeys.<name>`).
    pub fn name(self) -> &'static str {
        match self {
            Action::Summon => "summon",
            Action::PushToTalk => "push_to_talk",
            Action::EmergencyStop => "emergency_stop",
            Action::ToggleOverlay => "toggle_overlay",
            Action::MicMute => "mic_mute",
        }
    }
}

/// Verification mode (D-09).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    Fast,
    Balanced,
    Paranoid,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct CoreState {
    /// A §5.4 conversation state, e.g. "asleep"; kept as text so new states never break parsing.
    pub conversation: String,
    pub game_mode: bool,
    pub offline: bool,
    pub dnd: bool,
    pub paused_overlay: bool,
}

/// Which monitor the overlay appears on (§14.2).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MonitorPolicy {
    #[default]
    Cursor,
    Primary,
}

/// Overlay placement (D-55): the edge, the orb's height (0 top .. 1 bottom), the monitor.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct OverlayConfig {
    pub edge: Edge,
    pub orb_y: f64,
    pub monitor: MonitorPolicy,
}

impl Default for OverlayConfig {
    fn default() -> Self {
        Self {
            edge: Edge::Right,
            orb_y: 0.5,
            monitor: MonitorPolicy::Cursor,
        }
    }
}

/// Everything the shell needs from the core; the core always sends it whole.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Snapshot {
    pub state: CoreState,
    pub hotkeys: BTreeMap<Action, Option<String>>,
    pub autostart: bool,
    pub mode: Mode,
    pub overlay: OverlayConfig,
}

#[derive(Debug, Clone, PartialEq)]
pub enum CoreLine {
    Ready { port: u16 },
    Snapshot(Box<Snapshot>),
    Other,
}

/// Parse one line from the core's stdout. Unknown lines are `Other`; malformed known ones fail.
pub fn parse_line(line: &str) -> Result<CoreLine, String> {
    let line = line.trim_end_matches(['\r', '\n']);
    if let Some(port) = line.strip_prefix(READY_PREFIX) {
        return match port.parse::<u16>() {
            Ok(port) if port > 0 => Ok(CoreLine::Ready { port }),
            _ => Err(format!("malformed READY line: {line:?}")),
        };
    }
    if let Some(json) = line.strip_prefix(SNAPSHOT_PREFIX) {
        return serde_json::from_str(json)
            .map(|snapshot| CoreLine::Snapshot(Box::new(snapshot)))
            .map_err(|err| format!("malformed snapshot: {err}"));
    }
    Ok(CoreLine::Other)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    Hotkey,
    Tray,
    Overlay,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Pressed,
    Released,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HotkeyProblem {
    pub action: Action,
    pub shortcut: String,
    pub error: String,
    pub suggestion: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ShellMessage {
    Input {
        action: Action,
        source: Source,
        phase: Phase,
    },
    SetMode {
        mode: Mode,
    },
    DesktopStatus {
        hotkey_problems: Vec<HotkeyProblem>,
        autostart_error: Option<String>,
    },
}

impl ShellMessage {
    /// One JSON line for the core's stdin.
    pub fn to_line(&self) -> String {
        let mut line = serde_json::to_string(self).unwrap_or_default();
        line.push('\n');
        line
    }
}

/// `text` cut to at most `max` characters (never in the middle of a character).
pub fn truncate(text: &str, max: usize) -> String {
    text.chars().take(max).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ready_lines() {
        assert_eq!(
            parse_line("ACE_READY port=50343\r\n"),
            Ok(CoreLine::Ready { port: 50343 })
        );
        assert!(parse_line("ACE_READY port=0").is_err());
        assert!(parse_line("ACE_READY port=70000").is_err());
        assert!(parse_line("ACE_READY port=").is_err());
        assert_eq!(parse_line("something else"), Ok(CoreLine::Other));
    }

    #[test]
    fn snapshot_lines() {
        let line = r#"ACE_DESKTOP {"state": {"conversation": "asleep", "game_mode": false, "offline": false, "dnd": true, "paused_overlay": false}, "hotkeys": {"summon": "Ctrl+Alt+Space", "push_to_talk": "Ctrl+Alt+A", "emergency_stop": "Ctrl+Alt+Escape", "toggle_overlay": null, "mic_mute": "Ctrl+Alt+M"}, "autostart": false, "mode": "paranoid", "overlay": {"edge": "left", "orb_y": 0.25, "monitor": "primary"}}"#;
        let Ok(CoreLine::Snapshot(snapshot)) = parse_line(line) else {
            panic!("not a snapshot");
        };
        assert_eq!(snapshot.state.conversation, "asleep");
        assert!(snapshot.state.dnd);
        assert_eq!(
            snapshot.hotkeys.get(&Action::Summon),
            Some(&Some("Ctrl+Alt+Space".to_string()))
        );
        assert_eq!(snapshot.hotkeys.get(&Action::ToggleOverlay), Some(&None));
        assert_eq!(snapshot.mode, Mode::Paranoid);
        assert_eq!(
            snapshot.overlay,
            OverlayConfig {
                edge: Edge::Left,
                orb_y: 0.25,
                monitor: MonitorPolicy::Primary
            }
        );
        assert!(parse_line("ACE_DESKTOP {not json").is_err());
    }

    #[test]
    fn messages_match_the_core_schema() {
        let input = ShellMessage::Input {
            action: Action::PushToTalk,
            source: Source::Hotkey,
            phase: Phase::Released,
        };
        assert_eq!(
            input.to_line(),
            "{\"type\":\"input\",\"action\":\"push_to_talk\",\"source\":\"hotkey\",\"phase\":\"released\"}\n"
        );
        let mode = ShellMessage::SetMode { mode: Mode::Fast };
        assert_eq!(
            mode.to_line(),
            "{\"type\":\"set_mode\",\"mode\":\"fast\"}\n"
        );
        let status = ShellMessage::DesktopStatus {
            hotkey_problems: vec![HotkeyProblem {
                action: Action::EmergencyStop,
                shortcut: "Ctrl+Alt+Escape".into(),
                error: "taken".into(),
                suggestion: Some("Ctrl+Alt+Shift+Escape".into()),
            }],
            autostart_error: None,
        };
        assert_eq!(
            status.to_line(),
            "{\"type\":\"desktop_status\",\"hotkey_problems\":[{\"action\":\"emergency_stop\",\"shortcut\":\"Ctrl+Alt+Escape\",\"error\":\"taken\",\"suggestion\":\"Ctrl+Alt+Shift+Escape\"}],\"autostart_error\":null}\n"
        );
    }

    #[test]
    fn truncation_respects_characters() {
        assert_eq!(truncate("नमस्ते", 2), "नम");
        assert_eq!(truncate("short", 300), "short");
    }
}
