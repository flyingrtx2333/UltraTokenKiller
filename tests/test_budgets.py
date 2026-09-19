from concurrent.futures import ThreadPoolExecutor

from ultratokenkiller.budgets import budget_status, consume_submission
from ultratokenkiller.budgets import authorize_ceiling
import pytest


def test_explicit_grant_preserves_consumption_and_is_idempotent(tmp_path):
    for _ in range(19):
        assert consume_submission(tmp_path, 20)
    assert authorize_ceiling(tmp_path, 40) == {"consumed": 19, "ceiling": 40}
    assert authorize_ceiling(tmp_path, 40) == {"consumed": 19, "ceiling": 40}
    with pytest.raises(ValueError):
        authorize_ceiling(tmp_path, 20)
    assert sum(consume_submission(tmp_path, 40) for _ in range(25)) == 21
    assert not consume_submission(tmp_path, 100)


def test_concurrent_budget_cannot_exceed_ceiling(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(lambda _: consume_submission(tmp_path, 10), range(30)))
    assert sum(accepted) == 10
    assert budget_status(tmp_path) == {"consumed": 10, "ceiling": 10}
    assert consume_submission(tmp_path, 100) is False
