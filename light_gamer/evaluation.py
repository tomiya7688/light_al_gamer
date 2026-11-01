"""入力前後の観測だけで操作の成功・報酬・終了を評価する。"""

from .contracts import Action, Evaluation, Observation
from .rules import legal_actions, slide


class TransitionError(ValueError):
    pass


class TransitionEvaluator:
    def evaluate(
        self, before: Observation, action: Action, after: Observation
    ) -> Evaluation:
        expected, reward = slide(before.board, action)
        if expected == before.board:
            if after.board != before.board:
                raise TransitionError("Illegal move changed the screen")
            reward = 0
        else:
            differences = [
                (old, new) for old, new in zip(expected, after.board) if old != new
            ]
            if len(differences) != 1 or differences[0] not in ((0, 2), (0, 4)):
                raise TransitionError(
                    "Expected slide/merge plus exactly one new 2 or 4"
                )
        return Evaluation(
            changed=before.board != after.board,
            score_delta=reward,
            terminal=not legal_actions(after.board),
            max_tile=max(after.board),
            empty_cells=after.board.count(0),
        )
