import hashlib
import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from PIL import Image

from light_gamer.contracts import Observation
from light_gamer.evaluation import TransitionError, TransitionEvaluator
from light_gamer.perception import PalettePerception
from light_gamer.policy import ExpectimaxPolicy
from light_gamer.rules import legal_actions
from light_gamer.runner import make_replay, run_session
from light_gamer.transport import GameProcess


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_policy_uses_legal_moves(seed):
    with GameProcess(seed) as port:
        perception = PalettePerception()
        policy = ExpectimaxPolicy(1)
        for _ in range(5):
            image = port.capture()
            before = perception.observe(image)
            action = policy.choose(before, image)
            assert action in legal_actions(before.board)
            port.press(action)
            after = perception.observe(port.capture())
            assert TransitionEvaluator().evaluate(before, action, after).changed


def test_terminal_policy_returns_none():
    board = (2, 4, 2, 4, 4, 2, 4, 2, 2, 4, 2, 4, 4, 2, 4, 2)
    assert (
        ExpectimaxPolicy().choose(Observation(board, 1), Image.new("RGB", (1, 1)))
        is None
    )


def test_blackbox_100_turns_and_artifacts(workspace_path):
    output = workspace_path / "session"
    process = GameProcess(7)
    with process as port:
        result = run_session(
            port,
            port,
            PalettePerception(),
            ExpectimaxPolicy(1),
            TransitionEvaluator(),
            output,
            100,
        )
    assert process.process.poll() is not None
    assert result["turns"] == 100
    assert result["status"] == "turn_limit"
    rows = [
        json.loads(line) for line in (output / "turns.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 100
    assert len(list((output / "screenshots").glob("*.png"))) == 101
    for row in rows:
        assert row["before"] != row["after"]
        assert (
            hashlib.sha256((output / row["frame"]).read_bytes()).hexdigest()
            == row["frame_sha256"]
        )
    assert sum(row["score_delta"] for row in rows) == result["score_from_merges"]
    make_replay(output)
    with Image.open(output / "replay.gif") as replay:
        assert replay.n_frames == 101


def test_only_png_and_key_are_exposed():
    with GameProcess(7) as port:
        for path in ("/state", "/board", "/score"):
            with pytest.raises(HTTPError) as exc:
                port._http.open(port.base + path)
            assert exc.value.code == 404
        request = Request(port.base + "/key", data=b"invalid", method="POST")
        with pytest.raises(HTTPError) as exc:
            port._http.open(request)
        assert exc.value.code == 400
        with port._http.open(port.base + "/") as response:
            html = response.read().decode()
            assert '<img id="screen"' in html
            assert "_board" not in html


def test_failed_observation_stops_and_saves_error(workspace_path):
    from light_gamer.game import Game2048

    class StuckPort:
        def capture(self):
            return Game2048(7).screenshot()

        def press(self, action):
            pass

    port = StuckPort()
    output = workspace_path / "failed"
    with pytest.raises(TransitionError):
        run_session(
            port,
            port,
            PalettePerception(),
            ExpectimaxPolicy(1),
            TransitionEvaluator(),
            output,
            3,
        )
    summary = json.loads((output / "summary.json").read_text())
    assert summary["status"] == "error"
    assert summary["turns"] == 0
    assert summary["transition_errors"] == 1


def test_existing_output_is_not_overwritten(workspace_path):
    with pytest.raises(FileExistsError):
        run_session(None, None, None, None, None, workspace_path, 1)
