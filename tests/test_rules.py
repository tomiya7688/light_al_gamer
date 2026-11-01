import random

import pytest

from light_gamer.contracts import ACTIONS
from light_gamer.rules import legal_actions, slide


@pytest.mark.parametrize(
    ("row", "expected", "score"),
    [
        ([2, 2, 2, 2], [4, 4, 0, 0], 8),
        ([2, 2, 4, 0], [4, 4, 0, 0], 4),
        ([4, 0, 4, 4], [8, 4, 0, 0], 8),
        ([0, 0, 0, 0], [0, 0, 0, 0], 0),
    ],
)
def test_merge_once(row, expected, score):
    board, reward = slide(tuple(row + [0] * 12), "left")
    assert list(board[:4]) == expected
    assert reward == score


@pytest.mark.parametrize(
    "action,target", [("left", 4), ("right", 7), ("up", 1), ("down", 13)]
)
def test_directions(action, target):
    board = [0] * 16
    board[5] = 2
    moved, reward = slide(tuple(board), action)
    assert moved[target] == 2
    assert sum(moved) == 2
    assert reward == 0


def test_mass_conservation_and_power_of_two():
    rng = random.Random(42)
    for _ in range(200):
        board = tuple(rng.choice((0, 2, 4, 8, 16)) for _ in range(16))
        for action in ACTIONS:
            moved, reward = slide(board, action)
            assert sum(moved) == sum(board)
            assert all(value == 0 or value & (value - 1) == 0 for value in moved)
            assert reward >= 0


def test_terminal():
    board = (2, 4, 2, 4, 4, 2, 4, 2, 2, 4, 2, 4, 4, 2, 4, 2)
    assert legal_actions(board) == ()


def test_invalid_action():
    with pytest.raises(ValueError):
        slide((0,) * 16, "space")
