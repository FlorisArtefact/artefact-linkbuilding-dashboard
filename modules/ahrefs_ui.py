"""Streamlit helpers: Ahrefs status in the sidebar and the 'ask first' button pattern used for every Ahrefs fetch."""
import streamlit as st

from modules import ahrefs_guard as guard


_CLIENT_VIEW = False


def set_client_view(flag: bool) -> None:
    """Client view: no credit counters, no load buttons. Stored results are still shown."""
    global _CLIENT_VIEW
    _CLIENT_VIEW = bool(flag)


def client_view() -> bool:
    return _CLIENT_VIEW


def render_status(api_key: str = "") -> None:
    if _CLIENT_VIEW:
        return
    s = guard.status()
    if not s["enabled"]:
        st.warning("**Ahrefs is on hold.** No Ahrefs requests are made; only results stored earlier are shown. "
                   "Set `AHREFS_ENABLED=1` when credits are available.")
    elif s["blocked"]:
        st.warning(f"**Ahrefs paused** for {s['blocked_minutes']} min ({s['reason']}).")
    else:
        st.caption(f"This client, this month: **{s['units_used']:,} / {s['units_budget']:,} credits** "
                   f"(requests today: {s['calls']} / {s['cap']}). Fetched results are stored for "
                   f"{guard.CACHE_TTL_DAYS} days and cost nothing again.")
        if api_key:
            try:
                from modules.ahrefs_client import workspace_usage
                w = workspace_usage(api_key)
                if w.get("used") is not None:
                    st.caption(f"Whole Ahrefs subscription (all users): {w['used']:,} / {w['limit']:,} credits, "
                               f"resets {str(w['reset'])[:10]}.")
            except Exception:
                pass


UNITS_PER_REQUEST = 50     # measured: page/domain summaries cost 50 units each


def gated(key: str, what: str, pending: int, fetch):
    """Run fetch() without asking when everything is already stored (pending == 0). Otherwise show what it will cost
    and wait for a click. Returns the result, or None when nothing was fetched (yet)."""
    if pending == 0:
        try:
            return fetch()
        except RuntimeError as e:
            st.warning(str(e))
            return None
    if _CLIENT_VIEW:
        return None                       # clients never trigger or see Ahrefs fetches
    s = guard.status()
    if not s["enabled"] or s["blocked"]:
        st.info(f"{what}: not loaded. " + ("Ahrefs is on hold." if not s["enabled"] else f"Ahrefs paused ({s['reason']})."))
        return None
    need = pending * UNITS_PER_REQUEST
    if need > s["units_remaining"]:
        st.warning(f"{what} needs about {need:,} credits, but this client has {s['units_remaining']:,} left this month "
                   f"(budget {s['units_budget']:,}).")
        return None
    if pending > s["remaining"]:
        st.warning(f"{what} needs about {pending} Ahrefs requests, but only {s['remaining']} are left today "
                   f"(limit {s['cap']}). Narrow the selection or raise `AHREFS_DAILY_CAP`.")
        return None
    st.info(f"**{what}** is not loaded. It needs about **{pending} Ahrefs requests = ~{need:,} credits**; the result is "
            f"stored afterwards.")
    if st.button(f"Load from Ahrefs (~{need:,} credits)", key=key):
        try:
            with st.spinner("Fetching from Ahrefs…"):
                return fetch()
        except RuntimeError as e:
            st.warning(str(e))
    return None
