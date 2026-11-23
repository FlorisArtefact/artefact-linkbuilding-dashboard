import html
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import os
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv

from modules.data_loader import (
    load_live_links,
    normalize_link_targets,
    is_approved,
    load_opportunities,
    apply_filters,
    get_landing_page_summary,
)
from modules.ahrefs_client import AhrefsClient
from modules.gsc_client import (
    load_gsc_csv,
    merge_gsc_into_table,
    get_gsc_data_api,
    get_gsc_monthly,
    get_gsc_queries,
    get_gsc_monthly_by,
    get_gsc_page_queries_monthly,
    gsc_api_available,
)
from modules.ga4_client import (
    get_revenue_by_page,
    merge_ga4_into_table,
    ga4_available,
    get_ga4_property_id,
    get_monthly_revenue_by_page,
    get_referral_traffic,
    load_ga4_csv,
)
from modules.citations_ui import render_citations_section
from modules.health_ui import render_health_section
from modules.referral_ui import render_referral_section
from modules.growth_ui import render_growth_section
from modules.ranking_ui import render_ranking_section
from modules.scorecard_ui import render_scorecard
from modules.evidence_ui import render_evidence_section
from modules.sheets_loader import (
    load_live_links_sheets,
    load_opportunities_sheets,
    sheets_available,
)
from modules import demo_data
from modules.roi_ui import sidebar_assumptions, render_roi_section
from modules.roi_model import compute_roi
from modules import budget_advice as _ba
from modules import evidence_model as _ev_model
from modules.growth_model import monthly_pivot as _monthly_pivot
from modules.budget_ui import render_budget_advice
from modules.search_ui import render_search_section
from modules.campaign_eval_ui import render_campaign_eval

load_dotenv()

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="Linkbuilding Dashboard | Artefact",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="auto",   # open on desktop, closed on phones (otherwise it covers the dashboard)
)

# ── Optional "Sign in with Google" gate with an e-mail allow-list (per app) ─────
def _check_login():
    """Returns None when not configured (the password gate below then applies).
    Configure in the app's secrets: an [auth] block (redirect_uri, cookie_secret, client_id, client_secret,
    server_metadata_url) plus ALLOWED_EMAILS = ["person@client.nl", "@client.nl"] ("@domain" allows a whole domain)."""
    try:
        allowed = [str(e).strip().lower() for e in st.secrets.get("ALLOWED_EMAILS", [])]
        configured = bool(allowed) and "auth" in st.secrets
    except Exception:
        return None
    if not configured:
        return None
    if not getattr(st.user, "is_logged_in", False):
        st.markdown("""<style>#MainMenu, footer, header {visibility: hidden;}</style>
        <div style="max-width:420px;margin:10vh auto 1rem;padding:2rem;border-radius:14px;background:white;
        box-shadow:0 4px 24px rgba(27,45,91,.12);border-top:4px solid #E5007D">
        <div style="color:#1B2D5B;font-size:1.4rem;font-weight:700">🔗 Linkbuilding Dashboard</div>
        <div style="color:#8B9BB4;font-size:.9rem">Sign in with your Google account to continue</div></div>""",
                    unsafe_allow_html=True)
        left, mid, right = st.columns([1, 1, 1])
        with mid:
            st.button("Sign in with Google", on_click=st.login, type="primary", width="stretch")
        return False
    email = str(st.user.get("email", "") or "").strip().lower()
    ok = bool(st.user.get("email_verified", True)) and any(
        email == a or (a.startswith("@") and email.endswith(a)) for a in allowed)
    if not ok:
        st.error(f"{email or 'This account'} does not have access to this dashboard.")
        st.button("Sign out", on_click=st.logout)
    return ok


# ── Password gate ──────────────────────────────────────────────────────────────
def _clients_secret() -> dict:
    """Optional [clients.<key>] blocks in the secrets: password = "...", config = '<client config JSON>' (no config =
    the repo's config.json). Lets one deployed app serve several clients, each with its own password."""
    try:
        return {k: dict(v) for k, v in dict(st.secrets.get("clients", {})).items()}
    except Exception:
        return {}


def _client_passwords() -> dict:
    return {str(v["password"]): k for k, v in _clients_secret().items() if v.get("password")}


def _check_password() -> bool:
    """Return True if no password is set, or if the user entered the correct one."""
    try:
        required = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        required = os.getenv("APP_PASSWORD", "")

    pmap = _client_passwords()
    if not required and not pmap:
        return True  # No password configured — skip gate

    if st.session_state.get("_authenticated"):
        return True

    # ── Login screen ────────────────────────────────────────────────────────────
    NAVY = "#1B2D5B"
    PINK = "#E5007D"
    st.markdown(f"""
    <style>
    #MainMenu, footer, header {{visibility: hidden;}}
    .login-wrap {{
        max-width: 400px; margin: 8vh auto; padding: 2.5rem;
        background: white; border-radius: 14px;
        box-shadow: 0 4px 24px rgba(27,45,91,0.12);
        border-top: 4px solid {PINK};
    }}
    .login-title {{
        color: {NAVY}; font-size: 1.4rem; font-weight: 700;
        margin-bottom: 0.3rem;
    }}
    .login-sub {{color: #8B9BB4; font-size: 0.88rem; margin-bottom: 1.5rem;}}
    </style>
    <div class="login-wrap">
        <div class="login-title">🔗 Linkbuilding Dashboard</div>
        <div class="login-sub">Artefact — enter your password to continue</div>
    </div>
    """, unsafe_allow_html=True)

    pwd = st.text_input("Password", type="password", label_visibility="collapsed",
                        placeholder="Enter password...")
    if st.button("Login", width="stretch", type="primary"):
        if pwd and pwd in pmap:                   # one app, several clients: the password picks the client
            st.session_state["_authenticated"] = True
            st.session_state["_client"] = pmap[pwd]
            st.rerun()
        elif required and pwd == required:
            st.session_state["_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password — please try again.")
    return False

def _access_mode() -> str:
    """'streamlit_viewers' in config.json = access is handled by Streamlit Cloud's own viewer list (private app,
    invite by e-mail). The in-app password screen is then skipped so viewers only sign in once."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"), encoding="utf-8") as f:
            return str(json.load(f).get("access", "")).strip().lower()
    except Exception:
        return ""

_login_ok = _check_login()
if _login_ok is False or (_login_ok is None and _access_mode() != "streamlit_viewers" and not _check_password()):
    st.stop()

# ── Brand colors ───────────────────────────────────────────────────────────────
NAVY   = "#1B2D5B"
PINK   = "#E5007D"
TEAL   = "#00B4C8"
LIGHT  = "#F0F4F8"
MID    = "#8B9BB4"
WHITE  = "#FFFFFF"
CHART_COLORS = [PINK, NAVY, TEAL, "#FF7043", "#7B1FA2"]
# No flag emojis: Windows shows them as letters ("NL NL", "GB EN"), which looks broken. Market codes only.
FLAGS: dict = {}

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
html, body, [class*="css"] {{ font-family: 'Roboto', sans-serif; }}

#MainMenu, footer {{ visibility: hidden; }}
[data-testid="stDecoration"] {{ display: none; }}
.block-container {{ padding-top: 3.6rem; padding-bottom: 2rem; max-width: 1400px; }}

/* Header: compact, one line */
.dash-header {{
    background: linear-gradient(120deg, {NAVY} 0%, #2A4080 55%, #8B1060 100%);
    padding: 0.9rem 1.4rem; border-radius: 14px; margin-bottom: 1rem;
    display: flex; justify-content: space-between; align-items: center;
}}
.dash-header h1 {{ color: white; margin: 0; padding: 0; font-size: 1.35rem; font-weight: 700; }}
.dash-header .sub {{ color: rgba(255,255,255,0.72); font-size: 0.82rem; margin-top: 0.15rem; }}
.header-right {{ display: flex; align-items: center; gap: 0.8rem; flex-shrink: 0; }}
@media (max-width: 640px) {{
    .dash-header {{ flex-direction: column; align-items: flex-start; gap: 0.7rem; }}
    .dash-header h1 {{ font-size: 1.15rem; }}
    .client-logo img {{ height: 30px; }}
}}
.client-logo {{ background: white; border-radius: 10px; padding: 0.3rem 0.7rem; display: flex; align-items: center; }}
.client-logo img {{ height: 40px; width: auto; display: block; }}
.artefact-pill {{
    background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.28);
    color: white; padding: 0.3rem 1rem; border-radius: 20px;
    font-size: 0.78rem; font-weight: 600; letter-spacing: 0.5px;
}}

/* Section titles: one calm accent bar instead of underlines */
.section-title {{
    color: {NAVY}; font-weight: 700; font-size: 1.05rem;
    margin: 1.4rem 0 0.7rem; padding-left: 0.65rem; border-left: 4px solid {PINK}; display: block;
}}
.section-hint {{ color: {MID}; font-size: 0.85rem; margin: -0.4rem 0 0.8rem 0.85rem; }}

/* KPI tiles = white cards */
[data-testid="stMetric"] {{
    background: {WHITE}; border: 1px solid #E8ECF2; border-radius: 12px; padding: 0.75rem 1rem;
    box-shadow: 0 1px 6px rgba(27,45,91,0.05);
}}
[data-testid="stMetricLabel"] p {{ color: {MID}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: .5px; }}
[data-testid="stMetricValue"] {{ color: {NAVY}; font-weight: 700; }}

/* Main navigation tabs */
[data-baseweb="tab-list"] {{ gap: 0.2rem; border-bottom: 1px solid #DDE3EC; }}
button[role="tab"] {{ padding: 0.65rem 1.1rem; font-weight: 600; }}
button[role="tab"][aria-selected="true"] {{ color: {PINK}; }}
[data-baseweb="tab-highlight"] {{ background-color: {PINK}; height: 3px; }}

/* Data-connection chips */
.status-strip {{ display: flex; flex-wrap: wrap; gap: .5rem; margin: .2rem 0 .9rem; align-items: center; }}
.chip {{ font-size: .78rem; padding: .25rem .7rem; border-radius: 999px; border: 1px solid #DDE3EC; background: {WHITE}; color: {NAVY}; }}
.chip.ok {{ border-color: #BFE5CF; background: #EEF9F2; }}
.chip.todo {{ border-color: #F2D9A6; background: #FFF8E8; }}
.chip small {{ color: {MID}; }}

.lang-card {{
    background: {WHITE}; border: 1px solid #E8ECF2; border-radius: 10px; padding: 0.8rem 1rem;
    margin-bottom: 0.6rem; border-left: 3px solid {PINK};
}}
.lang-name {{ font-weight: 600; color: {NAVY}; font-size: 0.95rem; }}
.lang-cost {{ color: {PINK}; font-size: 1.1rem; font-weight: 700; }}
.lang-sub  {{ color: {MID}; font-size: 0.72rem; margin-top: 0.15rem; }}

.broken-alert {{
    background: #FFF3E0; border: 1px solid #FF9800; border-radius: 8px;
    padding: 0.9rem 1.2rem; margin-bottom: 1rem; color: #E65100; font-size: 0.87rem;
}}
.dash-footer {{
    text-align: center; color: {MID}; font-size: 0.72rem;
    margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #E8ECF2;
}}
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_eur(val: float) -> str:
    return f"€{val:,.0f}"

def chart_layout(title: str, height: int = 300) -> dict:
    """Base layout — does NOT include yaxis/xaxis so callers can set them freely."""
    return dict(
        title=dict(text=title, font=dict(size=13, color=NAVY, family="Roboto")),
        paper_bgcolor=WHITE, plot_bgcolor=WHITE,
        font=dict(family="Roboto", color=NAVY, size=11),
        height=height, margin=dict(t=45, b=30, l=40, r=20),
    )

AXIS_DEFAULT = dict(gridcolor="#E8ECF2", showgrid=True, zeroline=False)
AXIS_NO_GRID = dict(showgrid=False, zeroline=False)


# ── Load config ────────────────────────────────────────────────────────────────
_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config() -> dict:   # not cached: a fallback must never get stuck for the whole server life
    # Multi-client hosting: each deployed app carries its OWN client config in its secrets
    # (CLIENT_CONFIG_JSON = the content of that client's config.json). That keeps client names,
    # sheet IDs and domains out of the repo, so one codebase can serve many isolated apps.
    ck = st.session_state.get("_client")
    if ck:
        c = _clients_secret().get(ck, {}).get("config")
        if c:
            return json.loads(c) if isinstance(c, str) else dict(c)
        cfg_path = os.path.join(_APP_DIR, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                return json.load(f)
    raw = ""
    try:
        raw = st.secrets.get("CLIENT_CONFIG_JSON", "")
    except Exception:
        pass
    raw = raw or os.getenv("CLIENT_CONFIG_JSON", "")
    if raw:
        return json.loads(raw)
    cfg_path = os.getenv("CONFIG_FILE", "config.json")      # e.g. clients/<client>.json for local testing
    if not os.path.isabs(cfg_path):
        cfg_path = os.path.join(_APP_DIR, cfg_path)         # independent of the folder the server was started from
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f)
    return {"client_name": "Client", "languages": ["NL", "EN", "DE"], "currency": "EUR"}

config    = load_config()
_xp = config.get("excel_path", "")
if _xp and not os.path.isabs(_xp):
    config["excel_path"] = os.path.normpath(os.path.join(_APP_DIR, _xp))   # relative paths count from the app folder
LANGUAGES = config.get("languages", ["NL", "EN", "DE"])
CLIENT    = config.get("client_name", "Client")
from modules import ahrefs_guard as _ahrefs_guard
_ahrefs_guard.set_client(CLIENT)

# View mode: "client" hides everything internal (credits, load buttons, set-up, assumptions). It is set per deployment
# (env var / secret / config), never by a URL parameter, so a client cannot switch to the analyst view.
try:
    _vm = st.secrets.get("VIEW_MODE", "")
except Exception:
    _vm = ""
# On Streamlit Cloud (code under /mount/src) the default is the client view: that URL is what clients open.
_ON_CLOUD = os.path.abspath(__file__).replace("\\", "/").startswith("/mount/src")
CLIENT_MODE = str(_vm or os.getenv("VIEW_MODE") or config.get("view_mode", "client" if _ON_CLOUD else "admin")).strip().lower() == "client"
from modules import ahrefs_ui as _ahrefs_ui
_ahrefs_ui.set_client_view(CLIENT_MODE)
_boot = st.empty()
_boot.info("⏳ Loading the dashboard — data is fetched from the sheet, Search Console and Analytics. "
           "The first load can take a couple of minutes; after that it is fast.")

# Resolve credentials path relative to project root — needed by Sheets, GSC API and GA4
_creds_file = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    config.get("google_sheets", {}).get("credentials_file", "")
)
_sheet_id = config.get("google_sheets", {}).get("spreadsheet_id", "")


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='font-size:1.25rem;font-weight:700;color:{NAVY};line-height:1.1'>Artefact</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:0.75rem;color:{MID};margin-bottom:.6rem;'>Linkbuilding dashboard</div>", unsafe_allow_html=True)
    if st.session_state.get("_client") and len(_clients_secret()) > 1:
        if st.button("↩ Other client / sign out", width="stretch"):
            for _k in ("_authenticated", "_client"):
                st.session_state.pop(_k, None)
            st.rerun()
    if CLIENT_MODE:
        _sb_filters, _sb_setup = st.container(), st.container()   # set-up stays empty for clients
    else:
        _sb_filters, _sb_setup = st.tabs(["🔍 Filters", "⚙️ Set-up"])
    # Filters first (what a client touches); everything technical lives under Set-up (analyst).
    _sb_filters.__enter__()
    # — Filters
    current_year = datetime.now().year
    year_opts = list(range(current_year - 1, current_year + 1))   # no future year: it would only show empty pages
    selected_year = st.selectbox("Year", year_opts, index=year_opts.index(current_year))
    selected_quarter = st.selectbox("Quarter", ["All", "Q1", "Q2", "Q3", "Q4"])
    _months = ["All", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    selected_month = st.selectbox("Month", _months, help="Only links placed in this month (and the spend on them). Combine with Year.")
    campaign_filter = st.text_input("Campaign", placeholder="e.g. Paid linkbuilding")


    # — ROI assumptions (generic ROI & budget-advice module)
    if CLIENT_MODE:
        from modules.roi_model import merged_assumptions as _merged
        roi_assumptions = _merged(config.get("roi"))
    else:
        roi_assumptions = sidebar_assumptions(config)
    _sb_filters.__exit__(None, None, None)
    _sb_setup.__enter__()
    if CLIENT_MODE:
        demo_mode = bool(config.get("demo_mode", False))
        use_sheets = sheets_available(config) and not demo_mode
        _dp = config.get("excel_path", "")
        excel_source = _dp if (not use_sheets and not demo_mode and _dp and os.path.exists(_dp)) else None
        ahrefs_key = os.getenv("AHREFS_API_KEY", "")
        use_gsc_api = gsc_api_available(config, _creds_file)
        gsc_csv = None
        use_ga4 = ga4_available(config, _creds_file)
        ga4_csvs = {}
    else:
        # — Data source
        st.markdown("**📂 Data source**")
        demo_mode = st.toggle(
            "🧪 Demo data", value=bool(config.get("demo_mode", False)),
            help="Shows the dashboard with SYNTHETIC data — no credentials needed. Never show demo numbers as real results.",
        )
        use_sheets = sheets_available(config) and not demo_mode

        if demo_mode:
            st.warning("DEMO MODE — all data is synthetic")
            excel_source = None
        elif use_sheets:
            sid = config["google_sheets"]["spreadsheet_id"]
            st.success("🟢 Google Sheets (live)")
            st.caption("Auto-refreshes every 5 minutes")
            with st.expander("Sheet details"):
                st.markdown(f"[Open Google Sheet](https://docs.google.com/spreadsheets/d/{sid})")
                st.caption(f"ID: `{sid}`")
            if st.button("🔄 Refresh now", key="refresh_sheets"):
                st.cache_data.clear()
                st.rerun()
            excel_source = None   # not used when Sheets is active
        else:
            uploaded_excel = st.file_uploader("Upload Excel database", type=["xlsx"], label_visibility="collapsed")
            default_path = config.get("excel_path", "")
            if uploaded_excel:
                excel_source = uploaded_excel
                st.success("Excel loaded ✓")
            elif default_path and os.path.exists(default_path):
                excel_source = default_path
                st.caption(f"Using: {os.path.basename(default_path)}")
            else:
                excel_source = None


        # — APIs
        st.markdown("**🔌 API connections**")
        ahrefs_key = os.getenv("AHREFS_API_KEY", "")
        if not ahrefs_key:
            ahrefs_key = st.text_input("Ahrefs API key", type="password", placeholder="Bearer token")
            if ahrefs_key:
                os.environ["AHREFS_API_KEY"] = ahrefs_key

        ahrefs_ok = bool(ahrefs_key)
        st.markdown(f"{'🟢' if ahrefs_ok else '🔴'} Ahrefs API {'(connected)' if ahrefs_ok else '(no key)'}")
        if ahrefs_ok and not demo_mode:
            from modules.ahrefs_ui import render_status as _ahrefs_status
            _ahrefs_status(ahrefs_key)

        # Search Console — API is automatic, CSV upload only as a fallback
        st.markdown("**📊 Search Console data**")
        use_gsc_api = gsc_api_available(config, _creds_file)
        if use_gsc_api:
            st.success("🟢 Search Console API (configured)")
            st.caption("Auto-refreshes every 6 hours — no manual work needed. "
                       "Shows no data until the service account is granted access in Search Console.")
            with st.expander("📎 No API access yet? Upload exports (CSV/ZIP)"):
                st.caption("Per market: Performance → Pages → Export (CSV or ZIP, last 3 months). "
                           "Used only while the API returns no data. Upload all markets together.")
                gsc_csv = st.file_uploader("GSC exports", type=["csv", "zip"], accept_multiple_files=True,
                                           key="gsc_csv_multi", label_visibility="collapsed")
        else:
            gsc_csv = st.file_uploader(
                "Upload GSC export (Pages CSV)",
                type=["csv"],
                help="In GSC: Performance → Pages → Export as CSV",
                label_visibility="collapsed",
            )
            st.caption("🔴 Manual upload (configure the API to automate this)")
            with st.expander("How to connect the API instead?"):
                st.info(
                    "1. Enable **Search Console API** in Google Cloud (same project as Sheets)\n"
                    "2. In Search Console: Settings → Users and permissions → Add user →\n"
                    "   paste the service account email → Restricted (read-only)\n"
                    "3. Add the site URL(s) under `gsc_properties` in config.json\n\n"
                    "Once set up, this upload disappears and data refreshes automatically."
                )

        # Revenue & conversions — Google Analytics 4
        st.markdown("**💰 Revenue & conversions (GA4)**")
        use_ga4 = ga4_available(config, _creds_file)
        ga4_csvs = {}
        if use_ga4:
            st.success("🟢 Google Analytics 4 (live)")
            st.caption("Revenue, conversions & ROI per landing page")
        else:
            st.caption("🔴 GA4 not connected")
            with st.expander("How to connect GA4?"):
                st.info(
                    "1. Enable **Google Analytics Data API** in Google Cloud (same project as Sheets)\n"
                    "2. In GA4: Admin → Property Access Management → Add users →\n"
                    "   paste the service account email → role: Viewer\n"
                    "3. Add the GA4 Property ID under `ga4.property_id` in config.json"
                )
            with st.expander("📎 Or upload a GA4 export (CSV)"):
                st.caption("Per market: last 90 days, dimensions *Landing page + query string* and "
                           "*Session default channel group*, metrics *Sessions*, *Key events*, *Total revenue*.")
                for _l in LANGUAGES:
                    ga4_csvs[_l] = st.file_uploader(f"GA4 export {_l}", type=["csv"], key=f"ga4csv_{_l}")


        # — Share
        st.markdown("**🔗 Share this dashboard**")
        import socket
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "10.52.130.204"

        with st.expander("📡 How to share with colleagues"):
            st.markdown(f"""
    **Same network (office / VPN)**
    Your colleague opens this URL in their browser:
    ```
    http://{local_ip}:8502
    ```
    Works as long as you are on the same network.

    ---

    **Outside the network — ngrok (free, temporary)**
    1. Download [ngrok.com](https://ngrok.com/download)
    2. Open a new terminal window
    3. Run: `ngrok http 8502`
    4. Copy the `https://xxxx.ngrok.io` URL
    5. Share it — anyone can access it

    ---

    **Always online — Streamlit Cloud (free)**
    1. Push this project to a GitHub repo (private)
    2. Go to [share.streamlit.io](https://share.streamlit.io)
    3. Connect your repo → deploy
    4. Add your Ahrefs API key under *App settings → Secrets*
    """)

        st.divider()
        st.caption(f"Client: **{CLIENT}**  \nGenerated: {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    _sb_setup.__exit__(None, None, None)


# ── Guard: no data ─────────────────────────────────────────────────────────────
if not demo_mode and not use_sheets and excel_source is None:
    st.markdown(f"""
    <div class="dash-header">
        <div>
            <h1>🔗 Linkbuilding Dashboard</h1>
            <div class="sub">Artefact — Professional Link Building Intelligence</div>
        </div>
        <div class="artefact-pill">Artefact</div>
    </div>
    """, unsafe_allow_html=True)
    st.info("👈 Upload your Excel database in the sidebar to get started.")
    st.stop()


# ── Market filter (top of the page): everything below — KPIs, scorecard, all tabs — follows it ──
header_box = st.container()
market_box = st.container()
ALL_LANGUAGES = list(LANGUAGES)
if len(ALL_LANGUAGES) > 1:
    with market_box:
        _opts = {"All markets": None, **{f"{FLAGS.get(l, '')} {l}".strip(): l for l in ALL_LANGUAGES}}
        _pick = st.radio("Market", list(_opts), horizontal=True, key="market_filter", label_visibility="collapsed",
                         help="Pick one country to see only its links, spend, revenue and effect.")
        _sel_lang = _opts.get(_pick)
    if _sel_lang:
        LANGUAGES = [_sel_lang]
market_label = LANGUAGES[0] if len(LANGUAGES) == 1 and len(ALL_LANGUAGES) > 1 else "All markets"

# ── Load & filter data ─────────────────────────────────────────────────────────
q_filter    = None if selected_quarter == "All" else selected_quarter
camp_filter = campaign_filter.strip() or None
_month_no   = None if selected_month == "All" else _months.index(selected_month)

# Period the GA4 numbers (revenue, conversions, referral visitors) cover = the Year / Quarter / Month filters.
# Never later than today; a period that has not started yet falls back to the last 90 days.
_today = pd.Timestamp.today().normalize()
if _month_no:
    _p0 = pd.Timestamp(selected_year, _month_no, 1)
    _p1 = _p0 + pd.offsets.MonthEnd(0)
elif q_filter:
    _p0 = pd.Timestamp(selected_year, 3 * int(q_filter[1]) - 2, 1)
    _p1 = _p0 + pd.offsets.MonthEnd(3)
else:
    _p0, _p1 = pd.Timestamp(selected_year, 1, 1), pd.Timestamp(selected_year, 12, 31)
_p1 = min(_p1, _today - pd.Timedelta(days=1))
if _p0 > _p1:
    _p0, _p1 = _today - pd.Timedelta(days=90), _today - pd.Timedelta(days=1)
PERIOD_START, PERIOD_END = _p0.date().isoformat(), _p1.date().isoformat()
PERIOD_DAYS = (_p1 - _p0).days + 1
PERIOD_TXT = f"{_p0:%-d %b} – {_p1:%-d %b %Y}" if os.name != "nt" else f"{_p0.day} {_p0:%b} – {_p1.day} {_p1:%b %Y}"

def page_label(url) -> str:
    """Readable chart label: 'Homepage' or the last two path parts ('collections/apple-watch-bandjes')."""
    path = urlparse(str(url)).path.strip("/")
    return "Homepage" if not path else "/".join(path.split("/")[-2:])


# All markets are fetched at the same time (first load went from ~2 minutes to a fraction of that).
from modules.parallel import run_parallel
_live_tab = config.get("google_sheets", {}).get("live_tab", "")
_opp_tab = config.get("google_sheets", {}).get("opp_tab", "")
_sheet_pre = {}
if use_sheets and not demo_mode:
    _res = run_parallel([(load_live_links_sheets, (_creds_file, _sheet_id, l, _live_tab), {}) for l in LANGUAGES]
                        + [(load_opportunities_sheets, (_creds_file, _sheet_id, l, _opp_tab), {}) for l in LANGUAGES])
    _sheet_pre = {("live", l): _res[i] for i, l in enumerate(LANGUAGES)}
    _sheet_pre.update({("opp", l): _res[len(LANGUAGES) + i] for i, l in enumerate(LANGUAGES)})

live_data, opp_data, raw_links = {}, {}, {}
for lang in LANGUAGES:
    if demo_mode:
        raw = demo_data.demo_live_links(lang, selected_year)
    elif use_sheets:
        raw = _sheet_pre[("live", lang)]
    else:
        raw = load_live_links(excel_source, lang)
    raw = normalize_link_targets(raw, config.get("domains", {}).get(lang, ""))
    raw_links[lang] = raw   # unfiltered: growth analysis needs the FIRST link ever to a page
    live_data[lang] = apply_filters(raw, year=selected_year, quarter=q_filter, campaign=camp_filter)
    if _month_no and not live_data[lang].empty and "LL Date" in live_data[lang].columns:
        live_data[lang] = live_data[lang][pd.to_datetime(live_data[lang]["LL Date"], errors="coerce").dt.month == _month_no]

    if demo_mode:
        opp_data[lang] = demo_data.demo_opportunities(lang)
    elif use_sheets:
        opp_data[lang] = _sheet_pre[("opp", lang)]
    else:
        opp_data[lang] = load_opportunities(excel_source, lang)

all_live = pd.concat(live_data.values(), ignore_index=True) if any(not d.empty for d in live_data.values()) else pd.DataFrame()

# ── Search Console data: API (automatic) or CSV (fallback) ─────────────────────
if demo_mode:
    gsc_df = pd.concat([demo_data.demo_gsc(l) for l in LANGUAGES], ignore_index=True)
elif use_gsc_api:
    _sites = [config.get("gsc_properties", {}).get(l, "") for l in LANGUAGES]
    _sites = [x for x in _sites if x]
    # Prefetch everything from Google at once: GSC pages + monthly clicks, and GA4 (revenue, referral, monthly).
    _pre = [(get_gsc_data_api, (_creds_file, x), {}) for x in _sites] + [(get_gsc_monthly, (_creds_file, x), {}) for x in _sites]
    _ga4_calls = {}
    if use_ga4 and not demo_mode:
        for _l in LANGUAGES:
            _pid = get_ga4_property_id(config, _l)
            if not _pid:
                continue
            _host = config.get("domains", {}).get(_l, "") if not config.get("ga4", {}).get("property_ids", {}).get(_l) else ""
            _paths = tuple(sorted({urlparse(str(u).strip()).path or "/" for u in raw_links.get(_l, pd.DataFrame()).get("Link to", pd.Series(dtype=str)).dropna()
                                   if str(u).strip()}))
            _ga4_calls[(_l, "rev")] = (get_revenue_by_page, (_creds_file, _pid), dict(hostname=_host, start_date=PERIOD_START, end_date=PERIOD_END))
            _ga4_calls[(_l, "ref")] = (get_referral_traffic, (_creds_file, _pid), dict(hostname=_host, start_date=PERIOD_START, end_date=PERIOD_END))
            _ga4_calls[(_l, "mon")] = (get_monthly_revenue_by_page, (_creds_file, _pid), dict(hostname=_host, paths=_paths))
    _res = run_parallel(_pre + list(_ga4_calls.values()))
    _gsc_dfs = _res[:len(_sites)]
    _ga4_pre = dict(zip(_ga4_calls.keys(), _res[len(_pre):]))
    gsc_df = pd.concat(_gsc_dfs, ignore_index=True) if _gsc_dfs else pd.DataFrame()
    if gsc_df.empty and gsc_csv:   # API has no access yet -> fall back to uploaded exports
        _csv_dfs = [d for d in (load_gsc_csv(f) for f in gsc_csv) if not d.empty]
        gsc_df = pd.concat(_csv_dfs, ignore_index=True) if _csv_dfs else pd.DataFrame()
else:
    gsc_df = load_gsc_csv(gsc_csv) if gsc_csv else pd.DataFrame()

# ── GA4 revenue & conversions per language ──────────────────────────────────────
ga4_data, monthly_data, referral_data = {}, {}, {}
if demo_mode:
    use_ga4 = True
    referral_data = {lang: demo_data.demo_referral(lang, raw_links.get(lang)) for lang in LANGUAGES}
    ga4_data = {lang: demo_data.demo_ga4(lang) for lang in LANGUAGES}
    monthly_data = {lang: demo_data.demo_monthly(lang, raw_links.get(lang)) for lang in LANGUAGES}
elif use_ga4:
    # If all markets share ONE property (no per-language id), the calls filter on this market's domain (see prefetch).
    if "_ga4_pre" not in globals():
        _ga4_pre = {}
        for _l in LANGUAGES:
            _pid = get_ga4_property_id(config, _l)
            if not _pid:
                continue
            _host = config.get("domains", {}).get(_l, "") if not config.get("ga4", {}).get("property_ids", {}).get(_l) else ""
            _paths = tuple(sorted({urlparse(str(u).strip()).path or "/" for u in raw_links.get(_l, pd.DataFrame()).get("Link to", pd.Series(dtype=str)).dropna()
                                   if str(u).strip()}))
            _ga4_pre[(_l, "rev")] = get_revenue_by_page(_creds_file, _pid, hostname=_host, start_date=PERIOD_START, end_date=PERIOD_END)
            _ga4_pre[(_l, "ref")] = get_referral_traffic(_creds_file, _pid, hostname=_host, start_date=PERIOD_START, end_date=PERIOD_END)
            _ga4_pre[(_l, "mon")] = get_monthly_revenue_by_page(_creds_file, _pid, hostname=_host, paths=_paths)
    for lang in LANGUAGES:
        ga4_data[lang] = _ga4_pre.get((lang, "rev"), pd.DataFrame())
        referral_data[lang] = _ga4_pre.get((lang, "ref"), pd.DataFrame())
        monthly_data[lang] = _ga4_pre.get((lang, "mon"), pd.DataFrame())
elif any(ga4_csvs.values()):
    use_ga4 = True
    ga4_data = {lang: (load_ga4_csv(f) if f else pd.DataFrame()) for lang, f in ga4_csvs.items()}

# Markets whose GA4 property reports another currency (e.g. UK = GBP): convert revenue to the reporting currency.
# Rate = config "fx_to_eur", e.g. {"EN": 1.15}. It is an assumption, shown in the ROI notes; set it to a sensible average.
_fx = config.get("fx_to_eur", {})
for _d in (ga4_data, monthly_data, referral_data):
    for _lang, _df in _d.items():
        if _fx.get(_lang) and _df is not None and not _df.empty and "Revenue" in _df.columns:
            _d[_lang] = _df.assign(Revenue=_df["Revenue"] * float(_fx[_lang]))


# ── Aggregate KPIs ─────────────────────────────────────────────────────────────
total_links  = len(all_live)
total_cost   = all_live["Price"].sum() if "Price" in all_live.columns and not all_live.empty else 0
avg_da       = all_live["DA"].mean()   if "DA"    in all_live.columns and not all_live.empty else 0
dofollow_pct = (
    (all_live["Link Type"] == "Dofollow").sum() / total_links * 100
    if total_links > 0 and "Link Type" in all_live.columns else 0
)
broken_links = (
    (~all_live["Status code"].isin([200])).sum()
    if "Status code" in all_live.columns and not all_live.empty else 0
)
lang_counts = {lang: len(df) for lang, df in live_data.items()}
lang_costs  = {lang: df["Price"].sum() if "Price" in df.columns else 0 for lang, df in live_data.items()}


# ── Dashboard header ───────────────────────────────────────────────────────────
quarter_label = selected_quarter if selected_quarter != "All" else "All quarters"
if selected_month != "All":
    quarter_label = f"{selected_month}"
data_badge    = "🧪 Demo data" if demo_mode else ("🟢 Live · Google Sheets" if use_sheets else "📁 Excel")
if CLIENT_MODE and not demo_mode:
    data_badge = f"Updated {datetime.now().strftime('%d-%m-%Y')}"
def _client_logo_html() -> str:
    """Client logo from config ("logo": path relative to the app folder), embedded so it also works in snapshots."""
    path = config.get("logo", "")
    if not path:
        return ""
    if path.startswith(("data:image/", "https://")):   # logo kept in the client's secrets, not in the public repo
        return f'<div class="client-logo"><img src="{html.escape(path, quote=True)}" alt="{CLIENT}"></div>'
    full = path if os.path.isabs(path) else os.path.join(_APP_DIR, path)
    try:
        import base64, mimetypes
        mime = mimetypes.guess_type(full)[0] or "image/png"
        with open(full, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'<div class="client-logo"><img src="data:{mime};base64,{b64}" alt="{CLIENT}"></div>'
    except OSError:
        return ""

with header_box:
    st.markdown(f"""
<div class="dash-header">
    <div>
        <h1>🔗 Linkbuilding Dashboard</h1>
        <div class="sub">{CLIENT} &nbsp;·&nbsp; {market_label} &nbsp;·&nbsp; {selected_year} &nbsp;·&nbsp; {quarter_label} &nbsp;·&nbsp; {data_badge}</div>
    </div>
    <div class="header-right">{_client_logo_html()}<div class="artefact-pill">Artefact</div></div>
</div>
""", unsafe_allow_html=True)

# Answer first: scorecard (filled further down, once ROI / growth / ranking exist), then what is connected.
scorecard_box = st.container()


def _chip(ok: bool, label: str, unlocks: str = "") -> str:
    tail = f" <small>· {unlocks}</small>" if (unlocks and not ok) else ""
    return f'<span class="chip {"ok" if ok else "todo"}">{"✓" if ok else "○"} {label}{tail}</span>'


_ga4_ok = bool(any(not d.empty for d in ga4_data.values()))
if not CLIENT_MODE:
    st.markdown('<div class="status-strip">'
                + _chip(True, "Links & costs", "")
                + _chip(bool(ahrefs_key) or demo_mode, "Ahrefs rankings", "add API key")
                + _chip(_ga4_ok or demo_mode, "GA4 revenue", "unlocks real ROI, growth, referral visitors")
                + _chip(bool(demo_mode or not gsc_df.empty), "Search Console", "unlocks click & position trend")
                + '</div>', unsafe_allow_html=True)


# ── Global KPIs ────────────────────────────────────────────────────────────────
_pipe = pd.concat([d for d in opp_data.values() if d is not None and not d.empty], ignore_index=True) \
    if any(d is not None and not d.empty for d in opp_data.values()) else pd.DataFrame()
c1, c2, c3, c4 = st.columns(4)
if total_links == 0 and not _pipe.empty:
    # Nothing placed yet (new client / new site): show the plan instead of four empty tiles, clearly labelled.
    _appr = int(is_approved(_pipe["Approved?"]).sum()) if "Approved?" in _pipe.columns else 0
    _price = pd.to_numeric(_pipe["Price"], errors="coerce") if "Price" in _pipe.columns else pd.Series(dtype=float)
    _dr = pd.to_numeric(_pipe["DR"], errors="coerce") if "DR" in _pipe.columns else pd.Series(dtype=float)
    c1.metric("Domains in pipeline", len(_pipe), help="Domains proposed for link building. Nothing is placed yet.")
    c2.metric("Proposed budget", fmt_eur(_price.sum()) if _price.notna().any() else "—",
              help="Sum of the prices in the proposal. Not spent yet: the investment only counts placed links.")
    c3.metric("Avg. DR of proposed domains", f"{_dr.mean():.0f}" if _dr.notna().any() else "—",
              help="Average Ahrefs Domain Rating of the proposed domains.")
    c4.metric("Approved so far", _appr, help="Proposed domains marked as approved. No links are placed yet.")
    st.caption("No links are placed yet, so these figures describe the proposal, not results.")
else:
    c1.metric(
        "Live links placed", total_links,
        help="Total number of live backlinks placed in the selected period, across all languages."
    )
    c2.metric(
        "Total investment", fmt_eur(total_cost),
        help="Sum of all costs for placed backlinks in the filtered period."
    )
    c3.metric(
        "Avg. DA", f"{avg_da:.0f}" if pd.notna(avg_da) and avg_da > 0 else "—",
        help="Domain Authority (DA) is a Moz score (0–100) measuring a domain's authority. "
             "A higher DA means more authority and therefore more SEO value for the backlink. "
             "This is the average DA of all domains linking to your pages."
    )
    c4.metric(
        "Dofollow %", f"{dofollow_pct:.0f}%",
        help="Dofollow links pass 'link juice' to the target page and are directly valuable for SEO. "
             "Nofollow links do not. A higher dofollow percentage is better for organic rankings."
    )
# ── GA4 business-impact KPIs (only shown once GA4 is connected) ────────────────
# Scope is explicit: selected market(s), organic search, and the period set by the Year/Quarter/Month filters (PERIOD_*).
# Whole site vs. the pages that received links are split.
if use_ga4 and any(not d.empty for d in ga4_data.values()):
    from modules.growth_model import norm_path as _norm_path
    _rev_all = _rev_linked = _conv_all = 0.0
    for _l, _d in ga4_data.items():
        if _d is None or _d.empty:
            continue
        _lp = {_norm_path(u) for u in raw_links.get(_l, pd.DataFrame()).get("Link to", pd.Series(dtype=str)).dropna() if str(u).strip()}
        _rev_all += float(_d["Revenue"].sum())
        _conv_all += float(_d["Conversions"].sum())
        _rev_linked += float(_d.loc[_d["path"].apply(_norm_path).isin(_lp), "Revenue"].sum())
    _scope = market_label

    g1, g2, g3 = st.columns(3)
    g1.metric(
        f"Organic revenue · {_scope} · {PERIOD_TXT}", fmt_eur(_rev_all),
        help="Organic-search revenue (GA4) of the WHOLE site for the selected market(s) in the period set by the "
             "Year / Quarter / Month filters (never beyond yesterday).")
    g2.metric(
        "…of which on pages with links", fmt_eur(_rev_linked),
        help="The part of that revenue landing on pages that received at least one link (all time).")
    g3.metric(
        "Share from pages with links", f"{_rev_linked / _rev_all:.0%}" if _rev_all else "—",
        help="Pages with links as a share of all organic revenue. See the 'Effect on organic' tab for how this develops.")


# ── Business value & budget advice (generic ROI module) ────────────────────────
# Fallback value basis while GA4 / Search Console are not connected: Ahrefs organic traffic
# estimate of the linked landing pages (monthly). Only fetched when there is no better source.
def _ahrefs_monthly_traffic(api_key: str, urls: tuple) -> float:
    """Sum of Ahrefs monthly organic traffic estimates for the given URLs (sequential; stored on disk by ahrefs_guard)."""
    client = AhrefsClient(api_key)
    return float(sum(client.get_landing_page_metrics(u)["est_traffic"] for u in urls))


_ahrefs_monthly = {}
_est_possible = bool(ahrefs_key and not demo_mode and gsc_df.empty and not any(not d.empty for d in ga4_data.values()))
# Opt-in: the estimate needs one Ahrefs request per landing page (slow the first time), so the page loads fast without it.
if _est_possible and st.session_state.get("ahrefs_est"):
    try:
        with st.spinner("Estimating organic traffic via Ahrefs..."):
            for _lang in LANGUAGES:
                _df = live_data.get(_lang, pd.DataFrame())
                if not _df.empty and "Link to" in _df.columns:
                    _ahrefs_monthly[_lang] = _ahrefs_monthly_traffic(
                        ahrefs_key, tuple(sorted(_df["Link to"].dropna().unique())))
    except RuntimeError as _e:
        _ahrefs_monthly = {}
        st.warning(str(_e))


# The page deep-dive needs per-page ranking history (Ahrefs / GSC export); the client view leaves it out instead of
# showing an empty chart. Rankings per market are in the Results tab.
HAS_REVENUE = bool(demo_mode or _ga4_ok)   # without GA4 (Search Console-only clients) the revenue tabs give way to Search Console
_tab_keys = (([] if HAS_REVENUE else ["eval"]) + ["advice"] + (["effect", "roi"] if HAS_REVENUE else ["search"]) + ["results"]
             + (["reach"] if HAS_REVENUE else []) + ["links"] + ([] if CLIENT_MODE else ["deep"]))
_tab_names = {"eval": "📊 Campaign evaluation", "advice": "🧭 Budget advice", "effect": "🏆 Effect on organic", "roi": "💶 Revenue vs. budget",
              "search": "🔎 Search performance", "results": "📈 Results", "reach": "🌍 Reach (referral & mentions)",
              "links": "🔗 Links & health", "deep": "🔬 Page deep-dive"}
TAB = dict(zip(_tab_keys, st.tabs([_tab_names[k] for k in _tab_keys])))
# ── Effect on organic: linked pages vs. not linked vs. whole domain, authority ──────────
def _domain_histories(api_key: str, domains: tuple) -> dict:
    from modules.ahrefs_client import get_domain_history
    return {d: get_domain_history(api_key, d) for d in domains}


_search_head = None
if HAS_REVENUE:
    TAB["effect"].__enter__()
    if demo_mode:
        _hist = {l: demo_data.demo_domain_history(l, raw_links.get(l)) for l in LANGUAGES}
        _gscm = {l: demo_data.demo_gsc_monthly(l) for l in LANGUAGES}
    else:
        _doms = {l: config.get("domains", {}).get(l, "") for l in LANGUAGES}
        _hh = {}
        if ahrefs_key:
            from modules.ahrefs_client import pending_domain_history
            from modules.ahrefs_ui import gated as _gated
            _dom_list = tuple(d for d in _doms.values() if d)
            _hh = _gated("ev_load", "Domain authority and traffic history (Ahrefs)", pending_domain_history(_dom_list),
                         lambda: _domain_histories(ahrefs_key, _dom_list)) or {}
        _hist = {l: _hh.get(_doms[l]) for l in LANGUAGES}
        _gscm = {l: get_gsc_monthly(_creds_file, config.get("gsc_properties", {}).get(l, "")) for l in LANGUAGES} if use_gsc_api else {}

    evidence_headline = render_evidence_section(
        per_lang={l: {"monthly": monthly_data.get(l), "links": raw_links.get(l, pd.DataFrame())} for l in LANGUAGES},
        langs=LANGUAGES, domains=config.get("domains", {}), history=_hist, gsc_monthly=_gscm, currency="€",
        categories=config.get("categories"), content_keywords=config.get("content_keywords"), demo_mode=demo_mode, flags=FLAGS)
    TAB["effect"].__exit__(None, None, None)

    TAB["roi"].__enter__()
    if _est_possible and not st.session_state.get("ahrefs_est") and not CLIENT_MODE:
        st.info("💡 No revenue data yet (waiting for GA4). You can get an **indicative** return based on the Ahrefs traffic "
                "estimate of the linked pages. It takes about a minute the first time and uses Ahrefs API units.")
        st.button("▶ Estimate return from Ahrefs traffic", key="ahrefs_est_btn",
                  on_click=lambda: st.session_state.update(ahrefs_est=True))
    roi_total = render_roi_section(
        client=CLIENT,
        period_label=f"{selected_year} · {quarter_label}",
        per_lang={
            lang: {"links": live_data.get(lang, pd.DataFrame()), "ga4": ga4_data.get(lang), "gsc": gsc_df,
                   "ahrefs_monthly": _ahrefs_monthly.get(lang, 0)}
            for lang in LANGUAGES
        },
        a=roi_assumptions,
        ga4_connected=bool(use_ga4),
        gsc_connected=bool(demo_mode or not gsc_df.empty),
        demo_mode=demo_mode,
        flags=FLAGS,
        window_days=PERIOD_DAYS if (use_ga4 and not demo_mode) else 90,
        window_txt=PERIOD_TXT if (use_ga4 and not demo_mode) else "last 90 days",
    )

    TAB["roi"].__exit__(None, None, None)
else:
    evidence_headline = None
    roi_total = compute_roi(float(total_cost or 0), 0.0, 0.0, 90, roi_assumptions)
    _search_head = None
    with TAB["search"]:
        _sites_by_lang = {l: config.get("gsc_properties", {}).get(l, "") for l in LANGUAGES}
        _host = lambda l: config.get("domains", {}).get(l, "").lower().removeprefix("www.")
        render_search_section(
            per_lang={l: {"monthly": get_gsc_monthly(_creds_file, x) if (use_gsc_api and x) else pd.DataFrame(),
                          "pages": gsc_df[gsc_df["Page"].astype(str).str.contains(_host(l), regex=False)] if (not gsc_df.empty and _host(l)) else gsc_df,
                          "queries": get_gsc_queries(_creds_file, x) if (use_gsc_api and x) else pd.DataFrame()}
                      for l, x in _sites_by_lang.items()},
            market_names={l: l for l in LANGUAGES},
            brand_terms=config.get("brand_terms") or [CLIENT.split(" ")[0]],
            groups=config.get("page_groups"))
        _m0 = get_gsc_monthly(_creds_file, _sites_by_lang.get(LANGUAGES[0], "")) if use_gsc_api else pd.DataFrame()
        if len(_m0) >= 4:
            _m0 = _m0.sort_values("month")
            _search_head = {"month": _m0.iloc[-1]["month"], "clicks": float(_m0.iloc[-1]["Clicks"]),
                            "clicks_before": float(_m0.iloc[-4]["Clicks"]), "month_before": _m0.iloc[-4]["month"]}

# ── Revenue growth on linked pages (per URL / category / domain) ────────────────
TAB["results"].__enter__()
growth_headline = render_growth_section(
    per_lang={lang: {"monthly": monthly_data.get(lang), "links": raw_links.get(lang, pd.DataFrame())} for lang in LANGUAGES},
    categories=config.get("categories"),
    currency="€",
    flags=FLAGS,
    demo_mode=demo_mode,
)

# ── Rankings of ALL pages that received links, per market ───────────────────────
ranking_result = render_ranking_section(
    per_lang={
        lang: {"urls": sorted(u for u in raw_links.get(lang, pd.DataFrame()).get("Link to", pd.Series(dtype=str)).dropna().unique()
                              if str(u).strip())}
        for lang in LANGUAGES
    },
    api_key=ahrefs_key,
    demo_mode=demo_mode,
    flags=FLAGS,
    gsc_creds=_creds_file if use_gsc_api else "",
    gsc_sites=config.get("gsc_properties", {}),
)

TAB["results"].__exit__(None, None, None)

# ── Referral visitors + brand mentions (side effects of the campaign) ───────────
if HAS_REVENUE:
    TAB["reach"].__enter__()
    render_referral_section(
        per_lang={lang: {"referral": referral_data.get(lang), "links": raw_links.get(lang, pd.DataFrame())} for lang in LANGUAGES},
        flags=FLAGS, demo_mode=demo_mode, period_txt=PERIOD_TXT if not demo_mode else "demo data",
    )
    render_citations_section(raw_links, FLAGS, demo_mode)
    TAB["reach"].__exit__(None, None, None)

# ── Budget advice (first tab): what to do with the budget, from the signals above ──────────────
with TAB["advice"]:
    _window = PERIOD_DAYS if (use_ga4 and not demo_mode) else 90
    _pages = []
    for _l in LANGUAGES:
        _lk = raw_links.get(_l, pd.DataFrame())
        _st = pd.DataFrame()
        _mon = monthly_data.get(_l)
        if _mon is not None and not _mon.empty and not _lk.empty:
            try:
                _st = _ev_model.page_table(_monthly_pivot(_mon, value="Revenue"), _lk)
            except Exception:
                _st = pd.DataFrame()
        _h = config.get("domains", {}).get(_l, "").lower().removeprefix("www.")
        _g = gsc_df[gsc_df["Page"].astype(str).str.contains(_h, regex=False)] if (not gsc_df.empty and _h) else gsc_df
        _pt = _ba.page_table(_lk, _g, _st)
        if not _pt.empty:
            _pages.append(_pt.assign(Market=_l) if len(LANGUAGES) > 1 else _pt)
    _pages_df = pd.concat(_pages, ignore_index=True) if _pages else pd.DataFrame()
    if not _pages_df.empty and "Market" in _pages_df.columns:
        _pages_df = _pages_df[["Market"] + [c for c in _pages_df.columns if c != "Market"]]
        _o = {a: i for i, a in enumerate(["more", "one_more", "pause", "wait", "keep", "watch"])}
        _pages_df = _pages_df.assign(_o=_pages_df["_action"].map(_o)).sort_values(["_o", "Spent"], ascending=[True, False]).drop(columns="_o")
    _targets = []
    for _l in LANGUAGES:
        _h = config.get("domains", {}).get(_l, "").lower().removeprefix("www.")
        _t = _ba.next_targets(gsc_df, raw_links.get(_l, pd.DataFrame()).get("Link to", pd.Series(dtype=str)).tolist(),
                              host=_h, n=15,
                              exclude_paths=tuple(config.get("target_exclude", [])))
        if not _t.empty:
            _targets.append(_t.assign(Market=_l)[["Market"] + list(_t.columns)] if len(LANGUAGES) > 1 else _t)
    _targets_df = pd.concat(_targets, ignore_index=True) if _targets else pd.DataFrame()
    _pipe_val = _ba.pipeline_value(_pipe)
    _pipe_ok = _ba.approved_only(_pipe)
    _pipe_total = float(pd.to_numeric(_pipe_ok["Price"], errors="coerce").sum()) if (not _pipe_ok.empty and "Price" in _pipe_ok.columns) else 0.0
    _vpv = {}
    for _l in LANGUAGES:
        _vpv.update(_ba.value_per_visit(ga4_data.get(_l), config.get("domains", {}).get(_l, "").lower().removeprefix("www.")))
    _alloc = _ba.allocation(_pages_df, _targets_df, _vpv or None, focus=config.get("focus_pages"), n=12)
    budget_headline = render_budget_advice(
        client=CLIENT, period_label=f"{selected_year} · {quarter_label}",
        overall_key=((roi_total or {}).get("advice", {}).get("key", "unknown") if HAS_REVENUE
                     else ("maintain" if (not _pages_df.empty and (_pages_df["_action"] == "pause").any()) else "unknown")),
        market_rows=_ba.per_market_roi({l: {"links": live_data.get(l, pd.DataFrame()), "ga4": ga4_data.get(l), "gsc": gsc_df}
                                        for l in LANGUAGES}, roi_assumptions, _window),
        pages=_pages_df, targets=_targets_df, pipeline=_pipe_val, pipeline_total=_pipe_total,
        has_links=bool(any(not raw_links.get(l, pd.DataFrame()).empty for l in LANGUAGES)),
        has_revenue=HAS_REVENUE, currency="€", allocation=_alloc,
        focus_set=bool(config.get("focus_pages")))

_eval_head = None
# ── Campaign evaluation (first tab for clients without revenue): domain + focus pages + what to build on ──────
if "eval" in TAB:
    with TAB["eval"]:
        _el = next((l for l in LANGUAGES if config.get("gsc_properties", {}).get(l)), LANGUAGES[0])
        _es = config.get("gsc_properties", {}).get(_el, "")
        _elk = raw_links.get(_el, pd.DataFrame())
        _eurls = tuple(sorted(u for u in _elk.get("Link to", pd.Series(dtype=str)).dropna().astype(str).unique() if u.strip()))
        _eval_head = render_campaign_eval(
            client=CLIENT,
            monthly=get_gsc_monthly(_creds_file, _es) if (use_gsc_api and _es) else pd.DataFrame(),
            links=_elk,
            queries=get_gsc_monthly_by(_creds_file, _es, "query", 9) if (use_gsc_api and _es) else pd.DataFrame(),
            page_queries=get_gsc_page_queries_monthly(_creds_file, _es, _eurls, 6) if (use_gsc_api and _es and _eurls) else pd.DataFrame(),
            allocation=_alloc, brand_terms=config.get("brand_terms") or [CLIENT.split(" ")[0]],
            launch_month=pd.Timestamp(config["launch_month"]) if config.get("launch_month") else None)

with scorecard_box:
    render_scorecard(roi_total, growth_headline, ranking_result.get("_total"), demo_mode, evidence_headline, None,
                     search=None if HAS_REVENUE else {**(_search_head or {}), **(_eval_head or {})})


# ── Overview: links per language + costs ───────────────────────────────────────
TAB["links"].__enter__()
st.metric("Links to check", broken_links if total_links else "—",
          delta=(f"{broken_links} ⚠️" if broken_links else "All good") if total_links else "Nothing placed yet",
          delta_color="inverse" if total_links else "off",
          help="Number of backlinks returning a non-200 HTTP status code (e.g. 403 or 404). "
               "The link may have been removed or blocked. Contact the publisher to resolve this.")
st.markdown('<div class="section-title">Overview by language</div>', unsafe_allow_html=True)
col_chart, col_cards = st.columns([3, 1])

with col_chart:
    if total_links > 0:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=list(lang_counts.keys()),
            y=list(lang_counts.values()),
            marker_color=CHART_COLORS[:len(LANGUAGES)],
            text=list(lang_counts.values()),
            textposition="outside",
            textfont=dict(color=NAVY, size=13, family="Roboto"),
        ))
        fig.update_layout(
            **chart_layout("Links placed per language", 280),
            showlegend=False,
            bargap=0.4,
            yaxis=AXIS_DEFAULT,
            xaxis=AXIS_NO_GRID,
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No links found for the selected filters.")

with col_cards:
    for lang, cost in lang_costs.items():
        cnt   = lang_counts.get(lang, 0)
        avg_c = cost / cnt if cnt > 0 else 0
        flag  = FLAGS.get(lang, "")
        st.markdown(f"""
        <div class="lang-card">
            <div class="lang-name">{flag} {lang}</div>
            <div class="lang-cost">{fmt_eur(cost)}</div>
            <div class="lang-sub">{cnt} links &nbsp;·&nbsp; avg {fmt_eur(avg_c)}/link</div>
        </div>
        """, unsafe_allow_html=True)


# ── Per-language tabs ──────────────────────────────────────────────────────────
tab_labels = [f"{FLAGS.get(l, '')} {l} ({lang_counts.get(l, 0)})".strip() for l in LANGUAGES]
tabs       = st.tabs(tab_labels)

ahrefs_client = AhrefsClient(ahrefs_key) if (ahrefs_key and not demo_mode) else None


def _render_pipeline(lang: str, expanded: bool = False) -> None:
    """Domains proposed for link building. Also shown when nothing is live yet (new client / new site)."""
    opp = opp_data.get(lang, pd.DataFrame())
    if opp.empty:
        return
    with st.expander(f"🎯 Opportunities pipeline — {lang} ({len(opp)})", expanded=expanded):
        approved    = opp[is_approved(opp["Approved?"])].copy() if "Approved?" in opp.columns else pd.DataFrame()
        st.caption(f"Total in pipeline: **{len(opp)}** &nbsp;·&nbsp; Approved: **{len(approved)}**")
        if "Price" in opp.columns and opp["Price"].notna().any():
            st.caption(f"Proposed budget in this list: **{fmt_eur(opp['Price'].sum())}** "
                       f"(not spent yet; the investment above only counts placed links)")
        opp_cols    = ["Domain", "DR", "Topic", "Price", "Proposed month", "Approved?", "Link to", "Anchor"]
        avail_opp   = [c for c in opp_cols if c in opp.columns]
        _show = opp[avail_opp].copy()
        for _c in _show.columns:                       # blank sheet cells: empty, not a grey "None"
            if _show[_c].dtype == object:
                _show[_c] = _show[_c].fillna("")
        st.dataframe(_show, width="stretch", hide_index=True, column_config={
            "Price": st.column_config.NumberColumn("Price", format="€%,.0f"),
            "DR": st.column_config.NumberColumn("DR", format="%d"),
            "Link to": st.column_config.LinkColumn("Link to")})


for i, lang in enumerate(LANGUAGES):
    with tabs[i]:
        df = live_data.get(lang, pd.DataFrame())

        if df.empty:
            st.info(f"No live links found for {lang} with the current filters.")
            _render_pipeline(lang, expanded=True)
            continue

        # Per-language KPIs
        k1, k2, k3, k4 = st.columns(4)
        l_cost   = df["Price"].sum() if "Price" in df.columns else 0
        l_avg_da = df["DA"].mean()   if "DA"    in df.columns else 0
        l_dofo   = (df["Link Type"] == "Dofollow").sum() if "Link Type" in df.columns else 0
        l_broken = (~df["Status code"].isin([200])).sum() if "Status code" in df.columns else 0
        k1.metric("Live links", len(df),
                  help=f"Number of live backlinks placed for {lang} in the selected period.")
        k2.metric("Investment", fmt_eur(l_cost),
                  help="Total cost of all placed backlinks for this language.")
        k3.metric("Avg. DA", f"{l_avg_da:.0f}" if pd.notna(l_avg_da) and l_avg_da > 0 else "—",
                  help="Average Domain Authority of the domains linking to your pages. "
                       "Scale: 0–100. Above 40 is good; above 60 is excellent.")
        k4.metric("Broken links", l_broken,
                  delta="⚠️" if l_broken else "OK", delta_color="inverse",
                  help="Links not returning HTTP 200. Check whether they are still live.")

        # Charts row 1
        ch1, ch2 = st.columns(2)

        with ch1:
            if "LL Date" in df.columns and df["LL Date"].notna().any():
                timeline         = df.copy()
                timeline["Month"] = timeline["LL Date"].dt.to_period("M").astype(str)
                monthly = (
                    timeline.groupby("Month")
                    .agg(Links=("Live Link", "count"), Cost=("Price", "sum"))
                    .reset_index()
                    .sort_values("Month")
                )
                fig_t = go.Figure()
                fig_t.add_trace(go.Bar(
                    x=monthly["Month"], y=monthly["Links"],
                    name="Links", marker_color=NAVY, yaxis="y",
                ))
                fig_t.add_trace(go.Scatter(
                    x=monthly["Month"], y=monthly["Cost"],
                    name="Cost (€)", mode="lines+markers",
                    line=dict(color=PINK, width=2),
                    marker=dict(size=6),
                    yaxis="y2",
                ))
                fig_t.update_layout(
                    **chart_layout(f"Links & cost per month — {lang}"),
                    legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
                    yaxis=dict(gridcolor="#E8ECF2", showgrid=True, zeroline=False, title="# Links"),
                    yaxis2=dict(overlaying="y", side="right", showgrid=False, zeroline=False, title="Cost (€)"),
                    xaxis=AXIS_NO_GRID,
                    barmode="group",
                )
                st.plotly_chart(fig_t, width="stretch")

        with ch2:
            if "DA" in df.columns and df["DA"].notna().any():
                fig_da = px.histogram(
                    df.dropna(subset=["DA"]),
                    x="DA", nbins=12,
                    title=f"Domain Authority distribution — {lang}",
                    color_discrete_sequence=[PINK],
                )
                fig_da.update_layout(
                    **chart_layout(f"Domain Authority distribution — {lang}"),
                    yaxis=AXIS_DEFAULT,
                    xaxis=dict(**AXIS_NO_GRID, title="Domain Authority"),
                )
                fig_da.update_traces(marker_line_width=0)
                st.plotly_chart(fig_da, width="stretch")

        # Charts row 2: cost vs. revenue per landing page
        ch3, ch4 = st.columns(2)

        with ch3:
            if "Link to" in df.columns and "Price" in df.columns:
                cost_per_lp = (
                    df.groupby("Link to")["Price"]
                    .sum()
                    .sort_values(ascending=True)
                    .tail(8)
                    .reset_index()
                )
                cost_per_lp["short"] = cost_per_lp["Link to"].apply(page_label)
                fig_lp = go.Figure(go.Bar(
                    x=cost_per_lp["Price"],
                    y=cost_per_lp["short"],
                    orientation="h",
                    marker_color=TEAL,
                    text=cost_per_lp["Price"].apply(fmt_eur),
                    textposition="outside",
                    textfont=dict(size=10, color=NAVY),
                ))
                fig_lp.update_layout(
                    **chart_layout(f"Cost per landing page — {lang}"),
                    yaxis=AXIS_NO_GRID,
                    xaxis=dict(**AXIS_DEFAULT, title="Cost (€)"),
                )
                st.plotly_chart(fig_lp, width="stretch")

        with ch4:
            ga4_lang_df = ga4_data.get(lang, pd.DataFrame())
            if not ga4_lang_df.empty and "Link to" in df.columns:
                from urllib.parse import urlparse
                links_paths = df[["Link to"]].dropna().drop_duplicates().copy()
                links_paths["_path"] = links_paths["Link to"].apply(lambda u: urlparse(u).path.rstrip("/") or "/")
                ga4_slim = ga4_lang_df.copy()
                ga4_slim["_path"] = ga4_slim["path"].apply(lambda p: p.rstrip("/") or "/")
                ga4_slim = ga4_slim.groupby("_path", as_index=False)["Revenue"].sum()
                rev_per_lp = links_paths.merge(ga4_slim, on="_path", how="inner")
                rev_per_lp = rev_per_lp.sort_values("Revenue", ascending=True).tail(8)

                if not rev_per_lp.empty:
                    rev_per_lp["short"] = rev_per_lp["Link to"].apply(page_label)
                    fig_rev = go.Figure(go.Bar(
                        x=rev_per_lp["Revenue"],
                        y=rev_per_lp["short"],
                        orientation="h",
                        marker_color=PINK,
                        text=rev_per_lp["Revenue"].apply(fmt_eur),
                        textposition="outside",
                        textfont=dict(size=10, color=NAVY),
                    ))
                    fig_rev.update_layout(
                        **chart_layout(f"Revenue per landing page — {lang} (GA4)"),
                        yaxis=AXIS_NO_GRID,
                        xaxis=dict(**AXIS_DEFAULT, title="Revenue (€)"),
                    )
                    st.plotly_chart(fig_rev, width="stretch")
                else:
                    st.info("No GA4 revenue data matched to these landing pages yet.")
            else:
                st.info("Revenue per landing page is not connected yet." if CLIENT_MODE else
                    "💡 Connect **Google Analytics 4** to see revenue per landing page here — "
                    "fully automatic once configured, no manual work. See sidebar for setup steps."
                )

        # Landing page performance table
        lp_info_col, _ = st.columns([4, 1])
        with lp_info_col:
            st.markdown('<div class="section-title">Landing page performance</div>', unsafe_allow_html=True)
        with st.expander("ℹ️ What do these columns mean?", expanded=False):
            st.markdown("""
| Column | Description |
|--------|-------------|
| **# Links** | Number of backlinks pointing to this landing page |
| **Total Cost (€)** | Sum of all costs for links to this page |
| **Avg DA** | Average Domain Authority of linking domains (0–100, higher = better) |
| **Dofollow** | Number of links passing link authority (valuable for SEO) |
| **Live (200)** | Number of links returning HTTP 200 — confirmed live and reachable |
| **Ahrefs Avg. Pos.** | Average organic position across all keywords this page ranks for, right now (source: Ahrefs) |
| **Ahrefs Traffic** | Estimated monthly organic traffic to this page (source: Ahrefs) |
| **GSC Position** | Average Google Search position (source: Search Console) |
| **Revenue (GA4)** | Total revenue attributed to this landing page (source: Google Analytics 4) |
| **Conversions** | Number of conversions/goal completions on this page (source: GA4) |
| **Revenue vs. cost** | Revenue divided by link-building cost for this page — above 1.0x means the revenue of the linked page is higher than its link budget (an indication, not proof that the links caused it) |

> **Tip:** Low avg. DA + poor GSC position = more high-quality links needed. High DA + strong position + high revenue vs. cost = campaign is working.
""")

        lp_table = get_landing_page_summary(df)

        if not gsc_df.empty:
            lp_table = merge_gsc_into_table(lp_table, gsc_df)

        ga4_lang_df = ga4_data.get(lang, pd.DataFrame())
        if not ga4_lang_df.empty:
            lp_table = merge_ga4_into_table(lp_table, ga4_lang_df)

        if demo_mode and not lp_table.empty:
            _demo_ah = {u: demo_data.demo_ahrefs_for_page(u) for u in lp_table["Landing Page"].dropna()}
            lp_table["Ahrefs Avg. Pos."] = lp_table["Landing Page"].map(lambda u: _demo_ah.get(u, {}).get("avg_position"))
            lp_table["Ahrefs Traffic"] = lp_table["Landing Page"].map(lambda u: _demo_ah.get(u, {}).get("est_traffic"))
            lp_table["Keywords"] = lp_table["Landing Page"].map(lambda u: _demo_ah.get(u, {}).get("keywords"))
        elif ahrefs_client and not lp_table.empty:
            from modules.ahrefs_ui import gated as _gated_lp
            urls        = lp_table["Landing Page"].dropna().tolist()
            ahrefs_data = _gated_lp(f"lp_load_{lang}", f"Ahrefs columns for {lang} landing pages",
                                    ahrefs_client.pending_landing(urls),
                                    lambda: ahrefs_client.enrich_landing_pages(urls))
            if ahrefs_data:
                lp_table["Ahrefs Avg. Pos."] = lp_table["Landing Page"].map(
                    lambda u: ahrefs_data.get(u, {}).get("avg_position")
                )
                lp_table["Ahrefs Traffic"] = lp_table["Landing Page"].map(
                    lambda u: ahrefs_data.get(u, {}).get("est_traffic")
                )
                lp_table["Keywords"] = lp_table["Landing Page"].map(
                    lambda u: ahrefs_data.get(u, {}).get("keywords")
                )

        col_cfg = {
            "Landing Page": st.column_config.LinkColumn("Landing Page", max_chars=55),
            "# Links":       st.column_config.NumberColumn("# Links", format="%d"),
            "Total Cost (€)": st.column_config.NumberColumn("Cost", format="€%,.0f"),
            "Avg DA":        st.column_config.ProgressColumn("Avg DA", min_value=0, max_value=100, format="%.0f"),
            "Dofollow":      st.column_config.NumberColumn("Dofollow", format="%d"),
            "Live (200)":    st.column_config.NumberColumn("Live (200)", format="%d"),
        }
        if "GSC Position" in lp_table.columns:
            col_cfg["GSC Position"] = st.column_config.NumberColumn("GSC Position", format="%.1f")
        for _c, _lbl in (("GSC Clicks", "GSC Clicks"), ("GSC Impressions", "GSC Impressions"), ("Sessions", "Sessions (GA4)")):
            if _c in lp_table.columns:
                col_cfg[_c] = st.column_config.NumberColumn(_lbl, format="%,.0f")
        if "Ahrefs Avg. Pos." in lp_table.columns:
            col_cfg["Ahrefs Avg. Pos."] = st.column_config.NumberColumn("Ahrefs Avg. Pos.", format="%.1f")
        if "Ahrefs Traffic" in lp_table.columns:
            col_cfg["Ahrefs Traffic"] = st.column_config.NumberColumn("Ahrefs Traffic", format="%d")
        if "Revenue" in lp_table.columns:
            col_cfg["Revenue"] = st.column_config.NumberColumn("Revenue (GA4)", format="€%,.0f")
        if "Conversions" in lp_table.columns:
            col_cfg["Conversions"] = st.column_config.NumberColumn("Conversions", format="%,.0f")
        if "ROI" in lp_table.columns:
            lp_table = lp_table.rename(columns={"ROI": "Revenue vs. cost"})
            lp_table["Revenue vs. cost"] = lp_table["Revenue vs. cost"].map(
                lambda v: "" if pd.isna(v) else f"{float(v):.1f}x")

        st.dataframe(lp_table, width="stretch", hide_index=True, column_config=col_cfg)

        with st.expander(f"📋 All live links — {lang} ({len(df)})"):
            show_cols = ["LL Date", "Live Link", "Domain", "DA", "Link Type", "Status code",
                         "Link to", "Anchor text", "Price", "Target campaign"]
            available = [c for c in show_cols if c in df.columns]
            st.dataframe(
                (df[available].sort_values("LL Date", ascending=False) if "LL Date" in df.columns else df[available])
                .apply(lambda c: c.fillna("") if c.dtype == object else c),
                width="stretch", hide_index=True,
                column_config={
                    "LL Date": st.column_config.DateColumn("Date live", format="DD-MM-YYYY"),
                    "Live Link": st.column_config.LinkColumn("Live link"),
                    "Link to": st.column_config.LinkColumn("Links to"),
                    "Price": st.column_config.NumberColumn("Price", format="€%,.0f"),
                    "Status code": st.column_config.NumberColumn("Status", format="%d"),
                },
            )

        _render_pipeline(lang)


# ── Broken links section ───────────────────────────────────────────────────────
if broken_links > 0 and "Status code" in all_live.columns:
    st.divider()
    st.markdown(f"""
    <div class="broken-alert">
        ⚠️ <strong>{broken_links} link(s)</strong> {"did not load normally at the last check." if CLIENT_MODE else
        "returned a non-200 status code. Check whether they are still live and contact the publisher if needed."}
    </div>
    """, unsafe_allow_html=True)
    want_cols = ["Live Link", "Language", "Domain", "Status code", "Price", "Link to"]
    show_cols = [c for c in want_cols if c in all_live.columns]
    broken_df = all_live[~all_live["Status code"].isin([200])][show_cols]
    st.dataframe(broken_df, width="stretch", hide_index=True, column_config={
        "Live Link": st.column_config.LinkColumn("Live link"), "Link to": st.column_config.LinkColumn("Links to"),
        "Price": st.column_config.NumberColumn("Price", format="€%,.0f"), "Status code": st.column_config.NumberColumn("Status", format="%d")})

if not CLIENT_MODE:      # runs live HTTP checks on a button press: an analyst tool
    render_health_section(raw_links, FLAGS, demo_mode)
TAB["links"].__exit__(None, None, None)


# ── Impact analysis ────────────────────────────────────────────────────────────
# Fragment: choosing another landing page / period only reruns THIS block, not the whole dashboard.
@st.fragment
def render_impact_analysis():
    st.divider()
    ia_title_col, ia_info_col = st.columns([5, 1])
    with ia_title_col:
        st.markdown('<div class="section-title">📈 Impact analysis: ranking over time</div>', unsafe_allow_html=True)

    with st.expander("ℹ️ How does this chart work?", expanded=False):
        st.markdown(f"""
    **Purpose:** Shows whether placed backlinks are actually improving the organic ranking of a landing page.

    **How to read the chart:**
    - The **blue line** shows the average organic position of the landing page over time (source: Ahrefs).
      *Higher on the chart = better ranking (position 1 is at the top).*
    - The **pink dashed lines** mark the exact date a backlink to this page was placed.
    - The **background colours** indicate ranking quality:
      - 🟩 Green = Top 3 (excellent)
      - 🟨 Yellow = Top 10 (good)
      - 🟧 Orange = Position 11–20 (fair)
      - 🟥 Red = Outside top 20 (needs improvement)

    **How it works technically:**
    Ahrefs stores monthly snapshots of all organic rankings.
    This dashboard fetches those historical snapshots and calculates the average position per month.
    You can directly see whether a link placed in month X leads to a ranking improvement in month X+1 or X+2.

    **Note:** Link building typically takes 4–12 weeks before its effect becomes visible in rankings.
    """)

    st.caption("Select a landing page to visualise the ranking impact of placed backlinks.")

    all_lp_options = []
    for lang in LANGUAGES:
        df_lang = live_data.get(lang, pd.DataFrame())
        if not df_lang.empty and "Link to" in df_lang.columns:
            for url in df_lang["Link to"].dropna().unique():
                all_lp_options.append({"url": url, "lang": lang})

    if not all_lp_options:
        st.info("No landing pages available for analysis yet." if CLIENT_MODE else
                "No landing pages available for analysis. Upload the Excel database.")
    else:
        ia_col1, ia_col2, ia_col3 = st.columns([1, 3, 1])
        with ia_col1:
            ia_lang = st.selectbox("Language", LANGUAGES, key="ia_lang")
        with ia_col2:
            lang_lp = [item["url"] for item in all_lp_options if item["lang"] == ia_lang]
            if lang_lp:
                ia_url = st.selectbox("Landing page", lang_lp, key="ia_url")
            else:
                st.info(f"No landing pages available for {ia_lang}.")
                ia_url = None
        with ia_col3:
            ia_months = st.slider("Months back", min_value=3, max_value=12, value=6, key="ia_months")

        if ia_url:
            ia_events = pd.concat(
                [df for df in live_data.values() if not df.empty], ignore_index=True
            ) if any(not d.empty for d in live_data.values()) else pd.DataFrame()

            if not ia_events.empty and "Link to" in ia_events.columns:
                ia_events = ia_events[ia_events["Link to"] == ia_url].copy()
            else:
                ia_events = pd.DataFrame()

            # GSC position history (from uploaded CSV)
            gsc_history = pd.DataFrame()
            if not gsc_df.empty and "Page" in gsc_df.columns and "Avg Position" in gsc_df.columns:
                gsc_page = gsc_df[gsc_df["Page"] == ia_url].copy()
                if "Date" in gsc_df.columns or "date" in gsc_df.columns:
                    date_col    = "Date" if "Date" in gsc_df.columns else "date"
                    gsc_history = gsc_page[[date_col, "Avg Position"]].copy()
                    gsc_history.columns = ["date", "gsc_position"]
                    gsc_history["date"] = pd.to_datetime(gsc_history["date"], errors="coerce")
                    gsc_history = gsc_history.dropna().sort_values("date")

            # Ahrefs position history (monthly snapshots)
            ahrefs_history = pd.DataFrame()
            if demo_mode:
                ahrefs_history = demo_data.demo_position_history(ia_url, ia_months)
            elif ahrefs_client:
                from modules.ahrefs_ui import gated as _gated_ia
                ahrefs_history = _gated_ia(
                    f"ia_load_{ia_months}", f"Ahrefs position history ({ia_months} months)",
                    ahrefs_client.pending_position_history(ia_url, ia_months),
                    lambda: ahrefs_client.get_position_history(ia_url, ia_months))
                if ahrefs_history is None:
                    ahrefs_history = pd.DataFrame()

            has_data = (
                (not ahrefs_history.empty and ahrefs_history["avg_position"].notna().any())
                or not gsc_history.empty
            )

            if not has_data:
                st.warning("No position history for this page yet." if CLIENT_MODE else
                    "No historical position data available. "
                    "Upload a GSC export with the date dimension enabled, or check the Ahrefs API connection."
                )
            else:
                short_label = "/" + "/".join(ia_url.rstrip("/").split("/")[-2:])
                fig_impact  = go.Figure()

                y_max = 60
                if not ahrefs_history.empty and ahrefs_history["avg_position"].notna().any():
                    y_max = max(60, ahrefs_history["avg_position"].dropna().max() * 1.3)
                if not gsc_history.empty:
                    y_max = max(y_max, gsc_history["gsc_position"].max() * 1.3)

                fig_impact.add_hrect(y0=1,  y1=3,     fillcolor="#C8E6C9", opacity=0.25, line_width=0)
                fig_impact.add_hrect(y0=3,  y1=10,    fillcolor="#FFF9C4", opacity=0.25, line_width=0)
                fig_impact.add_hrect(y0=10, y1=20,    fillcolor="#FFE0B2", opacity=0.2,  line_width=0)
                fig_impact.add_hrect(y0=20, y1=y_max, fillcolor="#FFCCCC", opacity=0.15, line_width=0)

                for pos, label, color in [
                    (2, "Top 3",           "#2E7D32"),
                    (6.5, "Top 10",        "#F57F17"),
                    (15, "Top 20",         "#E65100"),
                    (35, "Outside top 20", "#B71C1C"),
                ]:
                    if pos < y_max:
                        fig_impact.add_annotation(
                            x=1, xref="paper", y=pos, text=label,
                            showarrow=False, font=dict(size=9, color=color),
                            xanchor="right", yanchor="middle",
                        )

                if not ahrefs_history.empty and ahrefs_history["avg_position"].notna().any():
                    fig_impact.add_trace(go.Scatter(
                        x=ahrefs_history["date"],
                        y=ahrefs_history["avg_position"],
                        mode="lines+markers",
                        name="Avg. position (Ahrefs)",
                        line=dict(color=NAVY, width=2.5),
                        marker=dict(size=7, color=NAVY, symbol="circle"),
                        hovertemplate="<b>%{x|%b %Y}</b><br>Position: %{y:.1f}<extra></extra>",
                    ))

                if not gsc_history.empty:
                    fig_impact.add_trace(go.Scatter(
                        x=gsc_history["date"],
                        y=gsc_history["gsc_position"],
                        mode="lines+markers",
                        name="Avg. position (GSC)",
                        line=dict(color=TEAL, width=2, dash="dot"),
                        marker=dict(size=6, color=TEAL, symbol="diamond"),
                        hovertemplate="<b>%{x|%d %b %Y}</b><br>GSC position: %{y:.1f}<extra></extra>",
                    ))

                if not ia_events.empty and "LL Date" in ia_events.columns:
                    for _, row in ia_events.dropna(subset=["LL Date"]).iterrows():
                        ll_date = row["LL Date"]
                        da_val  = row.get("DA", None)
                        domain  = row.get("Domain", "")
                        da_txt  = f"DA {int(da_val)}" if pd.notna(da_val) else ""
                        fig_impact.add_vline(
                            x=ll_date.timestamp() * 1000,
                            line=dict(color=PINK, width=1.5, dash="dash"),
                        )
                        fig_impact.add_annotation(
                            x=ll_date, y=0, yref="paper",
                            text=f"🔗 {domain[:20]}<br><span style='color:{PINK}'>{da_txt}</span>",
                            showarrow=True, arrowhead=2, arrowcolor=PINK, arrowsize=0.8,
                            ax=0, ay=-35,
                            font=dict(size=9, color=NAVY),
                            bgcolor="white", bordercolor=PINK, borderwidth=1, borderpad=3,
                        )

                fig_impact.update_layout(
                    **chart_layout(f"Ranking over time: {short_label}", 450),
                    yaxis=dict(
                        title="Average organic position",
                        autorange="reversed",
                        range=[y_max, 0],
                        gridcolor="#E8ECF2",
                        showgrid=True,
                        zeroline=False,
                        ticksuffix="  ",
                    ),
                    xaxis=dict(title="Date", showgrid=False, zeroline=False),
                    legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)),
                    hovermode="x unified",
                    hoverlabel=dict(bgcolor="white", font_size=11, font_family="Roboto"),
                )
                st.plotly_chart(fig_impact, width="stretch")

                s1, s2, s3, s4 = st.columns(4)
                if not ahrefs_history.empty and ahrefs_history["avg_position"].notna().any():
                    valid     = ahrefs_history["avg_position"].dropna()
                    first_pos = valid.iloc[0]
                    last_pos  = valid.iloc[-1]
                    delta_pos = first_pos - last_pos
                    s1.metric("Position start of period", f"{first_pos:.1f}",
                              help="Average organic position at the start of the selected period.")
                    s2.metric("Position now", f"{last_pos:.1f}",
                              delta=f"{'-' if delta_pos < 0 else '+'}{abs(delta_pos):.1f}",
                              delta_color="inverse" if delta_pos < 0 else "normal",
                              help="Current average organic position. Green = improvement vs. start of period.")
                if not ia_events.empty:
                    s3.metric("Backlinks built", len(ia_events),
                              help="Number of backlinks placed to this landing page in the visible period.")
                    avg_link_da = ia_events["DA"].mean() if "DA" in ia_events.columns else None
                    if pd.notna(avg_link_da):
                        s4.metric("Avg. DA of placed links", f"{avg_link_da:.0f}",
                                  help="Average Domain Authority of the domains that placed links. "
                                       "Higher DA = more authority transferred to the landing page.")

                if gsc_history.empty and not CLIENT_MODE:
                    st.caption(
                        "💡 **Tip:** Upload a GSC export with the date dimension enabled for daily position data. "
                        "In Search Console: Performance → enable 'Date' → Export CSV."
                    )


if not CLIENT_MODE:
    TAB["deep"].__enter__()
    render_impact_analysis()
    TAB["deep"].__exit__(None, None, None)


# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="dash-footer">
    Artefact Linkbuilding Dashboard &nbsp;·&nbsp; Template v2.0 &nbsp;·&nbsp;
    Client: <strong>{CLIENT}</strong> &nbsp;·&nbsp;
    {datetime.now().strftime('%d-%m-%Y')}
</div>
""", unsafe_allow_html=True)


_boot.empty()   # loading notice is gone once the whole page is built
