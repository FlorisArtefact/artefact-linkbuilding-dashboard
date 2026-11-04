"""Ahrefs safety net. requests.get is always replaced by a fake: these tests never reach the real API."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import ahrefs_client, ahrefs_guard as guard  # noqa: E402


class FakeResp:
    def __init__(self, code=200, body=None):
        self.status_code, self._body = code, body if body is not None else {"keywords": [{"best_position": 3, "sum_traffic": 10}]}

    def json(self):
        return self._body


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("AHREFS_ENABLED", "1")
    monkeypatch.setenv("AHREFS_DAILY_CAP", "5")
    calls = []
    codes = {"next": 200}

    def fake_get(url, **kw):
        calls.append(url)
        return FakeResp(codes["next"])

    monkeypatch.setattr(ahrefs_client.requests, "get", fake_get)
    return calls, codes


def test_on_hold_makes_no_request(api, monkeypatch):
    calls, _ = api
    monkeypatch.setenv("AHREFS_ENABLED", "0")
    with pytest.raises(guard.AhrefsBlocked):
        ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 1})
    assert calls == []


def test_result_is_stored_and_reused(api):
    calls, _ = api
    ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 1})
    ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 1})
    assert len(calls) == 1
    assert guard.status()["calls"] == 1


def test_stored_results_work_while_on_hold(api, monkeypatch):
    calls, _ = api
    ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 1})
    monkeypatch.setenv("AHREFS_ENABLED", "0")
    assert ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 1})["keywords"]
    assert len(calls) == 1


def test_rate_limit_trips_breaker_without_retry(api):
    calls, codes = api
    codes["next"] = 429
    with pytest.raises(guard.AhrefsBlocked):
        ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 1})
    assert len(calls) == 1
    with pytest.raises(guard.AhrefsBlocked):
        ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 2})
    assert len(calls) == 1 and guard.status()["blocked"]


def test_failures_are_not_stored(api):
    calls, codes = api
    codes["next"] = 500
    with pytest.raises(RuntimeError):
        ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 1})
    assert len(calls) == 2                      # one retry at most
    assert not guard.cache_has("site-explorer/x", {"a": 1})


def test_daily_cap(api):
    calls, _ = api
    for i in range(5):
        ahrefs_client.guarded_get("k", "site-explorer/x", {"a": i})
    with pytest.raises(guard.AhrefsBlocked):
        ahrefs_client.guarded_get("k", "site-explorer/x", {"a": 99})
    assert len(calls) == 5


def test_pending_counts_drop_when_stored(api):
    c = ahrefs_client.AhrefsClient("k")
    urls = ["https://a.nl/1", "https://a.nl/2"]
    assert c.pending_snapshots(urls, 6) == 4           # 2 pages x 2 snapshots, not months+1 each
    c.get_snapshot_history(urls[0], 6)
    assert c.pending_snapshots(urls, 6) == 2
    assert c.pending_snapshots(urls, 6) == 2 and len(c.get_snapshot_history(urls[0], 6)) == 2


def test_blocked_is_runtime_error(api):
    assert issubclass(guard.AhrefsBlocked, RuntimeError)
