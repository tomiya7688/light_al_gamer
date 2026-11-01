"""ターゲット検証・緊急停止・押下解除を伴うWindows入出力。"""

import threading
import time

from .models import ControlAction
from .native import Win32Native, Window


class StopRequested(RuntimeError):
    pass


def select_window(windows: list[Window], title: str, hwnd: int | None = None) -> Window:
    if hwnd is None and not title.strip():
        raise ValueError("A non-empty window title or explicit HWND is required")
    matches = [
        window
        for window in windows
        if (
            window.hwnd == hwnd
            if hwnd is not None
            else title.casefold() in window.title.casefold()
            and "launcher" not in window.title.casefold()
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one matching game window, found {len(matches)}; use --list-windows and --hwnd"
        )
    return matches[0]


class WindowsGamePort:
    def __init__(
        self,
        native: Win32Native,
        window: Window,
        capture_mode: str = "desktop",
        clock=time.monotonic,
        sleep=time.sleep,
        monitor: bool = True,
    ):
        if capture_mode not in ("desktop", "window"):
            raise ValueError("Unknown capture mode")
        self.native, self.window, self.capture_mode = native, window, capture_mode
        self.clock, self.sleep = clock, sleep
        self.held = []
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.monitor = None
        if monitor:
            self.monitor = threading.Thread(target=self._watch_stop, daemon=True)
            self.monitor.start()

    def _watch_stop(self):
        try:
            while not self.finished.wait(0.02):
                if self.native.stop_pressed():
                    self.cancelled.set()
                    return
        except Exception:
            self.cancelled.set()

    def check_ready(self):
        if self.cancelled.is_set() or self.native.stop_pressed():
            raise StopRequested("F8 emergency stop requested")
        if not self.native.valid(self.window):
            raise StopRequested("Target closed, minimized, hidden or replaced")
        if self.native.foreground() != self.window.hwnd:
            raise StopRequested("Game lost foreground; no further input")

    def capture(self):
        self.check_ready()
        image = self.native.capture(self.window.hwnd, self.capture_mode)
        self.check_ready()
        return image

    def release_all(self):
        errors = []
        for kind, value in list(reversed(self.held)):
            try:
                getattr(self.native, kind)(value, False)
                self.held.remove((kind, value))
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise OSError("Input release failed: " + "; ".join(errors))

    def perform(self, action: ControlAction):
        # モデル出力を直接渡さず、検証済みプロファイルの値だけを受け取る。
        if not isinstance(action, ControlAction):
            raise TypeError("Expected validated ControlAction")
        if action.aim and action.pointer is None:
            raise ValueError("Pointed action needs a normalized target")
        self.check_ready()
        if any(self.native.key_pressed(key) for key in action.keys):
            raise StopRequested("Requested game key is already held by user")
        if any(self.native.button_pressed(button) for button in action.buttons):
            raise StopRequested("Requested mouse button is already held by user")
        original = None
        try:
            if action.pointer is not None:
                self.check_ready()
                self.native.point(self.window.hwnd, *action.pointer)
            if action.mouse_delta != (0, 0):
                self.check_ready()
                self.native.move(*action.mouse_delta)
            if action.wheel:
                self.check_ready()
                self.native.wheel(action.wheel)
            for kind, values in (("key", action.keys), ("button", action.buttons)):
                for value in values:
                    self.check_ready()
                    # SendInputが部分的に失敗した場合にも解除を試みる。
                    self.held.append((kind, value))
                    getattr(self.native, kind)(value, True)
            deadline = self.clock() + action.seconds
            while self.clock() < deadline:
                self.check_ready()
                self.sleep(min(0.02, max(0, deadline - self.clock())))
        except BaseException as exc:
            original = exc
            raise
        finally:
            try:
                self.release_all()
            except OSError as exc:
                if original is None:
                    raise
                original.add_note(str(exc))

    def close(self):
        self.finished.set()
        if self.monitor:
            self.monitor.join(timeout=1)
        try:
            self.release_all()
        finally:
            self.native.close()
