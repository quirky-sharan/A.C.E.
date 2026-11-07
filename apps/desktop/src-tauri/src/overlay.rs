//! The overlay (S06, §14.1–§14.3, D-40, D-55): the edge orb and the slide-out sidebar.
//!
//! Both are transparent, undecorated, always-on-top windows. They are created hidden and are then
//! shown (without activation) and hidden with plain `ShowWindow`, never through Tauri: tao's show
//! activates the window, and tao re-runs `ShowWindow(SW_SHOW)` on every window-flag change, so no
//! tao window setter is used after creation. A window is shown only while it has something to
//! show; a closed sidebar is really hidden, because when the app Sharan is using closes, Windows
//! activates the window it remembers as last active, even a WS_EX_NOACTIVATE one.
//! Click-through is set directly on the extended style (WS_EX_TRANSPARENT | WS_EX_LAYERED) from a
//! ~60 Hz cursor-polling thread, using the hit rectangles the UI reports. The windows are
//! WS_EX_NOACTIVATE and owned by a hidden window, so they never take focus by themselves and stay
//! out of the taskbar and Alt+Tab. Focus moves only on purpose: the summon hotkey or a click into
//! the sidebar's text box; closing the sidebar gives it back to the window Sharan was using.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, State, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder,
};
use windows_sys::Win32::Foundation::{HWND, POINT};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON, VK_RBUTTON};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, GWL_EXSTYLE, GWLP_HWNDPARENT, GetCursorPos, GetForegroundWindow,
    GetShellWindow, GetWindowLongPtrW, HWND_TOPMOST, IsWindow, IsWindowVisible, SW_HIDE,
    SW_SHOWNOACTIVATE, SWP_ASYNCWINDOWPOS, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOOWNERZORDER,
    SWP_NOSIZE, SetForegroundWindow, SetWindowLongPtrW, SetWindowPos, ShowWindow, WS_EX_LAYERED,
    WS_EX_TRANSPARENT, WS_POPUP,
};

use crate::geometry::{self, CssRect, Edge, Rect};
use crate::protocol::{Action, MonitorPolicy, OverlayConfig, Phase, ShellMessage, Source};
use crate::status::lock;
use crate::supervisor::Msg;

pub const ORB: &str = "orb";
pub const SIDEBAR: &str = "sidebar";
/// Sent to the orb window when it should appear or disappear.
pub const ORB_EVENT: &str = "ace://overlay-orb";
/// Sent to the sidebar window when it opens or closes.
pub const SIDEBAR_EVENT: &str = "ace://overlay-sidebar";
/// ~60 Hz cursor polling (D-40).
const TICK: Duration = Duration::from_millis(16);
/// Every ~2 s: topmost re-assertion, display / taskbar changes, the end of "hide for 1 hour".
const HOUSEKEEPING_TICKS: u32 = 125;
/// A summon older than this is not measured any more.
const SUMMON_WINDOW: Duration = Duration::from_secs(5);
/// A closed sidebar's window is hidden when its page says the slide-out ended, or after this long.
const HIDE_FALLBACK: Duration = Duration::from_secs(1);
const CLICK_THROUGH: isize = (WS_EX_TRANSPARENT | WS_EX_LAYERED) as isize;

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OrbEvent {
    pub visible: bool,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SidebarEvent {
    pub open: bool,
    pub focus: bool,
    pub edge: &'static str,
}

/// What a newly loaded overlay page should show (it may miss the events sent before it loaded).
#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OverlayView {
    pub orb_visible: bool,
    pub sidebar_open: bool,
    pub edge: &'static str,
}

#[derive(Default)]
struct OverlayState {
    config: OverlayConfig,
    /// The core paused the overlay (game mode or the paused_overlay flag).
    paused: bool,
    /// Hidden with the hotkey or the tray until shown again.
    user_hidden: bool,
    /// "Hide for 1 hour".
    hidden_until: Option<Instant>,
    sidebar_open: bool,
    /// When the sidebar last closed, until its window is hidden.
    sidebar_closed_at: Option<Instant>,
    /// What the orb page was last told (and whether its window is shown).
    orb_visible: bool,
    /// The work area and scale factor of the monitor the overlay is on.
    work: Option<(Rect, f64)>,
    orb: Option<Rect>,
    sidebar: Option<Rect>,
    hit: HashMap<&'static str, Vec<CssRect>>,
    dragging: bool,
    summoned_at: Option<Instant>,
    /// The window to give focus back to when the sidebar closes (as an integer handle).
    previous_foreground: Option<isize>,
}

impl OverlayState {
    fn overlay_on(&self) -> bool {
        !self.user_hidden && self.hidden_until.is_none() && !self.paused
    }

    fn edge_name(&self) -> &'static str {
        match self.config.edge {
            Edge::Right => "right",
            Edge::Left => "left",
        }
    }
}

pub struct Overlay {
    app: AppHandle,
    state: Mutex<OverlayState>,
    /// Native handles of the two windows (integers, so the polling thread can use them).
    orb_hwnd: isize,
    sidebar_hwnd: isize,
}

impl Overlay {
    /// Create the two overlay windows, hidden; `sync` shows them when they have something to show.
    /// Call on the main thread during setup.
    pub fn create(app: &AppHandle) -> tauri::Result<Arc<Self>> {
        let owner = hidden_owner();
        let mut handles = Vec::new();
        for (label, width, height) in [
            (ORB, geometry::ORB_WINDOW, geometry::ORB_WINDOW),
            (SIDEBAR, geometry::SIDEBAR_WIDTH, 600.0),
        ] {
            let window = WebviewWindowBuilder::new(app, label, WebviewUrl::default())
                .title(format!("ACE {label}"))
                .inner_size(width, height)
                .transparent(true)
                .decorations(false)
                .shadow(false)
                .resizable(false)
                .always_on_top(true)
                .skip_taskbar(true)
                .focusable(false)
                .focused(false)
                .visible(false) // shown and hidden with `show_window`, never through tao
                .build()?;
            let hwnd = window.hwnd().map(|handle| handle.0 as isize).unwrap_or(0);
            if hwnd != 0 && owner != 0 {
                // SAFETY: both are valid top-level windows of this process. An owned window stays
                // out of the taskbar and Alt+Tab.
                unsafe { SetWindowLongPtrW(hwnd as HWND, GWLP_HWNDPARENT, owner) };
            }
            set_click_through(hwnd, true); // nothing is clickable until the page reports its hit areas
            handles.push(hwnd);
        }
        Ok(Arc::new(Self {
            app: app.clone(),
            state: Mutex::new(OverlayState::default()),
            orb_hwnd: handles[0],
            sidebar_hwnd: handles[1],
        }))
    }

    /// Start the cursor-polling / housekeeping thread.
    pub fn start(self: &Arc<Self>) -> std::io::Result<()> {
        let overlay = Arc::clone(self);
        thread::Builder::new()
            .name("ace-overlay".into())
            .spawn(move || {
                shell_log!("overlay: cursor polling started");
                let mut tick: u32 = 0;
                loop {
                    thread::sleep(TICK);
                    tick = tick.wrapping_add(1);
                    overlay.poll_cursor();
                    if tick.is_multiple_of(HOUSEKEEPING_TICKS) {
                        let target = Arc::clone(&overlay);
                        if let Err(err) = overlay
                            .app
                            .run_on_main_thread(move || target.housekeeping())
                        {
                            shell_log!("overlay: housekeeping not scheduled: {err}");
                        }
                    }
                }
            })?;
        Ok(())
    }

    /// First placement when ACE starts (the core's settings follow with its first snapshot).
    pub fn show_initial(&self) {
        self.place(true);
        self.sync();
    }

    fn window(&self, label: &str) -> Option<WebviewWindow> {
        self.app.get_webview_window(label)
    }

    /// What a freshly loaded overlay page should show.
    pub fn view(&self) -> OverlayView {
        let state = lock(&self.state);
        OverlayView {
            orb_visible: state.orb_visible,
            sidebar_open: state.sidebar_open,
            edge: state.edge_name(),
        }
    }

    // ---- actions (main thread) ----

    /// New settings or core flags from the core's snapshot.
    pub fn apply_config(&self, config: OverlayConfig, paused: bool) {
        let was_open = {
            let mut state = lock(&self.state);
            state.config = config;
            state.paused = paused;
            state.sidebar_open
        };
        self.place(false);
        if paused && was_open {
            self.close_sidebar();
        }
        self.sync();
    }

    /// The summon hotkey (D-29): open the sidebar on the cursor's monitor and focus its input.
    pub fn summon(&self) {
        {
            let mut state = lock(&self.state);
            state.summoned_at = Some(Instant::now());
            state.sidebar_open = true;
            state.user_hidden = false;
            state.hidden_until = None;
        }
        self.place(true);
        self.sync();
        self.take_focus();
        self.notify_sidebar(true);
    }

    /// A click on the orb: open or close the sidebar, without taking focus.
    pub fn orb_clicked(&self) {
        let open = !lock(&self.state).sidebar_open;
        if open {
            lock(&self.state).sidebar_open = true;
            self.sync();
            self.notify_sidebar(false);
        } else {
            self.close_sidebar();
        }
    }

    pub fn close_sidebar(&self) {
        let previous = {
            let mut state = lock(&self.state);
            state.sidebar_open = false;
            state.sidebar_closed_at = Some(Instant::now());
            state.previous_foreground.take()
        };
        self.give_focus_back(previous);
        self.sync();
        let edge = lock(&self.state).edge_name();
        let _ = self.app.emit_to(
            SIDEBAR,
            SIDEBAR_EVENT,
            SidebarEvent {
                open: false,
                focus: false,
                edge,
            },
        );
    }

    /// Sharan clicked into the sidebar's text box: let it take keyboard focus.
    pub fn focus_input(&self) {
        self.take_focus();
    }

    /// The sidebar page finished sliding out: hide its window, unless it was opened again since.
    pub fn sidebar_hidden(&self) {
        let closed = {
            let mut state = lock(&self.state);
            if !state.sidebar_open {
                state.sidebar_closed_at = None;
            }
            !state.sidebar_open
        };
        if closed {
            show_window(self.sidebar_hwnd, false);
        }
    }

    /// The hide / show hotkey and the tray item.
    pub fn toggle(&self) {
        let (visible, open) = {
            let state = lock(&self.state);
            (state.sidebar_open || state.overlay_on(), state.sidebar_open)
        };
        if visible {
            lock(&self.state).user_hidden = true;
            if open {
                self.close_sidebar();
            }
        } else {
            {
                let mut state = lock(&self.state);
                state.user_hidden = false;
                state.hidden_until = None;
            }
            self.place(true);
        }
        self.sync();
    }

    /// "Hide for 1 hour" (§14.2): everything hides until then, or until shown again.
    pub fn hide_for(&self, minutes: u32) {
        lock(&self.state).hidden_until =
            Some(Instant::now() + Duration::from_secs(u64::from(minutes) * 60));
        self.close_sidebar();
        self.sync();
    }

    /// The UI reports where its clickable parts are (CSS pixels).
    pub fn set_hit_rects(&self, label: &str, rects: Vec<CssRect>) {
        let key = match label {
            ORB => ORB,
            SIDEBAR => SIDEBAR,
            _ => return,
        };
        lock(&self.state).hit.insert(key, rects);
    }

    /// Dragging the orb along its edge. Returns the new `orb_y` when the drag ends.
    pub fn drag(&self, phase: &str) -> Option<f64> {
        let mut state = lock(&self.state);
        match phase {
            "start" => {
                state.dragging = true;
                None
            }
            "end" => {
                state.dragging = false;
                let (work, scale) = state.work?;
                let orb = state.orb?;
                let orb_y = geometry::orb_y_for(work, scale, orb.y + orb.height / 2);
                state.config.orb_y = orb_y;
                Some(orb_y)
            }
            _ => None,
        }
    }

    /// Time from the summon hotkey to the focused input, for NFR-1 (≤ 150 ms).
    pub fn summon_latency(&self) -> Option<u128> {
        let started = lock(&self.state).summoned_at.take()?;
        let elapsed = started.elapsed();
        (elapsed <= SUMMON_WINDOW).then_some(elapsed.as_millis())
    }

    // ---- focus ----

    /// Make the sidebar the foreground window, remembering where focus was.
    fn take_focus(&self) {
        // SAFETY: plain window-manager queries and calls on valid or null handles.
        unsafe {
            let foreground = GetForegroundWindow() as isize;
            if foreground != 0 && foreground != self.sidebar_hwnd && foreground != self.orb_hwnd {
                lock(&self.state).previous_foreground = Some(foreground);
            }
            // WS_EX_NOACTIVATE windows can still be activated this way (Win32 docs).
            SetForegroundWindow(self.sidebar_hwnd as HWND);
        }
    }

    /// If the sidebar has focus, hand it back to the window Sharan was using (or the desktop).
    fn give_focus_back(&self, previous: Option<isize>) {
        // SAFETY: as above; IsWindow guards against a window that closed meanwhile.
        unsafe {
            if GetForegroundWindow() as isize != self.sidebar_hwnd {
                return;
            }
            let target = previous
                .filter(|handle| IsWindow(*handle as HWND) != 0)
                .unwrap_or(GetShellWindow() as isize);
            SetForegroundWindow(target as HWND);
        }
    }

    // ---- placement and visibility (main thread) ----

    /// Put the windows on the right monitor. `follow_cursor`: move to the cursor's monitor
    /// (when the overlay appears); otherwise stay on the current one and only adapt to changes.
    fn place(&self, follow_cursor: bool) {
        let (policy, current) = {
            let state = lock(&self.state);
            (state.config.monitor, state.orb)
        };
        let point = match (policy, current) {
            (MonitorPolicy::Primary, _) => None,
            (MonitorPolicy::Cursor, Some(rect)) if !follow_cursor => {
                Some((rect.x + rect.width / 2, rect.y + rect.height / 2))
            }
            (MonitorPolicy::Cursor, _) => cursor(),
        };
        let monitor = point
            .and_then(|(x, y)| {
                self.app
                    .monitor_from_point(f64::from(x), f64::from(y))
                    .ok()
                    .flatten()
            })
            .or_else(|| self.app.primary_monitor().ok().flatten());
        let Some(monitor) = monitor else { return };
        let area = monitor.work_area();
        let work = Rect {
            x: area.position.x,
            y: area.position.y,
            width: i32::try_from(area.size.width).unwrap_or(i32::MAX),
            height: i32::try_from(area.size.height).unwrap_or(i32::MAX),
        };
        let scale = monitor.scale_factor();
        let moves = {
            let mut state = lock(&self.state);
            state.work = Some((work, scale));
            let orb = geometry::orb_rect(work, scale, state.config.edge, state.config.orb_y);
            let sidebar = geometry::sidebar_rect(work, scale, state.config.edge);
            let mut moves = Vec::new();
            if state.orb != Some(orb) && !state.dragging {
                state.orb = Some(orb);
                moves.push((ORB, orb));
            }
            if state.sidebar != Some(sidebar) {
                state.sidebar = Some(sidebar);
                moves.push((SIDEBAR, sidebar));
            }
            moves
        };
        for (label, rect) in moves {
            if let Some(window) = self.window(label) {
                // tao moves and resizes with SWP_NOACTIVATE.
                let _ = window.set_position(PhysicalPosition::new(rect.x, rect.y));
                let _ = window.set_size(PhysicalSize::new(
                    u32::try_from(rect.width).unwrap_or(1),
                    u32::try_from(rect.height).unwrap_or(1),
                ));
            }
        }
    }

    /// Show the open sidebar's window, and show or hide the orb (its window and its page).
    /// A closed sidebar's window is hidden later, once its page has slid out (`sidebar_hidden`).
    fn sync(&self) {
        let (change, sidebar_open) = {
            let mut state = lock(&self.state);
            if state
                .hidden_until
                .is_some_and(|until| Instant::now() >= until)
            {
                state.hidden_until = None;
                shell_log!("overlay: hide timer ended");
            }
            let want = state.overlay_on() && !state.sidebar_open;
            let change = (want != state.orb_visible).then(|| {
                state.orb_visible = want;
                want
            });
            (change, state.sidebar_open)
        };
        if sidebar_open {
            show_window(self.sidebar_hwnd, true);
        }
        if let Some(visible) = change {
            let _ = self.app.emit_to(ORB, ORB_EVENT, OrbEvent { visible });
            show_window(self.orb_hwnd, visible);
        }
    }

    fn notify_sidebar(&self, focus: bool) {
        let edge = lock(&self.state).edge_name();
        let _ = self.app.emit_to(
            SIDEBAR,
            SIDEBAR_EVENT,
            SidebarEvent {
                open: true,
                focus,
                edge,
            },
        );
    }

    /// Every ~2 s on the main thread.
    fn housekeeping(&self) {
        static FIRST: AtomicBool = AtomicBool::new(true);
        if FIRST.swap(false, Ordering::Relaxed) {
            shell_log!("overlay: housekeeping running");
        }
        self.place(false);
        self.sync();
        let (orb_visible, sidebar_open, stale) = {
            let mut state = lock(&self.state);
            let stale = !state.sidebar_open
                && state
                    .sidebar_closed_at
                    .is_some_and(|closed| closed.elapsed() >= HIDE_FALLBACK);
            if stale {
                state.sidebar_closed_at = None;
            }
            (state.orb_visible, state.sidebar_open, stale)
        };
        // Re-assert what should be shown, in case anything else showed or hid a window.
        show_window(self.orb_hwnd, orb_visible);
        if sidebar_open {
            show_window(self.sidebar_hwnd, true);
        } else if stale {
            show_window(self.sidebar_hwnd, false); // its page never said the slide-out ended
        }
        raise_topmost(self.orb_hwnd);
        raise_topmost(self.sidebar_hwnd);
    }

    // ---- click-through (polling thread) ----

    fn poll_cursor(&self) {
        let Some((x, y)) = cursor() else { return };
        let pressed = key_down(VK_LBUTTON) || key_down(VK_RBUTTON);
        let mut drag_to = None;
        let wanted = {
            let mut state = lock(&self.state);
            if state.dragging
                && let (Some((work, scale)), Some(orb)) = (state.work, state.orb)
            {
                let orb_y = geometry::orb_y_for(work, scale, y);
                let rect = geometry::orb_rect(work, scale, state.config.edge, orb_y);
                if rect != orb {
                    state.orb = Some(rect);
                    drag_to = Some(rect);
                }
            }
            let scale = state.work.map_or(1.0, |(_, scale)| scale);
            let over = |label: &'static str, rect: Option<Rect>, active: bool| {
                active
                    && rect.is_some_and(|rect| {
                        let rects = state.hit.get(label).map_or(&[][..], Vec::as_slice);
                        geometry::hit((x, y), rect, scale, rects)
                    })
            };
            [
                (self.orb_hwnd, !over(ORB, state.orb, state.orb_visible)),
                (
                    self.sidebar_hwnd,
                    !over(SIDEBAR, state.sidebar, state.sidebar_open),
                ),
            ]
        };
        if let Some(rect) = drag_to
            && let Some(orb) = self.window(ORB)
        {
            let _ = orb.set_position(PhysicalPosition::new(rect.x, rect.y));
        }
        // Never switch while a button is held: a click or a drag must finish where it began.
        if !pressed {
            for (hwnd, through) in wanted {
                set_click_through(hwnd, through);
            }
        }
    }
}

/// Show (without activating) or hide one of the overlay windows. Never through Tauri: tao's show
/// activates the window. Main thread only.
fn show_window(hwnd: isize, show: bool) {
    if hwnd == 0 {
        return;
    }
    // SAFETY: a valid top-level window of this process, on the thread that created it.
    unsafe {
        if (IsWindowVisible(hwnd as HWND) != 0) != show {
            ShowWindow(hwnd as HWND, if show { SW_SHOWNOACTIVATE } else { SW_HIDE });
        }
    }
}

/// Let clicks pass through `hwnd` (or stop doing so). Reads the current style first, so it also
/// repairs the style if anything else rewrote it. Returns whether it changed something.
fn set_click_through(hwnd: isize, through: bool) -> bool {
    if hwnd == 0 {
        return false;
    }
    // SAFETY: reading and writing the extended style of one of our own windows.
    unsafe {
        let style = GetWindowLongPtrW(hwnd as HWND, GWL_EXSTYLE);
        let wanted = if through {
            style | CLICK_THROUGH
        } else {
            style & !CLICK_THROUGH
        };
        if wanted == style {
            return false;
        }
        SetWindowLongPtrW(hwnd as HWND, GWL_EXSTYLE, wanted);
        true
    }
}

/// A hidden, never-shown window that owns the overlay windows (keeps them out of Alt+Tab).
fn hidden_owner() -> isize {
    let class: Vec<u16> = "STATIC\0".encode_utf16().collect();
    let title: Vec<u16> = "ACE overlay owner\0".encode_utf16().collect();
    // SAFETY: a plain hidden popup of the predefined STATIC class; all pointers are valid.
    unsafe {
        CreateWindowExW(
            0,
            class.as_ptr(),
            title.as_ptr(),
            WS_POPUP,
            0,
            0,
            0,
            0,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            GetModuleHandleW(std::ptr::null()),
            std::ptr::null(),
        ) as isize
    }
}

/// The cursor position in physical screen pixels (the process is per-monitor DPI aware v2).
fn cursor() -> Option<(i32, i32)> {
    let mut point = POINT { x: 0, y: 0 };
    // SAFETY: `point` is a valid, writable POINT.
    let ok = unsafe { GetCursorPos(&mut point) };
    (ok != 0).then_some((point.x, point.y))
}

fn key_down(key: u16) -> bool {
    // SAFETY: plain query of the asynchronous key state.
    let state = unsafe { GetAsyncKeyState(i32::from(key)) };
    state < 0 // high bit set = currently down
}

/// Put the window back on top of the topmost group without activating it. Tauri only touches
/// the z-order when the always-on-top flag changes, so after a fullscreen app or a display
/// change the overlay is re-raised here.
fn raise_topmost(hwnd: isize) {
    if hwnd == 0 {
        return;
    }
    // SAFETY: a valid window handle; the flags keep position, size and activation unchanged.
    unsafe {
        SetWindowPos(
            hwnd as HWND,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_ASYNCWINDOWPOS,
        );
    }
}

// ---- commands for the overlay windows (synchronous, so they run on the main thread) ----

/// Lets overlay commands forward input to the core (via the supervisor).
pub struct CoreInput(pub Sender<Msg>);

#[tauri::command]
pub fn overlay_state(overlay: State<'_, Arc<Overlay>>) -> OverlayView {
    overlay.view()
}

#[tauri::command]
pub fn overlay_hit_rects(
    window: WebviewWindow,
    overlay: State<'_, Arc<Overlay>>,
    rects: Vec<CssRect>,
) {
    overlay.set_hit_rects(window.label(), rects);
}

#[tauri::command]
pub fn overlay_orb_clicked(overlay: State<'_, Arc<Overlay>>) {
    overlay.orb_clicked();
}

#[tauri::command]
pub fn overlay_drag(overlay: State<'_, Arc<Overlay>>, phase: String) -> Option<f64> {
    overlay.drag(&phase)
}

#[tauri::command]
pub fn overlay_close_sidebar(overlay: State<'_, Arc<Overlay>>) {
    overlay.close_sidebar();
}

#[tauri::command]
pub fn overlay_focus_input(overlay: State<'_, Arc<Overlay>>) {
    overlay.focus_input();
}

#[tauri::command]
pub fn overlay_sidebar_hidden(overlay: State<'_, Arc<Overlay>>) {
    overlay.sidebar_hidden();
}

#[tauri::command]
pub fn overlay_hide_for(overlay: State<'_, Arc<Overlay>>, minutes: u32) {
    overlay.hide_for(minutes.clamp(1, 24 * 60));
}

/// The sidebar focused its input after a summon; returns (and logs) the time it took.
#[tauri::command]
pub fn overlay_report_focus(overlay: State<'_, Arc<Overlay>>) -> Option<u64> {
    let elapsed = overlay.summon_latency()?;
    shell_log!("summon → input focused in {elapsed} ms");
    u64::try_from(elapsed).ok()
}

/// A footer toggle in the sidebar (e.g. mute mic): forwarded to the core like the tray's items.
#[tauri::command]
pub fn overlay_input(input: State<'_, CoreInput>, action: Action) {
    let _ = input.0.send(Msg::Send(ShellMessage::Input {
        action,
        source: Source::Overlay,
        phase: Phase::Pressed,
    }));
}

#[tauri::command]
pub fn open_control_center(app: AppHandle) {
    crate::show_control_center(&app);
}
