"""Persistent atomic ceilings for explicitly authorized live verification."""
import sqlite3
from pathlib import Path


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
