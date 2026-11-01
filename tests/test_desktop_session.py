import hashlib
import json
from pathlib import Path

from light_gamer.desktop.models import Decision, load_profile
from light_gamer.desktop.policies import MinecraftExplorePolicy
from light_gamer.desktop.session import run_desktop_session
from light_gamer.desktop.windows import StopRequested
from tests.desktop_helpers import Clock, scene

PROFILE = load_profile(
    Path(__file__).resolve().parents[1] / "light_gamer/desktop/profiles/minecraft.json"
)


class ScreenshotFixturePort:
    """合成画像のfixture。実Minecraftの試験結果として扱わない。"""

    def __init__(self):
        self.step = 0
        self.actions = []
        self.closed = False
        self.menu_at = None
        self.failed = False

    def check_ready(self):
        if self.failed:
            raise StopRequested("fixture focus loss")

    def capture(self):
        kind = (
            "lava"
            if self.step in (15, 16)
            else "wood"
            if 35 <= self.step <= 38
            else "terrain"
        )
        frame_step = 54 if 54 <= self.step <= 57 else self.step
        return scene(frame_step, kind=kind, crosshair=self.menu_at != self.step)

    def perform(self, action):
        self.actions.append(action)
        self.step += 1

    def close(self):
        self.closed = True


def test_100_step_screenshot_loop_and_evidence(workspace_path):
    port = ScreenshotFixturePort()
    output = workspace_path / "desktop"
    summary = run_desktop_session(
        port, PROFILE, MinecraftExplorePolicy(), output, steps=100, settle_seconds=0
    )
    assert summary["status"] == "step_limit" and summary["steps"] == 100
    assert summary["goal_achievement"] == "not_verified"
    assert len(port.actions) == 100 and port.closed
    assert PROFILE.actions["mine"] in port.actions
    assert PROFILE.actions["backward"] in port.actions
    assert PROFILE.actions["jump_forward"] in port.actions
    assert PROFILE.actions["turn_right"] in port.actions
    assert len(list((output / "screenshots").glob("*.png"))) == 101
    events = [
        json.loads(line)
        for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 200
    for event in events[1::2]:
        assert (
            hashlib.sha256((output / event["frame"]).read_bytes()).hexdigest()
            == event["frame_sha256"]
        )


def test_menu_stops_before_next_input(workspace_path):
    port = ScreenshotFixturePort()
    port.menu_at = 2
    result = run_desktop_session(
        port,
        PROFILE,
        MinecraftExplorePolicy(),
        workspace_path / "menu",
        settle_seconds=0,
    )
    assert result["status"] == "observation_blocked"
    assert len(port.actions) == 2 and port.closed


def test_cancellation_after_slow_policy_never_sends_input(workspace_path):
    port = ScreenshotFixturePort()

    class Policy:
        def choose(self, *args):
            port.failed = True
            return Decision("forward", "fixture")

    result = run_desktop_session(
        port, PROFILE, Policy(), workspace_path / "cancel", settle_seconds=0
    )
    assert result["status"] == "stopped"
    assert not port.actions and port.closed


def test_deadline_after_slow_policy_never_sends_input(workspace_path):
    port, clock = ScreenshotFixturePort(), Clock()

    class Policy:
        def choose(self, *args):
            clock.now += 5
            return Decision("forward", "fixture")

    result = run_desktop_session(
        port,
        PROFILE,
        Policy(),
        workspace_path / "deadline",
        max_seconds=1,
        clock=clock,
        sleep=clock.sleep,
    )
    assert result["status"] == "time_limit"
    assert not port.actions and port.closed


def test_unknown_action_stops_with_error_artifact(workspace_path):
    port = ScreenshotFixturePort()

    class Policy:
        def choose(self, *args):
            return Decision("shell_command", "fixture")

    result = run_desktop_session(port, PROFILE, Policy(), workspace_path / "unknown")
    assert result["status"] == "error"
    assert not port.actions and port.closed


def test_cleanup_failure_is_not_reported_as_success(workspace_path):
    port = ScreenshotFixturePort()

    def fail():
        raise OSError("release failed")

    port.close = fail
    result = run_desktop_session(
        port,
        PROFILE,
        MinecraftExplorePolicy(),
        workspace_path / "cleanup",
        steps=1,
        settle_seconds=0,
    )
    assert result["status"] == "error"
    assert result["cleanup_error"] == "release failed"


def test_custom_policy_can_use_inventory_without_crosshair(workspace_path):
    port = ScreenshotFixturePort()
    port.menu_at = 0

    class InventoryPolicy:
        requires_crosshair = False

        def choose(self, *args):
            return Decision("point_click", "in-game inventory fixture", (0.25, 0.75))

    result = run_desktop_session(
        port,
        PROFILE,
        InventoryPolicy(),
        workspace_path / "inventory",
        steps=1,
        settle_seconds=0,
    )
    assert result["status"] == "step_limit"
    assert port.actions[0].pointer == (0.25, 0.75)
    assert port.closed
