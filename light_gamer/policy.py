"""APIキー不要の確率的探索。入力は認識した盤面と画像だけ。"""

import math
from functools import lru_cache

from PIL import Image

from .contracts import ACTIONS, Action, Board, Observation
from .rules import slide


@lru_cache(maxsize=32768)
def heuristic(board: Board) -> float:
    logs = [math.log2(value) if value else 0 for value in board]
    empty = board.count(0)
    smoothness = 0.0
    monotonicity = 0.0
    for row in range(4):
        for col in range(4):
            index = row * 4 + col
            for neighbor in (
                index + 1 if col < 3 else -1,
                index + 4 if row < 3 else -1,
            ):
                if neighbor >= 0 and board[index] and board[neighbor]:
                    smoothness -= abs(logs[index] - logs[neighbor])
        for line in (logs[row * 4 : row * 4 + 4], logs[row::4]):
            increasing = sum(max(0, line[i + 1] - line[i]) for i in range(3))
            decreasing = sum(max(0, line[i] - line[i + 1]) for i in range(3))
            monotonicity -= min(increasing, decreasing)
    corner = max(logs[i] for i in (0, 3, 12, 15))
    return empty * 24 + smoothness * 1.5 + monotonicity * 8 + corner * 4


class ExpectimaxPolicy:
    def __init__(self, depth: int = 2):
        if not 1 <= depth <= 3:
            raise ValueError("Search depth must be 1..3")
        self.depth = depth

    def choose(
        self, observation: Observation, screenshot: Image.Image
    ) -> Action | None:
        # キャッシュは1意思決定ごとに破棄し、長時間プレイのメモリを制限する。
        @lru_cache(maxsize=20000)
        def chance(board: Board, remaining: int) -> float:
            if remaining == 0:
                return heuristic(board)
            empty = [i for i, value in enumerate(board) if not value]
            if not empty:
                return player(board, remaining)
            total = 0.0
            for index in empty:
                for value, probability in ((2, 0.9), (4, 0.1)):
                    spawned = board[:index] + (value,) + board[index + 1 :]
                    total += probability * player(spawned, remaining)
            return total / len(empty)

        def player(board: Board, remaining: int) -> float:
            values = [
                chance(moved, remaining - 1) + reward * 0.05
                for action in ACTIONS
                for moved, reward in [slide(board, action)]
                if moved != board
            ]
            return max(values) if values else -10000.0

        candidates = [
            (chance(moved, self.depth - 1) + reward * 0.05, action)
            for action in ACTIONS
            for moved, reward in [slide(observation.board, action)]
            if moved != observation.board
        ]
        return max(candidates, key=lambda item: item[0])[1] if candidates else None
