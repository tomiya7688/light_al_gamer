import pytest

from light_gamer.contracts import Observation
from light_gamer.evaluation import TransitionError, TransitionEvaluator


def obs(values):
    return Observation(tuple(values + [0] * (16 - len(values))), 1)


def test_merge_reward_and_spawn():
    result = TransitionEvaluator().evaluate(obs([2, 2]), "left", obs([4, 0, 2]))
    assert result.changed
    assert result.score_delta == 4
    assert result.max_tile == 4


def test_noop():
    before = obs([2])
    assert not TransitionEvaluator().evaluate(before, "left", before).changed


@pytest.mark.parametrize("after", [obs([2, 2]), obs([4]), obs([4, 8]), obs([4, 2, 2])])
def test_reject_stale_impossible_or_double_input(after):
    with pytest.raises(TransitionError):
        TransitionEvaluator().evaluate(obs([2, 2]), "left", after)
