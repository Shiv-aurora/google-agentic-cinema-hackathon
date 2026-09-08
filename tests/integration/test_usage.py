from concurrent.futures import ThreadPoolExecutor

import pytest

from services.api.usage import UsageBudget, UsageLimitExceeded
from services.api.access import authorize_invitation, origin_allowed, validate_access_settings
from fastapi import HTTPException


def test_budget_survives_restart_deduplicates_and_reserves_atomically(tmp_path):
    path = tmp_path/"usage.sqlite"
    limits = {"ai_jobs": 2, "renders": 1}
    budget = UsageBudget(path, limits, clock=lambda: 86401)
    budget.reserve("first", {"ai_jobs": 1, "renders": 1})
    restarted = UsageBudget(path, limits, clock=lambda: 86401)
    restarted.reserve("first", {"ai_jobs": 1, "renders": 1})
    assert restarted.remaining() == {"ai_jobs": 1, "renders": 0}
    with pytest.raises(UsageLimitExceeded):
        restarted.reserve("second", {"ai_jobs": 1, "renders": 1})
    assert restarted.remaining()["ai_jobs"] == 1
    with pytest.raises(ValueError):
        restarted.reserve("first", {"ai_jobs": 2})
    tomorrow = UsageBudget(path, limits, clock=lambda: 172801)
    assert tomorrow.remaining() == limits


def test_concurrent_handles_cannot_overspend(tmp_path):
    a = UsageBudget(tmp_path/"usage.sqlite", {"ai_jobs": 1})
    b = UsageBudget(tmp_path/"usage.sqlite", {"ai_jobs": 1})
    def spend(args):
        budget, operation = args
        try:
            budget.reserve(operation, {"ai_jobs": 1})
            return True
        except UsageLimitExceeded:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(spend, [(a, "a"), (b, "b")])) == 1


def test_invitation_and_origin_fail_closed(monkeypatch):
    monkeypatch.setenv("CLAPPY_DEMO_ACCESS_KEY", "x"*32)
    monkeypatch.setenv("CLAPPY_PUBLIC_ORIGIN", "https://clappy.example")
    validate_access_settings()
    authorize_invitation("x"*32)
    with pytest.raises(HTTPException):
        authorize_invitation("incorrect")
    assert origin_allowed("https://clappy.example")
    assert not origin_allowed("https://clappy.example.untrusted.test")
    assert not origin_allowed("null")
    monkeypatch.setenv("CLAPPY_DEMO_ACCESS_KEY", "short")
    with pytest.raises(ValueError):
        validate_access_settings()
