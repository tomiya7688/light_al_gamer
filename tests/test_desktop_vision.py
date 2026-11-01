import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from light_gamer.desktop.models import ControlAction, VisualFeedback, load_profile
from light_gamer.desktop.policies import MinecraftExplorePolicy
from light_gamer.desktop.vision import VisualEvaluator, VisualPerception, has_crosshair
from tests.desktop_helpers import scene

PROFILE_DIR = Path(__file__).resolve().parents[1] / "light_gamer/desktop/profiles"


@pytest.mark.parametrize("name", ["minecraft", "generic"])
def test_builtin_profiles(name):
    profile = load_profile(PROFILE_DIR / (name + ".json"))
    assert profile.actions
    assert all(isinstance(action, ControlAction) for action in profile.actions.values())


@pytest.mark.parametrize(
    "values",
    [
        {"seconds": 0},
        {"seconds": 6},
        {"seconds": float("nan")},
        {"seconds": True},
        {"keys": ("win",)},
        {"keys": ("w", "w")},
        {"keys": (["w"],)},
        {"mouse_delta": (1000, 0)},
        {"mouse_delta": (True, 0)},
        {"wheel": 4},
        {"pointer": (1.1, 0)},
        {"pointer": (float("nan"), 0)},
        {"pointer": (0, 0), "mouse_delta": (1, 0)},
        {"buttons": ("left", "left")},
    ],
)
def test_invalid_input_definitions(values):
    with pytest.raises(ValueError):
        ControlAction(**values)


def test_unknown_profile_property_rejected(workspace_path):
    data = {
        "name": "test",
        "perception": "generic",
        "actions": {"run": {"shell": "anything"}},
    }
    path = workspace_path / "profile.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_profile(path)


def test_recognizes_crosshair_and_blocks_menu():
    assert has_crosshair(scene())
    assert not has_crosshair(scene(crosshair=False))
    assert not VisualPerception().observe(Image.new("RGB", (640, 360))).usable


@pytest.mark.parametrize(
    "kind,field,minimum",
    [
        ("lava", "lava_fraction", 0.5),
        ("water", "water_fraction", 0.5),
        ("wood", "brown_fraction", 0.45),
    ],
)
def test_pixel_features(kind, field, minimum):
    observation = VisualPerception().observe(scene(kind=kind))
    assert observation.usable and observation.crosshair
    assert getattr(observation, field) > minimum


def test_feedback_detects_static_motion_and_resize():
    evaluator = VisualEvaluator()
    assert not evaluator.evaluate(scene(), scene()).changed
    assert evaluator.evaluate(scene(), scene(1)).changed
    with pytest.raises(ValueError, match="resized"):
        evaluator.evaluate(scene(), scene().resize((320, 180)))


def test_explore_responds_to_stuck_and_hazard():
    image = scene()
    observation = VisualPerception().observe(image)
    policy = MinecraftExplorePolicy()
    assert policy.choose(observation, image, None).action == "forward"
    assert (
        policy.choose(observation, image, VisualFeedback(0, False)).action
        == "jump_forward"
    )
    assert (
        policy.choose(observation, image, VisualFeedback(0, False)).action
        == "turn_right"
    )
    lava = replace(observation, lava_fraction=0.6)
    assert policy.choose(lava, image, None).action == "backward"
    assert policy.choose(lava, image, None).action == "turn_right"
    assert (
        policy.choose(replace(observation, crosshair=False), image, None).action is None
    )


def test_mining_is_bounded_not_infinite():
    image = scene(kind="wood")
    observation = VisualPerception().observe(image)
    policy = MinecraftExplorePolicy()
    actions = [policy.choose(observation, image, None).action for _ in range(5)]
    assert actions == ["mine"] * 4 + ["turn_left"]
