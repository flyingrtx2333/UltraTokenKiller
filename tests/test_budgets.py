from concurrent.futures import ThreadPoolExecutor

from ultratokenkiller.budgets import budget_status, consume_submission


def test_concurrent_budget_cannot_exceed_ceiling(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(lambda _: consume_submission(tmp_path, 10), range(30)))
    assert sum(accepted) == 10
    assert budget_status(tmp_path) == {"consumed": 10, "ceiling": 10}
    assert consume_submission(tmp_path, 100) is False
