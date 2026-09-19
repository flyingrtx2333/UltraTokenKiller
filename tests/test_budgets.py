from concurrent.futures import ThreadPoolExecutor

from ultratokenkiller.budgets import budget_status, consume_submission
from ultratokenkiller.budgets import authorize_ceiling
import pytest
from ultratokenkiller.budgets import reconcile_submissions


def test_reconciliation_is_atomic_idempotent_and_does_not_grant(tmp_path):
    authorize_ceiling(tmp_path, 3)
    assert consume_submission(tmp_path, 3)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: reconcile_submissions(tmp_path, "observed-run", 4), range(16)))
    assert budget_status(tmp_path) == {"consumed": 5, "ceiling": 3}
    assert not consume_submission(tmp_path, 100)
    with pytest.raises(ValueError):
        reconcile_submissions(tmp_path, "observed-run", 2)
    assert budget_status(tmp_path)["consumed"] == 5


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
