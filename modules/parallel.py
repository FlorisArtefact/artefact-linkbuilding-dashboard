"""Run independent (cached) data fetches at the same time instead of one after another.

Every Google call builds its own API client, so the calls are thread-safe; the Streamlit script context is attached to
each worker so st.cache_data keeps working. Results come back in the order of `calls`. A failing call returns
an empty DataFrame (the fetch functions already return empty frames on errors; this is a second safety net)."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd


def run_parallel(calls: list, max_workers: int = 8) -> list:
    """calls: [(func, args_tuple, kwargs_dict), ...] -> [result, ...] in the same order."""
    if not calls:
        return []
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        ctx = get_script_run_ctx()
    except Exception:
        add_script_run_ctx, ctx = None, None

    def _init():
        if ctx is not None:
            add_script_run_ctx(threading.current_thread(), ctx)

    def _one(call):
        func, args, kwargs = call
        try:
            return func(*args, **(kwargs or {}))
        except Exception:
            return pd.DataFrame()

    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls)), initializer=_init) as pool:
        return list(pool.map(_one, calls))
