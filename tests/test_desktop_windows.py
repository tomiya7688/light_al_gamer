import ctypes

import pytest

from light_gamer.desktop.models import ControlAction
from light_gamer.desktop.native import Input, keyboard_event, mouse_button_event
from light_gamer.desktop.windows import (
    StopRequested,
    Window,
    WindowsGamePort,
    select_window,
)
from tests.desktop_helpers import Clock, FakeNative


def port_for(native, clock=None, monitor=False):
    clock = clock or Clock()
    return WindowsGamePort(
        native,
        Window(10, 20, "Minecraft"),
        clock=clock,
        sleep=clock.sleep,
        monitor=monitor,
    )


def test_input_abi_and_scan_codes():
    assert ctypes.sizeof(Input) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
    event = keyboard_event("w", True)
    assert event.type == 1 and event.ki.wScan == 0x11 and event.ki.dwFlags == 8
    assert keyboard_event("right", False).ki.dwFlags == 0x000B
    assert mouse_button_event("left", False).mi.dwFlags == 4


def test_unique_window_and_launcher_exclusion():
    windows = [Window(1, 1, "Minecraft Launcher"), Window(2, 3, "Minecraft 1.21")]
    assert select_window(windows, "Minecraft").hwnd == 2
    assert select_window(windows, "", hwnd=1).hwnd == 1
    with pytest.raises(ValueError):
        select_window(windows, "")
    with pytest.raises(ValueError):
        select_window(windows + [Window(3, 4, "Minecraft World")], "Minecraft")


def test_balanced_keys_buttons_mouse_and_duration():
    native, clock = FakeNative(), Clock()
    port = port_for(native, clock)
    port.perform(
        ControlAction(
            keys=("w", "space"), buttons=("left",), mouse_delta=(100, -10), seconds=0.4
        )
    )
    assert native.events == [
        ("move", 100, -10),
        ("key", "w", True),
        ("key", "space", True),
        ("button", "left", True),
        ("button", "left", False),
        ("key", "space", False),
        ("key", "w", False),
    ]
    assert clock.now == pytest.approx(0.4)
    assert not port.held
    port.close()
    assert native.closed


def test_absolute_point_and_wheel():
    native = FakeNative()
    port = port_for(native)
    port.perform(ControlAction(pointer=(0.25, 0.75), aim=True, wheel=-1))
    assert native.events[:2] == [("point", 10, 0.25, 0.75), ("wheel", -1)]
    with pytest.raises(ValueError):
        port.perform(ControlAction(aim=True))


@pytest.mark.parametrize("failure", ["focus", "stop", "exists"])
def test_stops_during_hold_and_always_releases(failure):
    native, clock = FakeNative(), Clock()
    port = port_for(native, clock)

    def interrupt():
        if failure == "focus":
            native.focus = 99
        elif failure == "stop":
            native.stop = True
        else:
            native.exists = False

    clock.on_sleep = interrupt
    with pytest.raises(StopRequested):
        port.perform(ControlAction(keys=("w",), buttons=("left",)))
    assert ("key", "w", False) in native.events
    assert ("button", "left", False) in native.events
    assert not port.held


def test_partial_key_failure_releases_previous_and_attempted_key():
    native = FakeNative()
    native.raise_on = ("space", True)
    port = port_for(native)
    with pytest.raises(OSError):
        port.perform(ControlAction(keys=("w", "space")))
    assert native.events[-2:] == [("key", "space", False), ("key", "w", False)]
    assert not port.held


def test_release_failure_is_visible_and_retried_on_close():
    native = FakeNative()
    native.raise_on = ("w", False)
    port = port_for(native)
    with pytest.raises(OSError, match="release failed"):
        port.perform(ControlAction(keys=("w",)))
    assert port.held == [("key", "w")]
    native.raise_on = None
    port.close()
    assert not port.held


def test_foreground_checked_before_capture_and_input():
    native = FakeNative()
    native.focus = 99
    port = port_for(native)
    with pytest.raises(StopRequested):
        port.capture()
    with pytest.raises(StopRequested):
        port.perform(ControlAction(keys=("w",)))
    assert not native.events


@pytest.mark.parametrize("kind", ["key", "button"])
def test_does_not_take_over_physically_held_controls(kind):
    native = FakeNative()
    port = port_for(native)
    if kind == "key":
        native.user_keys.add("w")
        action = ControlAction(keys=("w",))
    else:
        native.user_buttons.add("left")
        action = ControlAction(buttons=("left",))
    with pytest.raises(StopRequested):
        port.perform(action)
    assert not native.events


def test_f8_is_latched_during_reasoning_without_input():
    native = FakeNative()
    port = port_for(native, monitor=True)
    native.stop = True
    assert port.cancelled.wait(1)
    native.stop = False
    with pytest.raises(StopRequested):
        port.check_ready()
    port.close()
    assert not port.monitor.is_alive()
    assert not native.events


def test_capture_focus_loss_during_capture():
    native = FakeNative()
    original = native.capture

    def capture(*args):
        native.focus = 99
        return original(*args)

    native.capture = capture
    with pytest.raises(StopRequested):
        port_for(native).capture()


def test_stop_monitor_failure_stops_input():
    native = FakeNative()
    native.stop_pressed = lambda: (_ for _ in ()).throw(OSError("monitor unavailable"))
    port = port_for(native, monitor=True)
    assert port.cancelled.wait(1)
    with pytest.raises(StopRequested):
        port.check_ready()
    port.close()


def test_input_rejected_is_reported(monkeypatch):
    from types import SimpleNamespace

    from light_gamer.desktop import native as module

    api = module.Win32Native.__new__(module.Win32Native)
    api.user32 = SimpleNamespace(SendInput=lambda *args: 0)
    monkeypatch.setattr(module.C, "get_last_error", lambda: 5, raising=False)
    with pytest.raises(OSError, match="SendInput rejected"):
        api.key("w", True)
