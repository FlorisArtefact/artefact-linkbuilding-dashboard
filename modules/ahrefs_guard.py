"""Safety net around every Ahrefs API call (credits are limited; one run once used ~1 million).

- Paused unless AHREFS_ENABLED=1: no network call is made, only results already on disk are used.
- Disk cache (default 30 days): a result is paid for once, also across restarts and for every user of the app.
- Daily cap on real requests (AHREFS_DAILY_CAP, default 300), shared by all sessions via a small state file.
- Circuit breaker: the first 401/402/403/429 stops all further calls for a while, no retry storm.
Pure Python, no Streamlit, so it can be unit-tested without touching the API.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("AHREFS_CACHE_DIR") or _ROOT / ".cache" / "ahrefs")
CACHE_TTL_DAYS = int(os.getenv("AHREFS_CACHE_DAYS", "30"))
BREAKER_MINUTES = 60
_lock = threading.Lock()


class AhrefsBlocked(RuntimeError):
    """Raised instead of calling Ahrefs: paused, daily cap reached, or breaker tripped."""


CLIENT = os.getenv("AHREFS_CLIENT", "default")   # the app sets this from the client config: budgets are per client


def set_client(name: str) -> None:
    global CLIENT
    CLIENT = (name or "default").strip() or "default"


def monthly_budget() -> int:
    """Credits (API units) one client may use per calendar month through this app."""
    return int(os.getenv("AHREFS_MONTHLY_UNITS", "200000"))


def estimate_units(endpoint: str, data) -> int:
    """Measured 2026-11-04: any request costs at least 50 units; keyword rows cost ~12 each (keyword+position+traffic)."""
    rows = len(data.get("keywords", [])) if isinstance(data, dict) else 0
    return max(50, rows * 12)


def daily_cap() -> int:
    return int(os.getenv("AHREFS_DAILY_CAP", "300"))


def enabled() -> bool:
    return os.getenv("AHREFS_ENABLED", "0").strip() == "1"


def _key(endpoint: str, params: dict) -> str:
    raw = endpoint + json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()


def _path(endpoint: str, params: dict) -> Path:
    return CACHE_DIR / f"{_key(endpoint, params)}.json"


def cache_get(endpoint: str, params: dict):
    p = _path(endpoint, params)
    try:
        if p.exists() and time.time() - p.stat().st_mtime < CACHE_TTL_DAYS * 86400:
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def cache_has(endpoint: str, params: dict) -> bool:
    return cache_get(endpoint, params) is not None


def cache_put(endpoint: str, params: dict, data) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path(endpoint, params).write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _state_file() -> Path:
    return CACHE_DIR / "_state.json"


def _read_state() -> dict:
    try:
        s = json.loads(_state_file().read_text(encoding="utf-8"))
    except Exception:
        s = {}
    if s.get("day") != date.today().isoformat():
        s = {"day": date.today().isoformat(), "calls": 0, "blocked_until": s.get("blocked_until", 0),
             "reason": s.get("reason", ""), "units": s.get("units", {})}
    return s


def _write_state(s: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps(s), encoding="utf-8")
    except Exception:
        pass


def _month_units(s: dict) -> int:
    m = s.get("units", {})
    return int(m.get(CLIENT, 0)) if m.get("_month") == date.today().strftime("%Y-%m") else 0


def status() -> dict:
    s = _read_state()
    blocked = s.get("blocked_until", 0) > time.time()
    used = _month_units(s)
    return {"enabled": enabled(), "calls": s["calls"], "cap": daily_cap(), "remaining": max(daily_cap() - s["calls"], 0),
            "client": CLIENT, "units_used": used, "units_budget": monthly_budget(),
            "units_remaining": max(monthly_budget() - used, 0),
            "blocked": blocked, "reason": s.get("reason", "") if blocked else "",
            "blocked_minutes": max(int((s.get("blocked_until", 0) - time.time()) / 60) + 1, 0) if blocked else 0}


def check_allowed() -> None:
    st = status()
    if not st["enabled"]:
        raise AhrefsBlocked("Ahrefs is on hold (set AHREFS_ENABLED=1 to switch it on). Only stored results are shown.")
    if st["blocked"]:
        raise AhrefsBlocked(f"Ahrefs calls are paused for {st['blocked_minutes']} more minutes ({st['reason']}).")
    if st["units_remaining"] <= 0:
        raise AhrefsBlocked(f"Monthly Ahrefs budget of {st['units_budget']:,} credits for {st['client']} is used up. "
                            "Stored results still work; raise AHREFS_MONTHLY_UNITS to continue.")
    if st["remaining"] <= 0:
        raise AhrefsBlocked(f"Daily Ahrefs limit of {st['cap']} requests reached. Stored results still work.")


def register_call() -> None:
    with _lock:
        s = _read_state()
        s["calls"] += 1
        _write_state(s)


def register_units(n: int) -> None:
    with _lock:
        s = _read_state()
        u = s.get("units", {})
        if u.get("_month") != date.today().strftime("%Y-%m"):
            u = {"_month": date.today().strftime("%Y-%m")}
        u[CLIENT] = int(u.get(CLIENT, 0)) + int(n)
        s["units"] = u
        _write_state(s)


def trip(reason: str, minutes: int = BREAKER_MINUTES) -> None:
    with _lock:
        s = _read_state()
        s["blocked_until"] = time.time() + minutes * 60
        s["reason"] = reason
        _write_state(s)
