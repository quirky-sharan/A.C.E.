//! Start ACE when Sharan signs in (S04 task 6, FR-CORE-1), following the core setting
//! `desktop.autostart` (default off until M2). Uses `auto-launch`, the library inside
//! tauri-plugin-autostart, directly so that ACE only ever writes the current user's Run key
//! (the plugin first tries the all-users key when elevated) and the exe path is quoted.

use auto_launch::{AutoLaunch, WindowsEnableMode};

/// Passed by the Run entry; ACE then starts in the tray without opening the Control Center.
pub const AUTOSTART_ARG: &str = "--autostart";

pub struct Autostart(AutoLaunch);

impl Autostart {
    pub fn for_current_exe() -> std::io::Result<Self> {
        let exe = std::env::current_exe()?;
        // A debug build gets its own entry, so testing never replaces the installed app's one.
        let name = if cfg!(debug_assertions) {
            "ACE (dev build)"
        } else {
            "ACE"
        };
        let path = format!("\"{}\"", exe.display());
        Ok(Self(AutoLaunch::new(
            name,
            &path,
            WindowsEnableMode::CurrentUser,
            &[AUTOSTART_ARG],
        )))
    }

    /// Make the Run entry match `wanted`; returns whether autostart is now on.
    pub fn apply(&self, wanted: bool) -> Result<bool, String> {
        let enabled = self.0.is_enabled().map_err(|err| err.to_string())?;
        if enabled != wanted {
            let result = if wanted {
                self.0.enable()
            } else {
                self.0.disable()
            };
            result.map_err(|err| err.to_string())?;
        }
        Ok(wanted)
    }
}
