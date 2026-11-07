//! ACE desktop shell (Tauri 2): single instance, tray, global hotkeys, autostart, the Control
//! Center window, and the supervisor that keeps ace-core running (ACE_MASTER_PLAN.md S04, §5.6,
//! D-52). The shell stays thin: no business logic, no database (§5.2).

/// Debug builds print shell diagnostics to the `tauri dev` terminal; release builds have none.
macro_rules! shell_log {
    ($($arg:tt)*) => {
        if cfg!(debug_assertions) {
            eprintln!("[ace-desktop] {}", format_args!($($arg)*));
        }
    };
}

mod autostart;
mod core_process;
mod geometry;
mod hotkeys;
mod job;
mod overlay;
mod policy;
mod protocol;
mod status;
mod supervisor;
mod token;
mod tray;

use std::sync::mpsc;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;

use tauri::{AppHandle, Manager, RunEvent, State, WindowEvent};

use crate::autostart::{AUTOSTART_ARG, Autostart};
use crate::core_process::CoreCommand;
use crate::overlay::{CoreInput, Overlay};
use crate::status::{IpcInfo, Shared, ShellStatus};
use crate::supervisor::{Msg, Wiring};
use crate::tray::Tray;

pub const CONTROL_CENTER: &str = "control-center";
/// Passed to a second launch, asks the running ACE to quit (core first).
const QUIT_ARG: &str = "--quit";

/// Port and token for the UI's IPC client (§5.6 step 4); fails while the core is not running.
#[tauri::command]
fn get_ipc_info(shared: State<'_, Arc<Shared>>) -> Result<IpcInfo, String> {
    shared
        .ipc_info()
        .ok_or_else(|| "ace-core is not running".to_string())
}

/// The core's supervision state, hotkey registrations and autostart (for the banner).
#[tauri::command]
fn get_shell_status(shared: State<'_, Arc<Shared>>) -> ShellStatus {
    shared.status()
}

pub fn show_control_center(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(CONTROL_CENTER) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let (tx, rx) = mpsc::channel::<Msg>();
    let shared = Arc::new(Shared::default());
    let registry = Arc::new(Mutex::new(hotkeys::Registry::default()));
    let started_by_autostart = std::env::args().any(|arg| arg == AUTOSTART_ARG);

    // The overlay windows are created in setup; hotkeys can fire only after that.
    let overlay_cell: Arc<OnceLock<Arc<Overlay>>> = Arc::new(OnceLock::new());
    let hotkey_overlay = Arc::clone(&overlay_cell);
    let hotkey_tx = tx.clone();
    let hotkey_registry = registry.clone();
    let input_tx = tx.clone();
    let setup_tx = tx.clone();
    let setup_shared = shared.clone();
    let instance_tx = tx.clone();
    let exit_tx = tx;

    let app = tauri::Builder::default()
        // First, so that a second launch hands over and exits before anything else starts.
        .plugin(tauri_plugin_single_instance::init(
            move |app, args, _cwd| {
                if args.iter().any(|arg| arg == QUIT_ARG) {
                    // `ace-desktop --quit`: quit the running ACE gracefully (scripts, installer).
                    shell_log!("second launch with {QUIT_ARG}: quitting");
                    let _ = instance_tx.send(Msg::Quit);
                } else if !args.iter().any(|arg| arg == AUTOSTART_ARG) {
                    shell_log!("second launch: showing the Control Center");
                    show_control_center(app);
                }
            },
        ))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |_app, shortcut, event| {
                    let overlay = hotkey_overlay.get().map(Arc::as_ref);
                    hotkeys::on_event(&hotkey_registry, &hotkey_tx, overlay, shortcut, event);
                })
                .build(),
        )
        .manage(shared)
        .manage(CoreInput(input_tx))
        .invoke_handler(tauri::generate_handler![
            get_ipc_info,
            get_shell_status,
            overlay::overlay_state,
            overlay::overlay_hit_rects,
            overlay::overlay_orb_clicked,
            overlay::overlay_drag,
            overlay::overlay_close_sidebar,
            overlay::overlay_focus_input,
            overlay::overlay_sidebar_hidden,
            overlay::overlay_hide_for,
            overlay::overlay_report_focus,
            overlay::overlay_input,
            overlay::open_control_center,
        ])
        .on_window_event(|window, event| {
            let WindowEvent::CloseRequested { api, .. } = event else {
                return;
            };
            match window.label() {
                // Closing the Control Center only hides it: ACE keeps running in the tray.
                CONTROL_CENTER => {
                    api.prevent_close();
                    let _ = window.hide();
                }
                // Alt+F4 on the sidebar closes the sidebar; the orb cannot be closed.
                overlay::SIDEBAR => {
                    api.prevent_close();
                    if let Some(overlay) = window.try_state::<Arc<Overlay>>() {
                        overlay.close_sidebar();
                    }
                }
                overlay::ORB => api.prevent_close(),
                _ => {}
            }
        })
        .setup(move |app| {
            let handle = app.handle().clone();
            let overlay = Overlay::create(&handle)?;
            app.manage(Arc::clone(&overlay));
            let _ = overlay_cell.set(Arc::clone(&overlay));
            overlay.start()?;
            overlay.show_initial();
            let tray = Tray::create(
                &handle,
                setup_tx.clone(),
                setup_shared.clone(),
                Arc::clone(&overlay),
            )?;
            let autostart = match Autostart::for_current_exe() {
                Ok(autostart) => Some(autostart),
                Err(err) => {
                    shell_log!("autostart is not available: {err}");
                    None
                }
            };
            let command = if cfg!(debug_assertions) {
                CoreCommand::development()
            } else {
                CoreCommand::bundled(&handle.path().resource_dir()?)
            };
            supervisor::spawn(Wiring {
                app: handle.clone(),
                rx,
                tx: setup_tx,
                command,
                shared: setup_shared,
                tray,
                hotkeys: registry,
                autostart,
                overlay,
            })?;
            if !started_by_autostart {
                show_control_center(&handle);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the ACE desktop shell");

    app.run(move |_app, event| match event {
        // The user closed every window: stay in the tray.
        RunEvent::ExitRequested {
            code: None, api, ..
        } => api.prevent_exit(),
        // ACE is exiting: the core stops first (§5.6 step 6). After "Quit ACE" it already has.
        RunEvent::Exit => {
            let (done_tx, done_rx) = mpsc::channel();
            if exit_tx.send(Msg::Shutdown(done_tx)).is_ok() {
                let _ = done_rx.recv_timeout(supervisor::GRACE + Duration::from_secs(1));
            }
        }
        _ => {}
    });
}
