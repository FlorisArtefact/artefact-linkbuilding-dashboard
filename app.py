import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import os
from datetime import datetime
from dotenv import load_dotenv

from modules.data_loader import (
    load_live_links,
    load_opportunities,
    apply_filters,
    get_landing_page_summary,
)
from modules.ahrefs_client import AhrefsClient
from modules.gsc_client import load_gsc_csv, merge_gsc_into_table
from modules.sheets_loader import (
    load_live_links_sheets,
    load_opportunities_sheets,
    sheets_available,
)

load_dotenv()

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="Linkbuilding Dashboard | Artefact",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Brand colors ───────────────────────────────────────────────────────────────
NAVY   = "#1B2D5B"
PINK   = "#E5007D"
TEAL   = "#00B4C8"
LIGHT  = "#F0F4F8"
MID    = "#8B9BB4"
WHITE  = "#FFFFFF"
CHART_COLORS = [PINK, NAVY, TEAL, "#FF7043", "#7B1FA2"]

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
html, body, [class*="css"] {{ font-family: 'Roboto', sans-serif; }}

#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }}

.dash-header {{
    background: linear-gradient(120deg, {NAVY} 0%, #2A4080 55%, #8B1060 100%);
    padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem;
    display: flex; justify-content: space-between; align-items: center;
}}
.dash-header h1 {{ color: white; margin: 0; font-size: 1.7rem; font-weight: 700; }}
.dash-header .sub {{ color: rgba(255,255,255,0.68); font-size: 0.87rem; margin-top: 0.3rem; }}
.artefact-pill {{
    background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.28);
    color: white; padding: 0.35rem 1.1rem; border-radius: 20px;
    font-size: 0.82rem; font-weight: 600; letter-spacing: 0.5px;
}}

.section-title {{
    color: {NAVY}; font-weight: 700; font-size: 1rem;
    margin: 1.2rem 0 0.8rem; padding-bottom: 0.4rem;
    border-bottom: 2px solid {PINK}; display: inline-block;
}}

.lang-card {{
    background: {LIGHT}; border-radius: 8px; padding: 0.85rem 1rem;
    margin-bottom: 0.65rem; border-left: 3px solid {PINK};
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
[data-testid="stMetric"] {{ border-left: 3px solid {PINK}; padding-left: 0.8rem; }}
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
@st.cache_data(show_spinner=False)
def load_config() -> dict:
    if os.path.exists("config.json"):
        with open("config.json") as f:
            return json.load(f)
    return {"client_name": "Client", "languages": ["NL", "EN", "DE"], "currency": "EUR"}

config    = load_config()
LANGUAGES = config.get("languages", ["NL", "EN", "DE"])
CLIENT    = config.get("client_name", "Client")


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='font-size:1.3rem;font-weight:700;color:{NAVY};'>Artefact</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:0.75rem;color:{MID};margin-bottom:1rem;'>Linkbuilding Dashboard</div>", unsafe_allow_html=True)
    st.divider()

    # — Data source
    st.markdown("**📂 Data source**")
    use_sheets = sheets_available(config)

    if use_sheets:
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

    st.divider()

    # — Filters
    st.markdown("**🔍 Filters**")
    current_year = datetime.now().year
    year_opts = list(range(current_year - 1, current_year + 2))
    selected_year = st.selectbox("Year", year_opts, index=year_opts.index(current_year))
    selected_quarter = st.selectbox("Quarter", ["All", "Q1", "Q2", "Q3", "Q4"])
    campaign_filter = st.text_input("Campaign", placeholder="e.g. Paid linkbuilding")

    st.divider()

    # — APIs
    st.markdown("**🔌 API connections**")
    ahrefs_key = os.getenv("AHREFS_API_KEY", "")
    if not ahrefs_key:
        ahrefs_key = st.text_input("Ahrefs API key", type="password", placeholder="Bearer token")
        if ahrefs_key:
            os.environ["AHREFS_API_KEY"] = ahrefs_key

    ahrefs_ok = bool(ahrefs_key)
    st.markdown(f"{'🟢' if ahrefs_ok else '🔴'} Ahrefs API {'(connected)' if ahrefs_ok else '(no key)'}")

    # GSC CSV upload
    st.markdown("**📊 Search Console data**")
    gsc_csv = st.file_uploader(
        "Upload GSC export (Pages CSV)",
        type=["csv"],
        help="In GSC: Performance → Pages → Export as CSV",
        label_visibility="collapsed",
    )
    gsc_df = load_gsc_csv(gsc_csv) if gsc_csv else pd.DataFrame()
    if not gsc_df.empty:
        st.success(f"GSC data loaded: {len(gsc_df)} pages ✓")
    else:
        st.caption("🔴 GSC (no data — upload CSV or connect API)")
        with st.expander("How to connect GSC?"):
            st.info(
                "Export from Google Search Console:\n"
                "Performance → Pages → Export → Download CSV\n\n"
                "Or connect the API (see README for free setup instructions)."
            )

    st.divider()

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


# ── Guard: no data ─────────────────────────────────────────────────────────────
if not use_sheets and excel_source is None:
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


# ── Load & filter data ─────────────────────────────────────────────────────────
q_filter    = None if selected_quarter == "All" else selected_quarter
camp_filter = campaign_filter.strip() or None

# Resolve credentials path relative to project root
_creds_file = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    config.get("google_sheets", {}).get("credentials_file", "")
)
_sheet_id = config.get("google_sheets", {}).get("spreadsheet_id", "")

live_data, opp_data = {}, {}
for lang in LANGUAGES:
    if use_sheets:
        raw = load_live_links_sheets(_creds_file, _sheet_id, lang)
    else:
        raw = load_live_links(excel_source, lang)
    live_data[lang] = apply_filters(raw, year=selected_year, quarter=q_filter, campaign=camp_filter)

    if use_sheets:
        opp_data[lang] = load_opportunities_sheets(_creds_file, _sheet_id, lang)
    else:
        opp_data[lang] = load_opportunities(excel_source, lang)

all_live = pd.concat(live_data.values(), ignore_index=True) if any(not d.empty for d in live_data.values()) else pd.DataFrame()


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
data_badge    = "🟢 Live · Google Sheets" if use_sheets else "📁 Excel"
st.markdown(f"""
<div class="dash-header">
    <div>
        <h1>🔗 Linkbuilding Dashboard</h1>
        <div class="sub">{CLIENT} &nbsp;·&nbsp; {selected_year} &nbsp;·&nbsp; {quarter_label} &nbsp;·&nbsp; {data_badge}</div>
    </div>
    <div class="artefact-pill">Artefact</div>
</div>
""", unsafe_allow_html=True)


# ── Global KPIs ────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Live links placed", total_links,
    help="Total number of live backlinks placed in the selected period, across all languages."
)
c2.metric(
    "Total investment", fmt_eur(total_cost),
    help="Sum of all costs for placed backlinks in the filtered period."
)
c3.metric(
    "Avg. Domain Authority", f"{avg_da:.0f}" if pd.notna(avg_da) and avg_da > 0 else "—",
    help="Domain Authority (DA) is a Moz score (0–100) measuring a domain's authority. "
         "A higher DA means more authority and therefore more SEO value for the backlink. "
         "This is the average DA of all domains linking to your pages."
)
c4.metric(
    "Dofollow %", f"{dofollow_pct:.0f}%",
    help="Dofollow links pass 'link juice' to the target page and are directly valuable for SEO. "
         "Nofollow links do not. A higher dofollow percentage is better for organic rankings."
)
c5.metric(
    "Links to check", broken_links,
    delta=f"{broken_links} ⚠️" if broken_links else "All good", delta_color="inverse",
    help="Number of backlinks returning a non-200 HTTP status code (e.g. 403 or 404). "
         "This means the link may have been removed or blocked. "
         "Contact the publisher to resolve this."
)


# ── Overview: links per language + costs ───────────────────────────────────────
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
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No links found for the selected filters.")

with col_cards:
    for lang, cost in lang_costs.items():
        cnt   = lang_counts.get(lang, 0)
        avg_c = cost / cnt if cnt > 0 else 0
        flag  = {"NL": "🇳🇱", "EN": "🇬🇧", "DE": "🇩🇪"}.get(lang, "🌐")
        st.markdown(f"""
        <div class="lang-card">
            <div class="lang-name">{flag} {lang}</div>
            <div class="lang-cost">{fmt_eur(cost)}</div>
            <div class="lang-sub">{cnt} links &nbsp;·&nbsp; avg {fmt_eur(avg_c)}/link</div>
        </div>
        """, unsafe_allow_html=True)


# ── Per-language tabs ──────────────────────────────────────────────────────────
flags      = {"NL": "🇳🇱", "EN": "🇬🇧", "DE": "🇩🇪"}
tab_labels = [f"{flags.get(l, '')} {l} ({lang_counts.get(l, 0)})" for l in LANGUAGES]
tabs       = st.tabs(tab_labels)

ahrefs_client = AhrefsClient(ahrefs_key) if ahrefs_key else None

for i, lang in enumerate(LANGUAGES):
    with tabs[i]:
        df = live_data.get(lang, pd.DataFrame())

        if df.empty:
            st.info(f"No live links found for {lang} with the current filters.")
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
                st.plotly_chart(fig_t, use_container_width=True)

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
                st.plotly_chart(fig_da, use_container_width=True)

        # Charts row 2
        ch3, ch4 = st.columns(2)

        with ch3:
            if "Link Type" in df.columns:
                lt_counts = df["Link Type"].value_counts().reset_index()
                lt_counts.columns = ["Type", "Count"]
                fig_lt = px.pie(
                    lt_counts, names="Type", values="Count",
                    title=f"Link types — {lang}",
                    color_discrete_sequence=[PINK, NAVY, TEAL],
                    hole=0.55,
                )
                fig_lt.update_traces(textfont_size=11)
                fig_lt.update_layout(
                    **chart_layout(f"Link types — {lang}"),
                    showlegend=True,
                )
                st.plotly_chart(fig_lt, use_container_width=True)

        with ch4:
            if "Link to" in df.columns and "Price" in df.columns:
                cost_per_lp = (
                    df.groupby("Link to")["Price"]
                    .sum()
                    .sort_values(ascending=True)
                    .tail(8)
                    .reset_index()
                )
                cost_per_lp["short"] = cost_per_lp["Link to"].str.split("/").str[-2:].str.join("/")
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
                st.plotly_chart(fig_lp, use_container_width=True)

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
| **GSC Position** | Average Google Search position according to Search Console data (upload CSV to enable) |

> **Tip:** Low avg. DA + poor GSC position = more high-quality links needed. High DA + strong position = campaign is working.
""")

        lp_table = get_landing_page_summary(df)

        if not gsc_df.empty:
            lp_table = merge_gsc_into_table(lp_table, gsc_df)

        if ahrefs_client and not lp_table.empty:
            with st.spinner("Fetching Ahrefs data..."):
                urls        = lp_table["Landing Page"].dropna().tolist()
                ahrefs_data = ahrefs_client.enrich_landing_pages(urls)
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
        if "Ahrefs Avg. Pos." in lp_table.columns:
            col_cfg["Ahrefs Avg. Pos."] = st.column_config.NumberColumn("Ahrefs Avg. Pos.", format="%.1f")
        if "Ahrefs Traffic" in lp_table.columns:
            col_cfg["Ahrefs Traffic"] = st.column_config.NumberColumn("Ahrefs Traffic", format="%d")

        st.dataframe(lp_table, use_container_width=True, hide_index=True, column_config=col_cfg)

        with st.expander(f"📋 All live links — {lang} ({len(df)})"):
            show_cols = ["LL Date", "Live Link", "Domain", "DA", "Link Type", "Status code",
                         "Link to", "Anchor text", "Price", "Target campaign"]
            available = [c for c in show_cols if c in df.columns]
            st.dataframe(
                df[available].sort_values("LL Date", ascending=False) if "LL Date" in df.columns else df[available],
                use_container_width=True, hide_index=True,
            )

        opp = opp_data.get(lang, pd.DataFrame())
        if not opp.empty:
            with st.expander(f"🎯 Opportunities pipeline — {lang} ({len(opp)})"):
                approved    = opp[opp["Approved?"].notna()].copy() if "Approved?" in opp.columns else pd.DataFrame()
                st.caption(f"Total in pipeline: **{len(opp)}** &nbsp;·&nbsp; Approved: **{len(approved)}**")
                opp_cols    = ["Domain", "DR", "Topic", "Price", "Proposed month", "Approved?", "Link to", "Anchor"]
                avail_opp   = [c for c in opp_cols if c in opp.columns]
                st.dataframe(opp[avail_opp], use_container_width=True, hide_index=True)


# ── Broken links section ───────────────────────────────────────────────────────
if broken_links > 0 and "Status code" in all_live.columns:
    st.divider()
    st.markdown(f"""
    <div class="broken-alert">
        ⚠️ <strong>{broken_links} link(s)</strong> returned a non-200 status code.
        Check whether they are still live and contact the publisher if needed.
    </div>
    """, unsafe_allow_html=True)
    want_cols = ["Live Link", "Language", "Domain", "Status code", "Price", "Link to"]
    show_cols = [c for c in want_cols if c in all_live.columns]
    broken_df = all_live[~all_live["Status code"].isin([200])][show_cols]
    st.dataframe(broken_df, use_container_width=True, hide_index=True)


# ── Impact analysis ────────────────────────────────────────────────────────────
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
    st.info("No landing pages available for analysis. Upload the Excel database.")
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
        if ahrefs_client:
            cache_key = f"pos_hist_{ia_url}_{ia_months}"
            if cache_key not in st.session_state:
                short = ia_url.rstrip("/").split("/")[-1] or ia_url
                with st.spinner(f"Ahrefs: fetching {ia_months} monthly snapshots for {short}..."):
                    st.session_state[cache_key] = ahrefs_client.get_position_history(ia_url, ia_months)
            ahrefs_history = st.session_state[cache_key]

        has_data = (
            (not ahrefs_history.empty and ahrefs_history["avg_position"].notna().any())
            or not gsc_history.empty
        )

        if not has_data:
            st.warning(
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
            st.plotly_chart(fig_impact, use_container_width=True)

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

            if ahrefs_client:
                if st.button("🔄 Refresh (clears cache)", key="refresh_impact"):
                    cache_key = f"pos_hist_{ia_url}_{ia_months}"
                    if cache_key in st.session_state:
                        del st.session_state[cache_key]
                    st.rerun()

            if gsc_history.empty:
                st.caption(
                    "💡 **Tip:** Upload a GSC export with the date dimension enabled for daily position data. "
                    "In Search Console: Performance → enable 'Date' → Export CSV."
                )


# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="dash-footer">
    Artefact Linkbuilding Dashboard &nbsp;·&nbsp; Template v1.0 &nbsp;·&nbsp;
    Client: <strong>{CLIENT}</strong> &nbsp;·&nbsp;
    {datetime.now().strftime('%d-%m-%Y')}
</div>
""", unsafe_allow_html=True)
