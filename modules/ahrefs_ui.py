"""Streamlit helpers: Ahrefs status in the sidebar and the 'ask first' button pattern used for every Ahrefs fetch."""
import streamlit as st

from modules import ahrefs_guard as guard


def render_status() -> None:
    s = guard.status()
    if not s["enabled"]:
        st.warning("**Ahrefs is on hold.** No Ahrefs requests are made; only results stored earlier are shown. "
                   "Set `AHREFS_ENABLED=1` when credits are available.")
    elif s["blocked"]:
        st.warning(f"**Ahrefs paused** for {s['blocked_minutes']} min ({s['reason']}).")
    else:
        st.caption(f"Ahrefs requests today: **{s['calls']} / {s['cap']}**. Fetched results are stored for "
                   f"{guard.CACHE_TTL_DAYS} days and cost nothing again.")


def gated(key: str, what: str, pending: int, fetch):
    """Run fetch() without asking when everything is already stored (pending == 0). Otherwise show what it will cost
    and wait for a click. Returns the result, or None when nothing was fetched (yet)."""
    if pending == 0:
        try:
            return fetch()
        except RuntimeError as e:
            st.warning(str(e))
            return None
    s = guard.status()
    if not s["enabled"] or s["blocked"]:
        st.info(f"{what}: not loaded. " + ("Ahrefs is on hold." if not s["enabled"] else f"Ahrefs paused ({s['reason']})."))
        return None
    if pending > s["remaining"]:
        st.warning(f"{what} needs about {pending} Ahrefs requests, but only {s['remaining']} are left today "
                   f"(limit {s['cap']}). Narrow the selection or raise `AHREFS_DAILY_CAP`.")
        return None
    st.info(f"**{what}** is not loaded. It needs about **{pending} Ahrefs requests** (uses API credits); the result is "
            f"stored afterwards.")
    if st.button(f"Load from Ahrefs (~{pending} requests)", key=key):
        try:
            with st.spinner("Fetching from Ahrefs…"):
                return fetch()
        except RuntimeError as e:
            st.warning(str(e))
    return None
