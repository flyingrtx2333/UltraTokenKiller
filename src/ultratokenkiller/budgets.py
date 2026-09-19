"""Persistent atomic ceilings for explicitly authorized live verification."""
import sqlite3
from pathlib import Path


def authorize_ceiling(home: Path, ceiling: int):
    """Explicit operator grant; ordinary submission paths cannot increase a budget."""
    if ceiling < 1:
        raise ValueError("Positive authorized ceiling required")
    home.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(home / "verification-budget.sqlite3", timeout=10) as db:
        db.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), consumed INTEGER NOT NULL, ceiling INTEGER NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO budget VALUES (1,0,?)", (ceiling,))
        consumed, previous = db.execute("SELECT consumed, ceiling FROM budget WHERE id=1").fetchone()
        if ceiling < previous or ceiling < consumed:
            raise ValueError("An additional grant cannot lower the existing ceiling")
        db.execute("UPDATE budget SET ceiling=? WHERE id=1", (ceiling,))
    return budget_status(home)


def consume_submission(home: Path, limit: int) -> bool:
    if limit <= 0:
        return False
    home.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(home / "verification-budget.sqlite3", timeout=10) as db:
        db.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), consumed INTEGER NOT NULL, ceiling INTEGER NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO budget VALUES (1,0,?)", (limit,))
        consumed, ceiling = db.execute("SELECT consumed, ceiling FROM budget WHERE id=1").fetchone()
        ceiling = min(ceiling, limit)
        if consumed >= ceiling:
            return False
        db.execute("UPDATE budget SET consumed=consumed+1, ceiling=? WHERE id=1", (ceiling,))
        return True


def budget_status(home: Path):
    path = home / "verification-budget.sqlite3"
    if not path.exists():
        return {"consumed": 0, "ceiling": None}
    with sqlite3.connect(path) as db:
        consumed, ceiling = db.execute("SELECT consumed, ceiling FROM budget WHERE id=1").fetchone()
        return {"consumed": consumed, "ceiling": ceiling}


def reconcile_submissions(home: Path, evidence_id: str, count: int):
    """Account for externally observed requests exactly once, without a grant.

    Consumption may exceed the ceiling: historical calls must not disappear
    merely because a faulty route bypassed enforcement. Future calls then stop.
    Store only an opaque evidence identifier and count, never request content.
    """
    import re
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", evidence_id) or type(count) is not int or count < 1:
        raise ValueError("A body-free evidence identifier and positive count are required")
    with sqlite3.connect(home / "verification-budget.sqlite3", timeout=10) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT consumed FROM budget WHERE id=1").fetchone() is None:
            raise ValueError("An existing authorized budget is required")
        db.execute("CREATE TABLE IF NOT EXISTS reconciliation (evidence_id TEXT PRIMARY KEY, count INTEGER NOT NULL)")
        previous = db.execute("SELECT count FROM reconciliation WHERE evidence_id=?", (evidence_id,)).fetchone()
        if previous:
            if previous[0] != count:
                raise ValueError("Evidence count conflicts with existing reconciliation")
        else:
            db.execute("INSERT INTO reconciliation VALUES (?,?)", (evidence_id, count))
            db.execute("UPDATE budget SET consumed=consumed+? WHERE id=1", (count,))
    return budget_status(home)
