fn main() {
    // ACE's own commands get permissions too (`allow-<command>`), so a window can only call the
    // ones its capability lists (least privilege, §15.1): see capabilities/*.json.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "get_ipc_info",
            "get_shell_status",
            "overlay_state",
            "overlay_hit_rects",
            "overlay_orb_clicked",
            "overlay_drag",
            "overlay_close_sidebar",
            "overlay_focus_input",
            "overlay_sidebar_hidden",
            "overlay_hide_for",
            "overlay_report_focus",
            "overlay_input",
            "open_control_center",
        ]),
    ))
    .expect("failed to run tauri-build");
}
