"""Win32だけに依存する薄いFFI。読み取るのはウィンドウ情報と画面画像のみ。"""

import ctypes as C
import os
from dataclasses import dataclass

from PIL import ImageGrab

from .models import SCAN_CODES

U32, I32, U16 = C.c_uint32, C.c_int32, C.c_uint16


class MouseInput(C.Structure):
    _fields_ = [
        ("dx", I32),
        ("dy", I32),
        ("mouseData", U32),
        ("dwFlags", U32),
        ("time", U32),
        ("dwExtraInfo", C.c_size_t),
    ]


class KeyboardInput(C.Structure):
    _fields_ = [
        ("wVk", U16),
        ("wScan", U16),
        ("dwFlags", U32),
        ("time", U32),
        ("dwExtraInfo", C.c_size_t),
    ]


class HardwareInput(C.Structure):
    _fields_ = [("uMsg", U32), ("wParamL", U16), ("wParamH", U16)]


class InputUnion(C.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]


class Input(C.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", U32), ("data", InputUnion)]


class Rect(C.Structure):
    _fields_ = [("left", I32), ("top", I32), ("right", I32), ("bottom", I32)]


class Point(C.Structure):
    _fields_ = [("x", I32), ("y", I32)]


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    title: str


def keyboard_event(key: str, down: bool) -> Input:
    scan, extended = SCAN_CODES[key]
    flags = 0x0008 | (0x0001 if extended else 0) | (0 if down else 0x0002)
    return Input(type=1, ki=KeyboardInput(0, scan, flags, 0, 0))


def mouse_button_event(button: str, down: bool) -> Input:
    flags = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }[button][0 if down else 1]
    return Input(type=0, mi=MouseInput(0, 0, 0, flags, 0, 0))


class Win32Native:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows desktop backend requires Windows")
        self.user32 = C.WinDLL("user32", use_last_error=True)
        self._bind()
        # プロセス全体の設定を変えず、呼出しスレッドを物理座標へ合わせる。
        self._old_dpi = self.user32.SetThreadDpiAwarenessContext(C.c_void_p(-4))
        self.dpi_ready = bool(self._old_dpi)

    def _bind(self):
        api = self.user32
        self._callback_type = C.WINFUNCTYPE(C.c_int, C.c_void_p, C.c_ssize_t)
        definitions = {
            "EnumWindows": ([self._callback_type, C.c_ssize_t], C.c_int),
            "GetWindowTextLengthW": ([C.c_void_p], C.c_int),
            "GetWindowTextW": ([C.c_void_p, C.c_wchar_p, C.c_int], C.c_int),
            "GetWindowThreadProcessId": ([C.c_void_p, C.POINTER(U32)], U32),
            "GetForegroundWindow": ([], C.c_void_p),
            "IsWindow": ([C.c_void_p], C.c_int),
            "IsWindowVisible": ([C.c_void_p], C.c_int),
            "IsIconic": ([C.c_void_p], C.c_int),
            "GetClientRect": ([C.c_void_p, C.POINTER(Rect)], C.c_int),
            "GetWindowRect": ([C.c_void_p, C.POINTER(Rect)], C.c_int),
            "ClientToScreen": ([C.c_void_p, C.POINTER(Point)], C.c_int),
            "SendInput": ([U32, C.POINTER(Input), C.c_int], U32),
            "GetAsyncKeyState": ([C.c_int], C.c_int16),
            "MapVirtualKeyW": ([U32, U32], U32),
            "SetThreadDpiAwarenessContext": ([C.c_void_p], C.c_void_p),
            "GetSystemMetrics": ([C.c_int], C.c_int),
        }
        for name, (argtypes, restype) in definitions.items():
            function = getattr(api, name)
            function.argtypes, function.restype = argtypes, restype

    def list_windows(self) -> list[Window]:
        windows = []

        def collect(hwnd, unused):
            if self.user32.IsWindowVisible(hwnd):
                length = self.user32.GetWindowTextLengthW(hwnd)
                if length:
                    title = C.create_unicode_buffer(length + 1)
                    self.user32.GetWindowTextW(hwnd, title, length + 1)
                    windows.append(Window(hwnd, self.pid(hwnd), title.value))
            return 1

        if not self.user32.EnumWindows(self._callback_type(collect), 0):
            error = C.get_last_error()
            if error or self.foreground():
                raise OSError(error, "Cannot enumerate windows on this desktop")
        return windows

    def foreground(self) -> int:
        return self.user32.GetForegroundWindow() or 0

    def pid(self, hwnd: int) -> int:
        value = U32()
        self.user32.GetWindowThreadProcessId(hwnd, C.byref(value))
        return value.value

    def valid(self, window: Window) -> bool:
        return bool(
            self.user32.IsWindow(window.hwnd)
            and self.user32.IsWindowVisible(window.hwnd)
            and not self.user32.IsIconic(window.hwnd)
            and self.pid(window.hwnd) == window.pid
        )

    def client_bounds(self, hwnd: int) -> tuple[int, int, int, int]:
        rect, point = Rect(), Point()
        if not self.user32.GetClientRect(hwnd, C.byref(rect)):
            raise C.WinError(C.get_last_error())
        if not self.user32.ClientToScreen(hwnd, C.byref(point)):
            raise C.WinError(C.get_last_error())
        return point.x, point.y, point.x + rect.right, point.y + rect.bottom

    def capture(self, hwnd: int, mode: str):
        if not self.dpi_ready:
            raise OSError("DPI context unavailable; use an interactive Windows desktop")
        bounds = self.client_bounds(hwnd)
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise OSError("Empty game client area")
        if mode == "desktop":
            return ImageGrab.grab(bbox=bounds, all_screens=True).convert("RGB")
        if mode != "window":
            raise ValueError("Unknown capture backend")
        rect = Rect()
        if not self.user32.GetWindowRect(hwnd, C.byref(rect)):
            raise C.WinError(C.get_last_error())
        image = ImageGrab.grab(window=hwnd).convert("RGB")
        # PillowのHWND取得はウィンドウ全体。物理座標からクライアントだけを切り出す。
        region = (
            bounds[0] - rect.left,
            bounds[1] - rect.top,
            bounds[2] - rect.left,
            bounds[3] - rect.top,
        )
        if not (
            0 <= region[0] < region[2] <= image.width
            and 0 <= region[1] < region[3] <= image.height
        ):
            raise OSError("Window capture geometry mismatch; try --capture desktop")
        return image.crop(region)

    def _send(self, event: Input):
        if self.user32.SendInput(1, C.byref(event), C.sizeof(Input)) != 1:
            raise OSError(
                C.get_last_error(),
                "SendInput rejected (integrity level/UIPI or input blocking possible)",
            )

    def key(self, key: str, down: bool):
        self._send(keyboard_event(key, down))

    def button(self, button: str, down: bool):
        self._send(mouse_button_event(button, down))

    def move(self, dx: int, dy: int):
        self._send(Input(type=0, mi=MouseInput(dx, dy, 0, 0x0001, 0, 0)))

    def point(self, hwnd: int, x: float, y: float):
        left, top, right, bottom = self.client_bounds(hwnd)
        desktop_x, desktop_y, width, height = [
            self.user32.GetSystemMetrics(i) for i in (76, 77, 78, 79)
        ]
        if width < 2 or height < 2:
            raise OSError("No interactive virtual desktop")
        dx = round((left + x * (right - left - 1) - desktop_x) * 65535 / (width - 1))
        dy = round((top + y * (bottom - top - 1) - desktop_y) * 65535 / (height - 1))
        if not 0 <= dx <= 65535 or not 0 <= dy <= 65535:
            raise OSError("Game target is outside virtual desktop")
        self._send(
            Input(type=0, mi=MouseInput(dx, dy, 0, 0x0001 | 0x8000 | 0x4000, 0, 0))
        )

    def wheel(self, amount: int):
        self._send(Input(type=0, mi=MouseInput(0, 0, amount * 120, 0x0800, 0, 0)))

    def stop_pressed(self) -> bool:
        return bool(self.user32.GetAsyncKeyState(0x77) & 0x8000)  # F8

    def key_pressed(self, key: str) -> bool:
        scan, extended = SCAN_CODES[key]
        virtual = self.user32.MapVirtualKeyW(scan | (0xE000 if extended else 0), 3)
        return bool(virtual and self.user32.GetAsyncKeyState(virtual) & 0x8000)

    def button_pressed(self, button: str) -> bool:
        return bool(
            self.user32.GetAsyncKeyState({"left": 1, "right": 2, "middle": 4}[button])
            & 0x8000
        )

    def close(self):
        if self._old_dpi:
            self.user32.SetThreadDpiAwarenessContext(self._old_dpi)
            self._old_dpi = None
