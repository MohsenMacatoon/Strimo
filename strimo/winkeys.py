"""Windows: make Space and the arrow keys always reach Strimo.

The playback engine draws into its own child window. On Windows that window can hold
the keyboard focus, and then key presses go to it instead of to Strimo. A low-level
keyboard hook sees every key press before any window does: while Strimo's main
window is the active window, Strimo handles Space and the arrows itself, no matter
which window has the focus. All other keys pass through untouched.

The hook only reacts while Strimo's main window is in front; in every other program
the keys behave exactly as normal.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32")

    WH_KEYBOARD_LL = 13
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
    VK_SPACE, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = 0x20, 0x25, 0x26, 0x27, 0x28
    VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
    LRESULT = ctypes.c_ssize_t

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    _user32.SetWindowsHookExW.restype = wintypes.HHOOK
    _user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    _user32.CallNextHookEx.restype = LRESULT
    _user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetFocus.restype = wintypes.HWND
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
    _user32.IsChild.restype = wintypes.BOOL
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
else:
    _user32 = None


def _pressed(vk: int) -> bool:
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


class KeyHook:
    """Routes Space / arrows to `handler(name, down, shift, repeat)` while `hwnd_fn()` is in front."""

    KEYS = {}

    def __init__(self, hwnd_fn, allowed_fn, handler, log=None):
        self.hwnd_fn = hwnd_fn          # -> int, Strimo's main window handle
        self.allowed_fn = allowed_fn    # -> bool, False while typing in a text box, dialogs open, ...
        self.handler = handler
        self.log = log
        self.hook = None
        self._proc = None
        self._down: set[int] = set()
        if _user32 is not None:
            self.KEYS = {VK_SPACE: "space", VK_LEFT: "left", VK_RIGHT: "right", VK_UP: "up", VK_DOWN: "down"}

    def install(self) -> bool:
        if _user32 is None or self.hook:
            return bool(self.hook)
        self._proc = HOOKPROC(self._callback)
        self.hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, _kernel32.GetModuleHandleW(None), 0)
        if not self.hook and self.log:
            self.log(f"keyboard hook could not be installed (error {ctypes.get_last_error()})")
        return bool(self.hook)

    def uninstall(self) -> None:
        if self.hook:
            _user32.UnhookWindowsHookEx(self.hook)
            self.hook = None

    def _ours_in_front(self) -> bool:
        fg = _user32.GetForegroundWindow()
        me = self.hwnd_fn()
        return bool(fg) and bool(me) and int(fg) == int(me)

    def _callback(self, code, wparam, lparam):
        # keep this fast: Windows drops hooks that take too long
        try:
            if code == 0 and wparam in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
                kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                name = self.KEYS.get(int(kb.vkCode))
                if name is not None:
                    down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    if not down and kb.vkCode in self._down:
                        # always finish a press we took, even if Strimo lost the front meanwhile
                        self._down.discard(kb.vkCode)
                        QTimer.singleShot(0, lambda n=name: self.handler(n, False, _pressed(VK_SHIFT), False))
                        return 1
                    if (down and self._ours_in_front() and not (_pressed(VK_CONTROL) or _pressed(VK_MENU)
                                                                  or _pressed(VK_LWIN) or _pressed(VK_RWIN))
                            and self.allowed_fn()):
                        repeat = kb.vkCode in self._down
                        self._down.add(kb.vkCode)
                        shift = _pressed(VK_SHIFT)
                        QTimer.singleShot(0, lambda n=name, s=shift, r=repeat: self.handler(n, True, s, r))
                        return 1  # handled: don't also deliver it to whichever window has focus
        except Exception:  # noqa: BLE001 - never break the keyboard
            pass
        return _user32.CallNextHookEx(self.hook, code, wparam, lparam)


def focus_is_lost(main_hwnd: int, video_hwnd: int) -> bool:
    """True when Strimo is in front but the keyboard focus sits in the engine's video window (or nowhere)."""
    if _user32 is None or not main_hwnd:
        return False
    if int(_user32.GetForegroundWindow() or 0) != int(main_hwnd):
        return False
    focus = _user32.GetFocus()
    if not focus:
        return True
    focus = int(focus)
    if video_hwnd and focus != int(video_hwnd) and _user32.IsChild(video_hwnd, focus):
        return True  # focus is inside the engine's own window
    return False
