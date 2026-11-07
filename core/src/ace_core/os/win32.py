"""Win32 implementations of the S08 adapters (D-57). Windows only; every call runs on the COM
thread (``ComThread``), which is a per-monitor-DPI-aware single-threaded apartment.

- Start menu: ``shell:AppsFolder`` through ``IShellFolder2`` (names, parsing names, AUMIDs and
  link targets), verified on this PC at S08 (PL-0010).
- Launch: Explorer's own ``IShellDispatch2.ShellExecute`` (the desktop folder view), so apps
  start like a click in Start: Explorer is their parent and they are not in ACE's Job Object
  (D-52), so they survive when ACE quits.
- Windows: ``EnumWindows`` + process exe / AUMID / elevation, DWM frame bounds for exact snaps.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any, Final

from ace_core.os.base import LaunchError, Rect, ShowState, Side, StartApp, WindowInfo
from ace_core.os.com import ComThread

_DWMWA_EXTENDED_FRAME_BOUNDS: Final = 9
_DWMWA_CLOAKED: Final = 14
_ERROR_SUCCESS: Final = 0
_SWC_DESKTOP: Final = 8
_SWFO_NEEDDISPATCH: Final = 1
_SVGIO_BACKGROUND: Final = 0
_SW_SHOWNORMAL: Final = 1

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.GetApplicationUserModelId.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.UINT),
    wintypes.LPWSTR,
]
_kernel32.GetApplicationUserModelId.restype = wintypes.LONG
_user32 = ctypes.WinDLL("user32")
_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsZoomed.restype = wintypes.BOOL
_dwmapi = ctypes.WinDLL("dwmapi")
_dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def _frame(hwnd: int) -> Rect | None:
    rect = wintypes.RECT()
    result = _dwmapi.DwmGetWindowAttribute(
        hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    return (rect.left, rect.top, rect.right, rect.bottom) if result == 0 else None


def _is_zoomed(hwnd: int) -> bool:
    # pywin32's win32gui does not export IsZoomed; call user32 directly.
    return bool(_user32.IsZoomed(hwnd))


def _cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD()
    result = _dwmapi.DwmGetWindowAttribute(
        hwnd, _DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
    )
    return result == 0 and value.value != 0


def _process_info(pid: int, ace_elevated: bool) -> tuple[str, str | None, bool]:
    """(exe path, packaged AUMID, runs with higher rights than ACE)."""
    import pywintypes
    import win32api
    import win32con
    import win32security

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except pywintypes.error:
        return "", None, not ace_elevated  # protected or system process
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buffer))
        ok = _kernel32.QueryFullProcessImageNameW(int(handle), 0, buffer, ctypes.byref(size))
        exe = buffer.value if ok else ""
        aumid_buffer = ctypes.create_unicode_buffer(256)
        length = wintypes.UINT(len(aumid_buffer))
        status = _kernel32.GetApplicationUserModelId(
            int(handle), ctypes.byref(length), aumid_buffer
        )
        aumid = aumid_buffer.value if status == _ERROR_SUCCESS else None
        try:
            token = win32security.OpenProcessToken(handle, win32con.TOKEN_QUERY)
        except pywintypes.error:
            elevated = not ace_elevated  # its token is closed to ACE: higher rights
        else:
            try:
                elevated = bool(
                    win32security.GetTokenInformation(token, win32security.TokenElevation)
                )
            finally:
                win32api.CloseHandle(token)
            elevated = elevated and not ace_elevated
        return exe, aumid, elevated
    finally:
        win32api.CloseHandle(handle)


def _window_aumid(hwnd: int) -> str | None:
    from win32com.propsys import propsys, pscon

    try:
        store: Any = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
        value = store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue()
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def _self_elevated() -> bool:
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        return bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
    finally:
        win32api.CloseHandle(token)


def _work_area(hwnd: int) -> Rect:
    import win32api
    import win32con

    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    return (left, top, right, bottom)


def _list_windows() -> list[WindowInfo]:
    import win32con
    import win32gui
    import win32process

    ace_elevated = _self_elevated()
    infos: dict[int, tuple[str, str | None, bool]] = {}
    found: list[WindowInfo] = []

    def visit(hwnd: int, _: Any) -> bool:
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title or _cloaked(hwnd):
            return True
        if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid not in infos:
            infos[pid] = _process_info(pid, ace_elevated)
        exe, aumid, elevated = infos[pid]
        rect = _frame(hwnd) or tuple(win32gui.GetWindowRect(hwnd))
        found.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                pid=pid,
                exe_path=exe,
                process_aumid=aumid,
                window_aumid=_window_aumid(hwnd),
                rect=(rect[0], rect[1], rect[2], rect[3]),
                minimized=bool(win32gui.IsIconic(hwnd)),
                maximized=_is_zoomed(hwnd),
                elevated=elevated,
                work_area=_work_area(hwnd),
            )
        )
        return True

    win32gui.EnumWindows(visit, None)  # top of the z-order first
    return found


def _focus(hwnd: int) -> bool:
    import pywintypes
    import win32con
    import win32gui

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except pywintypes.error:
        return False
    return bool(win32gui.GetForegroundWindow() == hwnd)


def _close(hwnd: int) -> bool:
    import pywintypes
    import win32con
    import win32gui

    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except pywintypes.error:
        return False  # e.g. ERROR_ACCESS_DENIED from UIPI
    return True


def _terminate(pid: int) -> bool:
    import pywintypes
    import win32api
    import win32con

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
    except pywintypes.error:
        return False
    try:
        win32api.TerminateProcess(handle, 1)
    except pywintypes.error:
        return False
    finally:
        win32api.CloseHandle(handle)
    return True


def _show(hwnd: int, state: ShowState) -> bool:
    import win32con
    import win32gui

    command = {
        "minimize": win32con.SW_MINIMIZE,
        "maximize": win32con.SW_MAXIMIZE,
        "restore": win32con.SW_RESTORE,
    }[state]
    win32gui.ShowWindow(hwnd, command)
    if state == "minimize":
        return bool(win32gui.IsIconic(hwnd))
    if state == "maximize":
        return _is_zoomed(hwnd)
    return not win32gui.IsIconic(hwnd) and not _is_zoomed(hwnd)


def _snap(hwnd: int, side: Side) -> Rect:
    import win32con
    import win32gui

    if win32gui.IsIconic(hwnd) or _is_zoomed(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    left, top, right, bottom = _work_area(hwnd)
    half = (right - left) // 2
    target = (
        (left, top, left + half, bottom) if side == "left" else (left + half, top, right, bottom)
    )
    outer = win32gui.GetWindowRect(hwnd)
    frame = _frame(hwnd) or outer
    # The visible frame sits inside invisible resize borders: grow the target by them.
    border_left, border_top = frame[0] - outer[0], frame[1] - outer[1]
    border_right, border_bottom = outer[2] - frame[2], outer[3] - frame[3]
    win32gui.SetWindowPos(
        hwnd,
        0,
        target[0] - border_left,
        target[1] - border_top,
        (target[2] - target[0]) + border_left + border_right,
        (target[3] - target[1]) + border_top + border_bottom,
        win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
    )
    return target


def _start_apps() -> list[StartApp]:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell, shellcon

    # pywintypes stubs are incomplete (they type the bind context as required); Any is deliberate.
    desktop: Any = shell.SHGetDesktopFolder()
    _, pidl, _ = desktop.ParseDisplayName(0, None, "shell:AppsFolder")
    folder: Any = desktop.BindToObject(pidl, None, shell.IID_IShellFolder2)
    target_key = propsys.PSGetPropertyKeyFromName("System.Link.TargetParsingPath")

    def detail(child: Any, key: Any) -> str | None:
        try:
            value = folder.GetDetailsEx(child, key)
        except pythoncom.com_error:
            return None
        return value if isinstance(value, str) and value else None

    apps: list[StartApp] = []
    for child in folder.EnumObjects(0, shellcon.SHCONTF_NONFOLDERS):
        name = folder.GetDisplayNameOf(child, shellcon.SHGDN_NORMAL)
        app_id = folder.GetDisplayNameOf(child, shellcon.SHGDN_FORPARSING)
        if not name or not app_id:
            continue
        apps.append(
            StartApp(
                name=name,
                app_id=app_id,
                aumid=detail(child, pscon.PKEY_AppUserModel_ID),
                exe_path=detail(child, target_key),
            )
        )
    return apps


class Win32StartMenu:
    def __init__(self, com: ComThread) -> None:
        self._com = com

    async def apps(self) -> list[StartApp]:
        return await self._com.run(_start_apps)


class ExplorerLauncher:
    """Launches through Explorer's ShellExecute (the desktop folder view's IShellDispatch2)."""

    def __init__(self, com: ComThread) -> None:
        self._com = com
        self._shell: Any = None  # lives on the COM thread only

    def _explorer_shell(self) -> Any:
        import pythoncom
        import win32com.client
        from win32com.shell import shell

        windows = win32com.client.Dispatch("Shell.Application").Windows()
        found = windows.FindWindowSW(0, 0, _SWC_DESKTOP, 0, _SWFO_NEEDDISPATCH)
        desktop = found[0] if isinstance(found, tuple) else found
        if desktop is None:
            raise LaunchError("Explorer's desktop is not running")
        provider = desktop._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
        browser = provider.QueryService(shell.SID_STopLevelBrowser, shell.IID_IShellBrowser)
        view = browser.QueryActiveShellView()
        folder_view = view.GetItemObject(_SVGIO_BACKGROUND, pythoncom.IID_IDispatch)
        return win32com.client.Dispatch(folder_view).Application

    def _launch(self, app_id: str) -> None:
        target = f"shell:AppsFolder\\{app_id}"
        for attempt in range(2):  # Explorer may have restarted since the last launch
            try:
                if self._shell is None:
                    self._shell = self._explorer_shell()
                self._shell.ShellExecute(target, "", "", "open", _SW_SHOWNORMAL)
                return
            except LaunchError:
                raise
            except Exception as exc:
                self._shell = None
                if attempt == 1:
                    raise LaunchError(f"Explorer could not start it: {exc}") from exc

    async def launch(self, app_id: str) -> None:
        await self._com.run(self._launch, app_id)


class Win32Windows:
    def __init__(self, com: ComThread) -> None:
        self._com = com

    async def windows(self) -> list[WindowInfo]:
        return await self._com.run(_list_windows)

    async def foreground(self) -> int:
        import win32gui

        return int(await self._com.run(win32gui.GetForegroundWindow))

    async def focus(self, hwnd: int) -> bool:
        return await self._com.run(_focus, hwnd)

    async def close(self, hwnd: int) -> bool:
        return await self._com.run(_close, hwnd)

    async def terminate(self, pid: int) -> bool:
        return await self._com.run(_terminate, pid)

    async def show(self, hwnd: int, state: ShowState) -> bool:
        return await self._com.run(_show, hwnd, state)

    async def snap(self, hwnd: int, side: Side) -> Rect:
        return await self._com.run(_snap, hwnd, side)

    async def ace_elevated(self) -> bool:
        return await self._com.run(_self_elevated)
