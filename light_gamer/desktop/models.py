"""ゲームに依存しない行動・観測・判断・評価の契約。"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

# スキャンコードと拡張キーの有無。WindowsキーやOS操作用の組合せは提供しない。
SCAN_CODES = {
    "w": (0x11, False),
    "a": (0x1E, False),
    "s": (0x1F, False),
    "d": (0x20, False),
    "e": (0x12, False),
    "q": (0x10, False),
    "space": (0x39, False),
    "shift": (0x2A, False),
    "ctrl": (0x1D, False),
    "escape": (0x01, False),
    "enter": (0x1C, False),
    "tab": (0x0F, False),
    "left": (0x4B, True),
    "right": (0x4D, True),
    "up": (0x48, True),
    "down": (0x50, True),
    **{str(i): (i + 1, False) for i in range(1, 10)},
    "0": (0x0B, False),
    "backspace": (0x0E, False),
    **{letter: (code, False) for letter, code in zip("rtyuiop", range(0x13, 0x1A))},
    **{letter: (code, False) for letter, code in zip("fghjkl", range(0x21, 0x27))},
    **{letter: (code, False) for letter, code in zip("zxcvbnm", range(0x2C, 0x33))},
    **{f"f{i}": (0x3A + i, False) for i in range(1, 11) if i != 8},
    "f11": (0x57, False),
    "f12": (0x58, False),
}


@dataclass(frozen=True)
class ControlAction:
    keys: tuple[str, ...] = ()
    buttons: tuple[str, ...] = ()
    mouse_delta: tuple[int, int] = (0, 0)
    seconds: float = 0.25
    wheel: int = 0
    aim: bool = False
    pointer: tuple[float, float] | None = None

    def __post_init__(self):
        if (
            not isinstance(self.seconds, (int, float))
            or isinstance(self.seconds, bool)
            or not math.isfinite(self.seconds)
            or not 0.02 <= self.seconds <= 5
        ):
            raise ValueError("Action seconds must be finite and within 0.02..5")
        if (
            not isinstance(self.keys, tuple)
            or any(not isinstance(key, str) for key in self.keys)
            or len(set(self.keys)) != len(self.keys)
            or any(key not in SCAN_CODES for key in self.keys)
        ):
            raise ValueError("Unknown or repeated keyboard key")
        if (
            not isinstance(self.buttons, tuple)
            or any(not isinstance(button, str) for button in self.buttons)
            or len(set(self.buttons)) != len(self.buttons)
            or any(button not in ("left", "right", "middle") for button in self.buttons)
        ):
            raise ValueError("Unknown or repeated mouse button")
        if (
            not isinstance(self.mouse_delta, tuple)
            or len(self.mouse_delta) != 2
            or any(
                type(value) is not int or abs(value) > 500 for value in self.mouse_delta
            )
        ):
            raise ValueError(
                "Relative mouse delta must contain two integers within -500..500"
            )
        if (
            type(self.wheel) is not int
            or abs(self.wheel) > 3
            or type(self.aim) is not bool
        ):
            raise ValueError("Wheel must be -3..3; aim must be boolean")
        if self.pointer is not None:
            validate_pointer(self.pointer)
            if self.mouse_delta != (0, 0):
                raise ValueError(
                    "Cannot combine absolute pointer and relative movement"
                )


def validate_pointer(pointer):
    if (
        not isinstance(pointer, tuple)
        or len(pointer) != 2
        or any(
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in pointer
        )
    ):
        raise ValueError(
            "Pointer must contain two finite normalized coordinates in 0..1"
        )


@dataclass(frozen=True)
class GameProfile:
    name: str
    perception: str
    actions: dict[str, ControlAction]


def load_profile(path: Path) -> GameProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"name", "perception", "actions"}:
        raise ValueError("Profile requires exactly name, perception, actions")
    if not isinstance(data["name"], str) or not 1 <= len(data["name"]) <= 80:
        raise ValueError("Invalid profile name")
    if data["perception"] not in ("minecraft", "generic"):
        raise ValueError("Perception must be minecraft or generic")
    raw = data["actions"]
    if not isinstance(raw, dict) or not 1 <= len(raw) <= 64:
        raise ValueError("Profile requires 1..64 actions")
    actions = {}
    for name, spec in raw.items():
        if not isinstance(name, str) or not name.isidentifier() or len(name) > 40:
            raise ValueError("Action names must be short identifiers")
        if not isinstance(spec, dict) or set(spec) - {
            "keys",
            "buttons",
            "mouse_delta",
            "seconds",
            "wheel",
            "aim",
            "pointer",
        }:
            raise ValueError(f"Unknown action properties: {name}")
        normalized = dict(spec)
        for key in ("keys", "buttons", "mouse_delta", "pointer"):
            if key in normalized:
                if not isinstance(normalized[key], list):
                    raise ValueError(f"{key} must be a JSON array")
                normalized[key] = tuple(normalized[key])
        actions[name] = ControlAction(**normalized)
    return GameProfile(data["name"], data["perception"], actions)


@dataclass(frozen=True)
class VisualObservation:
    usable: bool
    crosshair: bool
    lava_fraction: float
    water_fraction: float
    brown_fraction: float
    brightness: float


@dataclass(frozen=True)
class VisualFeedback:
    motion: float
    changed: bool


@dataclass(frozen=True)
class Decision:
    action: str | None
    reason: str
    pointer: tuple[float, float] | None = None


class DesktopPort(Protocol):
    def check_ready(self) -> None: ...
    def capture(self) -> Image.Image: ...
    def perform(self, action: ControlAction) -> None: ...
    def close(self) -> None: ...


class VisualPolicy(Protocol):
    def choose(
        self,
        observation: VisualObservation,
        screenshot: Image.Image,
        previous: VisualFeedback | None,
    ) -> Decision: ...


class DesktopPerception(Protocol):
    def observe(self, screenshot: Image.Image) -> VisualObservation: ...


class DesktopEvaluator(Protocol):
    def evaluate(self, before: Image.Image, after: Image.Image) -> VisualFeedback: ...
