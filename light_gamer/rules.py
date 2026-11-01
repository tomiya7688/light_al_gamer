"""既知の2048ルール。探索用の仮想盤面だけを扱う純粋関数。"""

from .contracts import ACTIONS, Action, Board


def slide(board: Board, action: Action) -> tuple[Board, int]:
    if action not in ACTIONS:
        raise ValueError(f"Unknown action: {action}")
    if len(board) != 16:
        raise ValueError("Expected 16 cells")
    result = list(board)
    reward = 0
    for line in range(4):
        indices = (
            [line * 4 + col for col in range(4)]
            if action in ("left", "right")
            else [row * 4 + line for row in range(4)]
        )
        if action in ("right", "down"):
            indices.reverse()
        values = [board[i] for i in indices if board[i]]
        merged = []
        cursor = 0
        while cursor < len(values):
            value = values[cursor]
            if cursor + 1 < len(values) and value == values[cursor + 1]:
                value *= 2
                reward += value
                cursor += 1
            merged.append(value)
            cursor += 1
        merged += [0] * (4 - len(merged))
        for index, value in zip(indices, merged):
            result[index] = value
    return tuple(result), reward


def legal_actions(board: Board) -> tuple[Action, ...]:
    return tuple(action for action in ACTIONS if slide(board, action)[0] != board)
