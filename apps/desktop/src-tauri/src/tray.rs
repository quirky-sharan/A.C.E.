//! The tray icon (S04 task 2): a ring tinted by what ACE is doing, plus the menu
//! Show / hide overlay · Control Center · Mute mic · Mode ▸ · Quit ACE.
//! Filled ring = the core is running; hollow ring = it is starting, restarting or stopped.

use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};

use tauri::image::Image;
use tauri::menu::{
    CheckMenuItem, CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder, SubmenuBuilder,
};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Wry};

use crate::protocol::{Action, Mode, Phase, ShellMessage, Source};
use crate::status::{CorePhase, CoreStatus, CoreView, Shared, lock};
use crate::supervisor::Msg;

pub const ICON_SIZE: u32 = 32;

// §14.4 tokens and the §5.4 orb colours.
const CYAN: [u8; 3] = [0x22, 0xD3, 0xEE];
const VIOLET: [u8; 3] = [0xA7, 0x8B, 0xFA];
const AMBER: [u8; 3] = [0xFB, 0xBF, 0x24];
const ORANGE: [u8; 3] = [0xFB, 0x92, 0x3C];
const GREEN: [u8; 3] = [0x34, 0xD3, 0x99];
const GREY: [u8; 3] = [0x7F, 0xA7, 0xB8];
const RED: [u8; 3] = [0xF8, 0x71, 0x71];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Look {
    pub color: [u8; 3],
    pub filled: bool,
}

/// Colour, shape and tooltip for the current situation.
pub fn look(core: &CoreStatus, conversation: Option<&str>) -> (Look, String) {
    let hollow = |color| Look {
        color,
        filled: false,
    };
    match core.phase {
        CorePhase::Starting => (hollow(AMBER), "ACE — starting…".into()),
        CorePhase::Restarting => (
            hollow(AMBER),
            format!("ACE — restarting the core (restart {})", core.restarts),
        ),
        CorePhase::Stopping => (hollow(AMBER), "ACE — stopping…".into()),
        CorePhase::Stopped => (hollow(RED), "ACE — the core is stopped".into()),
        CorePhase::Running if core.safe_mode => (
            Look {
                color: ORANGE,
                filled: true,
            },
            "ACE — safe mode".into(),
        ),
        CorePhase::Running => {
            let state = conversation.unwrap_or("asleep");
            let color = match state {
                "transcribing" | "thinking" => VIOLET,
                "acting" => AMBER,
                "awaiting_confirm" | "awaiting_answer" => ORANGE,
                "dictating" => GREEN,
                "muted" => GREY,
                "error" => RED,
                _ => CYAN, // asleep, listening, speaking, follow_up and anything new
            };
            (
                Look {
                    color,
                    filled: true,
                },
                format!("ACE — {}", state.replace('_', " ")),
            )
        }
    }
}

/// A 32×32 RGBA ring (plus a centre dot when filled), anti-aliased.
pub fn render(look: Look) -> Vec<u8> {
    let size = ICON_SIZE as usize;
    let centre = ICON_SIZE as f32 / 2.0;
    let mut rgba = vec![0u8; size * size * 4];
    for y in 0..size {
        for x in 0..size {
            let dx = x as f32 + 0.5 - centre;
            let dy = y as f32 + 0.5 - centre;
            let distance = (dx * dx + dy * dy).sqrt();
            let ring = coverage(distance, 11.5, 14.5);
            let dot = if look.filled {
                coverage(distance, 0.0, 6.0)
            } else {
                0.0
            };
            let pixel = (y * size + x) * 4;
            rgba[pixel..pixel + 3].copy_from_slice(&look.color);
            rgba[pixel + 3] = (ring.max(dot) * 255.0).round() as u8;
        }
    }
    rgba
}

/// 1 between `inner` and `outer`, fading to 0 over one pixel at both edges.
fn coverage(distance: f32, inner: f32, outer: f32) -> f32 {
    let from_inner = if inner <= 0.0 {
        1.0
    } else {
        (distance - inner + 0.5).clamp(0.0, 1.0)
    };
    let to_outer = (outer - distance + 0.5).clamp(0.0, 1.0);
    from_inner.min(to_outer)
}

pub struct Tray {
    icon: TrayIcon,
    mic: CheckMenuItem<Wry>,
    modes: [(Mode, CheckMenuItem<Wry>); 3],
    last: Mutex<Option<(Look, String)>>,
}

impl Tray {
    pub fn create(
        app: &AppHandle,
        tx: Sender<Msg>,
        shared: Arc<Shared>,
    ) -> tauri::Result<Arc<Self>> {
        let overlay = MenuItemBuilder::with_id("overlay", "Show / hide overlay").build(app)?;
        let control_center =
            MenuItemBuilder::with_id("control_center", "Control Center").build(app)?;
        let mic = CheckMenuItemBuilder::with_id("mic_mute", "Mute mic").build(app)?;
        let fast = CheckMenuItemBuilder::with_id("mode_fast", "Fast").build(app)?;
        let balanced = CheckMenuItemBuilder::with_id("mode_balanced", "Balanced")
            .checked(true)
            .build(app)?;
        let paranoid = CheckMenuItemBuilder::with_id("mode_paranoid", "Paranoid").build(app)?;
        let mode = SubmenuBuilder::with_id(app, "mode", "Mode")
            .items(&[&fast, &balanced, &paranoid])
            .build()?;
        let quit = MenuItemBuilder::with_id("quit", "Quit ACE").build(app)?;
        let menu = MenuBuilder::new(app)
            .items(&[&overlay, &control_center, &mic, &mode])
            .separator()
            .item(&quit)
            .build()?;

        let (first_look, tooltip) = look(&CoreStatus::default(), None);
        let modes = [
            (Mode::Fast, fast),
            (Mode::Balanced, balanced),
            (Mode::Paranoid, paranoid),
        ];
        let menu_modes = modes.clone();
        let menu_mic = mic.clone();
        let menu_shared = shared.clone();
        let icon = TrayIconBuilder::with_id("ace")
            .icon(Image::new_owned(render(first_look), ICON_SIZE, ICON_SIZE))
            .tooltip(&tooltip)
            .menu(&menu)
            .show_menu_on_left_click(false)
            .on_menu_event(move |app, event| {
                on_menu(
                    app,
                    event.id().as_ref(),
                    &tx,
                    &menu_shared,
                    &menu_mic,
                    &menu_modes,
                );
            })
            .on_tray_icon_event(|tray, event| {
                if let TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } = event
                {
                    crate::show_control_center(tray.app_handle());
                }
            })
            .build(app)?;
        Ok(Arc::new(Self {
            icon,
            mic,
            modes,
            last: Mutex::new(Some((first_look, tooltip))),
        }))
    }

    /// Show the current status: icon and tooltip, the mic tick and the mode ticks.
    pub fn refresh(&self, core: &CoreStatus, view: Option<&CoreView>) {
        let conversation = view.map(|v| v.conversation.as_str());
        let wanted = look(core, conversation);
        {
            let mut last = lock(&self.last);
            if last.as_ref() != Some(&wanted) {
                let _ = self.icon.set_icon(Some(Image::new_owned(
                    render(wanted.0),
                    ICON_SIZE,
                    ICON_SIZE,
                )));
                let _ = self.icon.set_tooltip(Some(&wanted.1));
                *last = Some(wanted);
            }
        }
        sync_checks(&self.mic, &self.modes, view);
    }
}

fn sync_checks(
    mic: &CheckMenuItem<Wry>,
    modes: &[(Mode, CheckMenuItem<Wry>); 3],
    view: Option<&CoreView>,
) {
    let _ = mic.set_checked(view.is_some_and(|v| v.conversation == "muted"));
    let current = view.map_or(Mode::Balanced, |v| v.mode);
    for (mode, item) in modes {
        let _ = item.set_checked(*mode == current);
    }
}

fn on_menu(
    app: &AppHandle,
    id: &str,
    tx: &Sender<Msg>,
    shared: &Shared,
    mic: &CheckMenuItem<Wry>,
    modes: &[(Mode, CheckMenuItem<Wry>); 3],
) {
    let send = |message| {
        let _ = tx.send(Msg::Send(message));
    };
    let tray_input = |action| ShellMessage::Input {
        action,
        source: Source::Tray,
        phase: Phase::Pressed,
    };
    match id {
        "overlay" => send(tray_input(Action::ToggleOverlay)),
        "control_center" => crate::show_control_center(app),
        "mic_mute" => {
            send(tray_input(Action::MicMute));
            // Windows ticked the item already; show the core's truth until it changes.
            sync_checks(mic, modes, shared.view().as_ref());
        }
        "mode_fast" | "mode_balanced" | "mode_paranoid" => {
            let mode = match id {
                "mode_fast" => Mode::Fast,
                "mode_paranoid" => Mode::Paranoid,
                _ => Mode::Balanced,
            };
            send(ShellMessage::SetMode { mode });
            for (item_mode, item) in modes {
                let _ = item.set_checked(*item_mode == mode); // the core confirms with a snapshot
            }
        }
        "quit" => {
            let _ = tx.send(Msg::Quit);
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn core(phase: CorePhase) -> CoreStatus {
        CoreStatus {
            phase,
            ..CoreStatus::default()
        }
    }

    #[test]
    fn looks_follow_the_core_and_the_conversation() {
        let running = core(CorePhase::Running);
        assert_eq!(
            look(&running, Some("asleep")).0,
            Look {
                color: CYAN,
                filled: true
            }
        );
        assert_eq!(look(&running, Some("thinking")).0.color, VIOLET);
        assert_eq!(look(&running, Some("muted")).0.color, GREY);
        assert_eq!(look(&running, Some("something_new")).0.color, CYAN);
        assert_eq!(
            look(&running, Some("awaiting_confirm")).1,
            "ACE — awaiting confirm"
        );
        assert_eq!(
            look(&core(CorePhase::Restarting), None).0,
            Look {
                color: AMBER,
                filled: false
            }
        );
        assert_eq!(look(&core(CorePhase::Stopped), None).0.color, RED);
        let safe = CoreStatus {
            safe_mode: true,
            ..running
        };
        assert_eq!(
            look(&safe, Some("asleep")),
            (
                Look {
                    color: ORANGE,
                    filled: true
                },
                "ACE — safe mode".into()
            )
        );
    }

    fn pixel(rgba: &[u8], x: usize, y: usize) -> &[u8] {
        let i = (y * ICON_SIZE as usize + x) * 4;
        &rgba[i..i + 4]
    }

    #[test]
    fn icons_are_a_ring_with_an_optional_dot() {
        let filled = render(Look {
            color: CYAN,
            filled: true,
        });
        let hollow = render(Look {
            color: RED,
            filled: false,
        });
        assert_eq!(filled.len(), (ICON_SIZE * ICON_SIZE * 4) as usize);
        assert_eq!(pixel(&filled, 16, 16), [0x22, 0xD3, 0xEE, 255]); // centre dot
        assert_eq!(pixel(&hollow, 16, 16)[3], 0);
        assert_eq!(pixel(&hollow, 16, 3), [0xF8, 0x71, 0x71, 255]); // on the ring
        assert_eq!(pixel(&filled, 16, 8)[3], 0); // between ring and dot
        assert_eq!(pixel(&filled, 0, 0)[3], 0); // corner
    }
}
