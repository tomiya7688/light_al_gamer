"""交換可能な認識・判断・操作・評価の境界。"""

from dataclasses import dataclass
from typing import Literal, Protocol

from PIL import Image

Board = tuple[int, ...]
Action = Literal["left", "up", "right", "down"]
ACTIONS: tuple[Action, ...] = ("left", "up", "right", "down")


@dataclass(frozen=True)
class Observation:
    board: Board
    confidence: float


@dataclass(frozen=True)
class Evaluation:
    changed: bool
    score_delta: int
    terminal: bool
    max_tile: int
    empty_cells: int


class ScreenSource(Protocol):
    def capture(self) -> Image.Image: ...


class InputPort(Protocol):
    def press(self, action: Action) -> None: ...


class Perception(Protocol):
    def observe(self, screenshot: Image.Image) -> Observation: ...


class Policy(Protocol):
    # LLM/VLM実装にも元画像を渡せる。ゲームの参照は渡さない。
    def choose(
        self, observation: Observation, screenshot: Image.Image
    ) -> Action | None: ...


class ResultEvaluator(Protocol):
    def evaluate(
        self, before: Observation, action: Action, after: Observation
    ) -> Evaluation: ...
