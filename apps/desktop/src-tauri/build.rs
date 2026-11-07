fn main() {
    // ACE's own commands get permissions too, so a window can only call them when a capability
    // allows it (least privilege, §15.1): `allow-get-ipc-info`, `allow-get-shell-status`.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["get_ipc_info", "get_shell_status"]),
    ))
    .expect("failed to run tauri-build");
}
