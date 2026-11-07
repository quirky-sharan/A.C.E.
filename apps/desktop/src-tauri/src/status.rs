//! What the shell knows right now, shared by the supervisor, the tray and the Tauri commands.
//! Every change is pushed to the UI as the `ace://shell-status` event (the banner, S04 task 4).

use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter};

use crate::protocol::{Action, Mode};

pub const STATUS_EVENT: &str = "ace://shell-status";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CorePhase {
    Starting,
    Running,
    Restarting,
    Stopping,
    Stopped,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CoreStatus {
    pub phase: CorePhase,
    pub safe_mode: bool,
    /// How often the core has been started again after stopping on its own.
    pub restarts: u32,
    pub recent_crashes: usize,
    /// While restarting: the wait before the next start.
    pub retry_in_ms: Option<u64>,
    pub last_exit_code: Option<i32>,
    /// A short explanation for the banner (never contains the token).
    pub message: Option<String>,
    pub port: Option<u16>,
}

impl Default for CoreStatus {
    fn default() -> Self {
        Self {
            phase: CorePhase::Starting,
            safe_mode: false,
            restarts: 0,
            recent_crashes: 0,
            retry_in_ms: None,
            last_exit_code: None,
            message: None,
            port: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HotkeyStatus {
    pub action: Action,
    /// None: no hotkey is set for this action.
    pub shortcut: Option<String>,
    pub registered: bool,
    pub error: Option<String>,
    pub suggestion: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AutostartStatus {
    pub enabled: bool,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ShellStatus {
    pub core: CoreStatus,
    pub hotkeys: Vec<HotkeyStatus>,
    pub autostart: AutostartStatus,
}

/// Where the UI connects (§5.6 step 4). Only handed out through the `get_ipc_info` command.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IpcInfo {
    pub port: u16,
    pub token: String,
}

/// The core's latest snapshot, as far as the tray cares.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CoreView {
    pub conversation: String,
    pub mode: Mode,
}

#[derive(Default)]
pub struct Shared {
    status: Mutex<ShellStatus>,
    ipc: Mutex<Option<IpcInfo>>,
    view: Mutex<Option<CoreView>>,
}

impl Shared {
    pub fn status(&self) -> ShellStatus {
        lock(&self.status).clone()
    }

    pub fn ipc_info(&self) -> Option<IpcInfo> {
        lock(&self.ipc).clone()
    }

    pub fn set_ipc_info(&self, info: Option<IpcInfo>) {
        *lock(&self.ipc) = info;
    }

    pub fn view(&self) -> Option<CoreView> {
        lock(&self.view).clone()
    }

    pub fn set_view(&self, view: Option<CoreView>) {
        *lock(&self.view) = view;
    }

    /// Change the status and tell the UI if anything changed.
    pub fn update(&self, app: &AppHandle, change: impl FnOnce(&mut ShellStatus)) -> ShellStatus {
        let (status, changed) = {
            let mut status = lock(&self.status);
            let before = status.clone();
            change(&mut status);
            (status.clone(), *status != before)
        };
        if changed {
            shell_log!(
                "status: core {:?}{}, restarts {}, hotkeys registered {}/{}",
                status.core.phase,
                if status.core.safe_mode {
                    " (safe mode)"
                } else {
                    ""
                },
                status.core.restarts,
                status.hotkeys.iter().filter(|h| h.registered).count(),
                status
                    .hotkeys
                    .iter()
                    .filter(|h| h.shortcut.is_some())
                    .count(),
            );
            let _ = app.emit(STATUS_EVENT, status.clone());
        }
        status
    }
}

/// A poisoned lock only means another thread panicked mid-update; the data is still usable.
pub fn lock<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}
