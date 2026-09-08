"""Restart-safe admission budgets; these are operation caps, not dollar caps."""
import os
import sqlite3
import threading
import time
from pathlib import Path


class UsageLimitExceeded(ValueError):
    pass


DEFAULT_LIMITS = {"sessions": 100, "takes": 60, "ai_jobs": 200, "speech_seconds": 3600,
                  "voice_requests": 100, "renders": 100}


class UsageBudget:
    def __init__(self, path: Path, limits=None, clock=time.time):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS reservations(day INTEGER, operation TEXT, kind TEXT, amount INTEGER, PRIMARY KEY(day,operation,kind))")
        self.db.commit()
        self.limits = dict(limits) if limits is not None else {
            key: int(os.getenv(f"CLAPPY_DAILY_{key.upper()}", str(value))) for key, value in DEFAULT_LIMITS.items()}
        if any(value < 0 for value in self.limits.values()):
            raise ValueError("Daily limits cannot be negative")
        self.clock = clock
        self.lock = threading.Lock()

    def reserve(self, operation, charges):
        """Reserve all charges atomically before work; retries do not refund cost.

        A repeated identical operation is idempotent. A changed reservation is an
        error. SQLite's write transaction also serializes other process handles.
        """
        if not operation or not charges or any(kind not in self.limits or amount <= 0 or not isinstance(amount, int) for kind, amount in charges.items()):
            raise ValueError("Invalid usage reservation")
        day = int(self.clock()//86400)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                existing = dict(self.db.execute("SELECT kind,amount FROM reservations WHERE day=? AND operation=?", (day, operation)))
                if existing:
                    if existing != charges:
                        raise ValueError("Usage operation was already reserved differently")
                    self.db.commit()
                    return
                for kind, amount in charges.items():
                    used = self.db.execute("SELECT coalesce(sum(amount),0) FROM reservations WHERE day=? AND kind=?", (day, kind)).fetchone()[0]
                    if used+amount > self.limits[kind]:
                        raise UsageLimitExceeded(f"The demo's daily {kind.replace('_', ' ')} limit is reached. Existing media and manual cut controls remain available.")
                self.db.executemany("INSERT INTO reservations VALUES(?,?,?,?)", [(day, operation, kind, amount) for kind, amount in charges.items()])
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def remaining(self):
        day = int(self.clock()//86400)
        with self.lock:
            used = dict(self.db.execute("SELECT kind,sum(amount) FROM reservations WHERE day=? GROUP BY kind", (day,)))
        return {kind: max(0, limit-used.get(kind, 0)) for kind, limit in self.limits.items()}
