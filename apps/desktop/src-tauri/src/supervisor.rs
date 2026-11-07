//! Keeps one ace-core running (S04 tasks 3, 4 and 7; §5.6; D-52): start it with a fresh token,
//! wait for READY, apply its snapshots (tray, hotkeys, autostart, overlay), restart it with backoff when it
//! stops on its own, switch to safe mode after 5 crashes in 5 minutes, and stop it before ACE exits.

use std::io;
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tauri::AppHandle;

use crate::autostart::Autostart;
use crate::core_process::{CoreCommand, CoreProcess};
use crate::hotkeys::{self, Registry};
use crate::overlay::Overlay;
use crate::policy::RestartPolicy;
use crate::protocol::{
    CoreLine, HotkeyProblem, MAX_ERROR_CHARS, ShellMessage, Snapshot, parse_line, truncate,
};
use crate::status::{AutostartStatus, CorePhase, CoreView, IpcInfo, Shared, ShellStatus};
use crate::token::new_token;
use crate::tray::Tray;

/// The core's own shutdown takes at most 5 s (§5.6); then the shell ends the process tree.
pub const GRACE: Duration = Duration::from_secs(6);
/// The first `uv run` after a dependency change may install packages first.
const READY_TIMEOUT: Duration = if cfg!(debug_assertions) {
    Duration::from_secs(180)
} else {
    Duration::from_secs(30)
};
const POLL: Duration = Duration::from_millis(100);
/// The core's limit for a shortcut text (`desktop_link.MAX_SHORTCUT_CHARS`).
const MAX_SHORTCUT_CHARS: usize = 64;

pub enum Msg {
    /// A line from the core's stdout.
    CoreLine { generation: u64, line: String },
    /// The core's stdout closed: it is exiting.
    CoreOutputClosed { generation: u64 },
    /// Forward to the core (hotkeys, tray). Dropped while no core is ready.
    Send(ShellMessage),
    /// Tray "Quit ACE": stop the core, then exit the app.
    Quit,
    /// The app is exiting for another reason: stop the core, then confirm.
    Shutdown(Sender<()>),
}

pub struct Wiring {
    pub app: AppHandle,
    pub rx: Receiver<Msg>,
    pub tx: Sender<Msg>,
    pub command: CoreCommand,
    pub shared: Arc<Shared>,
    pub tray: Arc<Tray>,
    pub hotkeys: Arc<Mutex<Registry>>,
    pub autostart: Option<Autostart>,
    pub overlay: Arc<Overlay>,
}

enum Ending {
    Crashed {
        code: Option<i32>,
        reason: String,
    },
    Quit {
        exit_app: bool,
        done: Option<Sender<()>>,
    },
}

pub fn spawn(wiring: Wiring) -> io::Result<()> {
    let supervisor = Supervisor {
        wiring,
        policy: RestartPolicy::default(),
        generation: 0,
    };
    thread::Builder::new()
        .name("ace-supervisor".into())
        .spawn(move || supervisor.run())?;
    Ok(())
}

struct Supervisor {
    wiring: Wiring,
    policy: RestartPolicy,
    generation: u64,
}

impl Supervisor {
    fn run(mut self) {
        loop {
            let (exit_app, done) = match self.run_core() {
                Ending::Quit { exit_app, done } => (exit_app, done),
                Ending::Crashed { code, reason } => {
                    let decision = self.policy.on_crash(Instant::now());
                    shell_log!(
                        "{reason}; restarting {}{}",
                        if decision.delay.is_zero() {
                            "now".to_string()
                        } else {
                            format!("in {} s", decision.delay.as_secs())
                        },
                        if decision.entered_safe_mode {
                            " in SAFE MODE"
                        } else {
                            ""
                        }
                    );
                    self.update(|status| {
                        let core = &mut status.core;
                        core.phase = CorePhase::Restarting;
                        core.restarts += 1;
                        core.recent_crashes = decision.recent_crashes;
                        core.safe_mode = decision.safe_mode;
                        core.retry_in_ms = Some(decision.delay.as_millis() as u64);
                        core.last_exit_code = code;
                        core.message = Some(if decision.entered_safe_mode {
                            format!(
                                "{reason}. The core crashed {} times in 5 minutes, so it restarts in safe mode.",
                                decision.recent_crashes
                            )
                        } else {
                            reason
                        });
                        core.port = None;
                    });
                    match self.wait(decision.delay) {
                        Some(quit) => quit,
                        None => continue,
                    }
                }
            };
            self.finish(exit_app, done);
            return;
        }
    }

    /// Start one core and look after it until it stops or ACE quits.
    fn run_core(&mut self) -> Ending {
        self.generation += 1;
        let generation = self.generation;
        let safe_mode = self.policy.safe_mode();
        self.wiring.shared.set_ipc_info(None);
        self.update(|status| {
            status.core.phase = CorePhase::Starting;
            status.core.safe_mode = safe_mode;
            status.core.retry_in_ms = None;
            status.core.port = None;
        });
        let token = match new_token() {
            Ok(token) => token,
            Err(err) => return crashed(None, format!("cannot create an IPC token: {err}")),
        };
        let mut core = match CoreProcess::spawn(
            &self.wiring.command,
            &token,
            safe_mode,
            generation,
            &self.wiring.tx,
        ) {
            Ok(core) => core,
            Err(err) => return crashed(None, format!("cannot start ace-core: {err}")),
        };
        shell_log!("core started (pid {}, safe mode: {safe_mode})", core.pid());
        let started = Instant::now();
        let mut ready = false;
        let mut last_report: Option<ShellMessage> = None;

        loop {
            match self.wiring.rx.recv_timeout(POLL) {
                Ok(Msg::CoreLine {
                    generation: g,
                    line,
                }) if g == generation => match parse_line(&line) {
                    Ok(CoreLine::Ready { port }) => {
                        ready = true;
                        self.policy.on_ready(Instant::now());
                        self.wiring.shared.set_ipc_info(Some(IpcInfo {
                            port,
                            token: token.clone(),
                        }));
                        self.update(|status| {
                            status.core.phase = CorePhase::Running;
                            status.core.port = Some(port);
                            status.core.message = None;
                        });
                        shell_log!("core ready on port {port}");
                    }
                    Ok(CoreLine::Snapshot(snapshot)) => {
                        self.apply_snapshot(&mut core, *snapshot, &mut last_report);
                    }
                    Ok(CoreLine::Other) => shell_log!("core stdout: {}", line.trim_end()),
                    Err(err) => shell_log!("{err}"),
                },
                Ok(Msg::CoreOutputClosed { generation: g }) if g == generation => {
                    let code = core.finish(Duration::from_secs(2)).and_then(|s| s.code());
                    return crashed(code, format!("ace-core stopped (exit code {})", show(code)));
                }
                Ok(Msg::CoreLine { .. } | Msg::CoreOutputClosed { .. }) => {} // an earlier core
                Ok(Msg::Send(message)) => {
                    if ready && let Err(err) = core.send(&message.to_line()) {
                        shell_log!("cannot reach the core: {err}");
                    }
                }
                Ok(Msg::Quit) => {
                    self.stop(core);
                    return Ending::Quit {
                        exit_app: true,
                        done: None,
                    };
                }
                Ok(Msg::Shutdown(done)) => {
                    self.stop(core);
                    return Ending::Quit {
                        exit_app: false,
                        done: Some(done),
                    };
                }
                Err(RecvTimeoutError::Timeout) => {}
                Err(RecvTimeoutError::Disconnected) => {
                    self.stop(core);
                    return Ending::Quit {
                        exit_app: false,
                        done: None,
                    };
                }
            }
            if let Some(status) = core.exited() {
                let code = status.code();
                let _ = core.finish(Duration::ZERO);
                return crashed(code, format!("ace-core stopped (exit code {})", show(code)));
            }
            if !ready && started.elapsed() > READY_TIMEOUT {
                let _ = core.finish(Duration::ZERO);
                return crashed(None, "ace-core did not report READY in time".into());
            }
        }
    }

    /// Apply what the core wants (hotkeys, autostart, tray) and report problems back to it.
    fn apply_snapshot(
        &mut self,
        core: &mut CoreProcess,
        snapshot: Snapshot,
        last_report: &mut Option<ShellMessage>,
    ) {
        self.wiring.shared.set_view(Some(CoreView {
            conversation: snapshot.state.conversation.clone(),
            mode: snapshot.mode,
        }));
        // Game mode and the paused_overlay flag hide the overlay (§14.2, D-15); window work runs
        // on the main thread.
        let overlay = Arc::clone(&self.wiring.overlay);
        let (config, paused) = (
            snapshot.overlay,
            snapshot.state.paused_overlay || snapshot.state.game_mode,
        );
        let _ = self
            .wiring
            .app
            .run_on_main_thread(move || overlay.apply_config(config, paused));
        let hotkey_statuses =
            hotkeys::apply(&self.wiring.app, &self.wiring.hotkeys, &snapshot.hotkeys);
        let autostart = match &self.wiring.autostart {
            Some(autostart) => match autostart.apply(snapshot.autostart) {
                Ok(enabled) => AutostartStatus {
                    enabled,
                    error: None,
                },
                Err(err) => AutostartStatus {
                    enabled: false,
                    error: Some(err),
                },
            },
            None => AutostartStatus {
                enabled: false,
                error: Some("autostart is not available".into()),
            },
        };
        self.update(|status| {
            status.hotkeys = hotkey_statuses.clone();
            status.autostart = autostart.clone();
        });

        let report = ShellMessage::DesktopStatus {
            hotkey_problems: hotkey_statuses
                .iter()
                .filter(|hotkey| !hotkey.registered)
                .filter_map(|hotkey| {
                    Some(HotkeyProblem {
                        action: hotkey.action,
                        shortcut: hotkey.shortcut.clone()?,
                        error: truncate(
                            hotkey.error.as_deref().unwrap_or("not registered"),
                            MAX_ERROR_CHARS,
                        ),
                        suggestion: hotkey
                            .suggestion
                            .clone()
                            .filter(|s| s.chars().count() <= MAX_SHORTCUT_CHARS),
                    })
                })
                .collect(),
            autostart_error: autostart
                .error
                .as_deref()
                .map(|e| truncate(e, MAX_ERROR_CHARS)),
        };
        if last_report.as_ref() != Some(&report) && core.send(&report.to_line()).is_ok() {
            *last_report = Some(report);
        }
    }

    /// Stop the core gracefully (core first, §5.6 step 6).
    fn stop(&self, core: CoreProcess) {
        self.update(|status| status.core.phase = CorePhase::Stopping);
        let code = core.stop(GRACE).and_then(|s| s.code());
        shell_log!("core stopped (exit code {})", show(code));
    }

    /// Wait before the next start. Returns a quit request that arrived meanwhile.
    fn wait(&self, delay: Duration) -> Option<(bool, Option<Sender<()>>)> {
        let deadline = Instant::now() + delay;
        loop {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return None;
            }
            match self.wiring.rx.recv_timeout(left) {
                Ok(Msg::Quit) => return Some((true, None)),
                Ok(Msg::Shutdown(done)) => return Some((false, Some(done))),
                Ok(_) => {} // input while no core runs has nowhere to go
                Err(RecvTimeoutError::Timeout) => return None,
                Err(RecvTimeoutError::Disconnected) => return Some((false, None)),
            }
        }
    }

    fn finish(&self, exit_app: bool, done: Option<Sender<()>>) {
        self.wiring.shared.set_ipc_info(None);
        self.update(|status| {
            status.core.phase = CorePhase::Stopped;
            status.core.port = None;
            status.core.retry_in_ms = None;
        });
        if let Some(done) = done {
            let _ = done.send(());
        }
        if exit_app {
            self.wiring.app.exit(0);
        }
    }

    fn update(&self, change: impl FnOnce(&mut ShellStatus)) {
        let status = self.wiring.shared.update(&self.wiring.app, change);
        self.wiring
            .tray
            .refresh(&status.core, self.wiring.shared.view().as_ref());
    }
}

fn crashed(code: Option<i32>, reason: String) -> Ending {
    Ending::Crashed { code, reason }
}

fn show(code: Option<i32>) -> String {
    code.map_or_else(|| "unknown".into(), |code| code.to_string())
}
