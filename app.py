"""Run: streamlit run app.py"""
import html, re
from pathlib import Path
import pandas as pd, plotly.express as px, streamlit as st
import core

import base64
ASSETS = Path(__file__).parent / "assets"
ICON, FULL = ASSETS / "logo_icon.png", ASSETS / "logo_full.png"
FULL_B64 = base64.b64encode(FULL.read_bytes()).decode() if FULL.exists() else ""
ICON_B64 = base64.b64encode(ICON.read_bytes()).decode() if ICON.exists() else ""
st.set_page_config(page_title="InsightFlow", page_icon=str(ICON) if ICON.exists() else "📊", layout="wide")
PAL = ["#7C3AED", "#EC4899", "#38BDF8", "#34D399", "#F59E0B", "#818CF8", "#FB7185"]
px.defaults.template = "plotly_white"; px.defaults.color_discrete_sequence = PAL
st.markdown(f"<style>{(Path(__file__).parent / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
E = html.escape
NAV = ["🏠  Dashboard", "🔍  Data Explorer", "💬  Ask a Question", "⚠️  Data Quality", "📄  Reports", "⚙️  Settings"]
ROLE_ICO = {"numeric": "🔢", "categorical": "🏷️", "datetime": "🗓️", "text": "📝", "identifier": "🔑"}

# ---------- Login / registration gate (same accounts database as the web app) ----------
import users
if "account" not in st.session_state:
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        if FULL.exists(): st.image(str(FULL), use_container_width=True)
        t_in, t_reg = st.tabs(["Sign in", "Create account"])
        with t_in, st.form("login_form"):
            ident = st.text_input("Username or email"); pw = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary", use_container_width=True):
                u = users.authenticate(ident, pw)
                if u: st.session_state.account = u; st.session_state.user = u["username"]; st.rerun()
                else: st.error("Incorrect username/email or password.")
        with t_reg, st.form("register_form"):
            ru = st.text_input("Username"); re_ = st.text_input("Email")
            rp = st.text_input("Password", type="password", help="At least 8 characters, with letters and numbers.")
            rc = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Create account", type="primary", use_container_width=True):
                errs = users.validate_registration(ru.strip(), re_.strip(), rp, rc)
                u, errs2 = ({}, errs) if errs else users.create_user(ru, re_, rp)
                if errs2: st.error(next(iter(errs2.values())))
                else: st.session_state.account = u; st.session_state.user = u["username"]; st.rerun()
    st.stop()

st.session_state.setdefault("history", [])

def style(fig):
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=45, b=10),
                      font_color="#2A1B6B", legend_title_text="")
    return fig
def head(icon, title, cls="pink"): return f'<div class="chead"><span class="ico {cls}">{icon}</span><span class="ctitle">{E(title)}</span></div>'
def banner(msg): st.markdown(f'<div class="banner"><div><h2>Welcome back, {E(st.session_state.user)}!</h2><p>{E(msg)}</p></div><div class="brain">🧠✨</div></div>', unsafe_allow_html=True)
def sev(pct): return "High" if pct > 5 else "Medium" if pct > 1 else "Low"

@st.cache_data(show_spinner=False)
def prepare(name, data):
    raw = core.load_file(name, data); df, log = core.clean(raw)
    return raw, df, log, core.profile(raw, df)

with st.sidebar:
    st.markdown(f'<img class="logofull" src="data:image/png;base64,{FULL_B64}" alt="InsightFlow">' if FULL_B64 else '<div class="brand"><b class="wm"><span style="color:#7B5BE0">Insight</span><span style="color:#EC8BCB">Flow</span></b></div>', unsafe_allow_html=True)
    page = st.radio("nav", NAV, key="nav", label_visibility="collapsed")
    up = st.file_uploader("Upload dataset", type=list(core.EXTS))
    st.caption(f"Signed in as **{st.session_state.account['username']}**")
    if st.button("Log out", use_container_width=True):
        for k in ("account", "user", "history"): st.session_state.pop(k, None)
        st.rerun()

c1, c2 = st.columns([5, 1.3])
search = c1.text_input("search", placeholder="🔎  Search columns, insights...", label_visibility="collapsed")
c2.markdown(f'<div class="user"><span class="bell">🔔</span> <span class="avatar">👩</span> <b>{E(st.session_state.user)}</b> ⌄</div>', unsafe_allow_html=True)

if not up:
    banner("Upload a CSV, Excel, JSON or TXT file in the sidebar to begin.")
    _, mid, _ = st.columns([1, 1, 1]); mid.image(str(FULL), use_container_width=True) if FULL.exists() else None
    st.markdown('<div class="sfoot" style="position:fixed;bottom:20px">From Data<br>to Insights<br>— Powered by AI</div>', unsafe_allow_html=True); st.stop()
try:
    raw, df, log, prof = prepare(up.name, up.getvalue())
except ValueError as e:
    banner("There was a problem with that file."); st.error(str(e)); st.stop()
roles = prof["roles"]; by = lambda r: [c for c, x in roles.items() if x == r]
num, cat, dt = by("numeric"), by("categorical"), by("datetime")

f = df.copy()
with st.sidebar.expander("🎚️ Filters"):
    for c in cat[:4]:
        sel = st.multiselect(c, sorted(df[c].astype(str).unique()))
        if sel: f = f[f[c].astype(str).isin(sel)]
    for c in dt[:1]:
        if df[c].notna().any():
            mn, mx = df[c].min().date(), df[c].max().date()
            rng = st.date_input(c, (mn, mx), min_value=mn, max_value=mx)
            if isinstance(rng, (tuple, list)) and len(rng) == 2:
                f = f[(f[c] >= pd.Timestamp(rng[0])) & (f[c] < pd.Timestamp(rng[1]) + pd.Timedelta(days=1))]
st.sidebar.markdown('<div class="sfoot">From Data<br>to Insights<br>— Powered by AI</div>', unsafe_allow_html=True)
if f.empty:
    st.warning("No rows match the current filters. Clear a filter or widen the date range."); st.stop()
fprof = {**prof, "outliers": core.profile(f, f)["outliers"]}

def anomalies():
    it = [(f"Outliers in {c}", f"{k} values ({k/len(f)*100:.1f}% of rows)", sev(k / len(f) * 100)) for c, k in fprof["outliers"].items() if k]
    it += [(f"Missing values in {c}", f"{k} missing ({k/len(raw)*100:.1f}%)", sev(k / len(raw) * 100)) for c in raw.columns if (k := int(raw[c].isna().sum()))]
    return sorted(it, key=lambda x: ["High", "Medium", "Low"].index(x[2]))

# ================= Dashboard =================
if page == NAV[0]:
    banner("Your dataset is ready. Explore, ask questions and discover insights from your data.")
    kp = [("📄", "Total Rows", f"{len(raw):,}", f"{len(f):,} in current view", "pink"),
          ("🧬", "Columns", str(raw.shape[1]), ", ".join(f"{v} {k}" for k, v in prof["counts"].items()), "lilac"),
          ("🔗", "Missing Values", f"{prof['missing']:,}", "filled during cleaning", "rose"),
          ("⚠️", "Duplicate Rows", f"{prof['duplicates']:,}", "removed during cleaning", "peach"),
          ("🛡️", "Outliers", f"{sum(fprof['outliers'].values()):,}", "IQR rule, current view", "blue")]
    for col, (i, l, v, s, cl) in zip(st.columns(5), kp):
        col.markdown(f'<div class="kpi {cl}"><span class="ico {cl}">{i}</span><div class="kl">{l}</div><div class="kv">{v}</div><div class="ks">{E(s)}</div></div>', unsafe_allow_html=True)
    st.write("")
    left, right = st.columns([2.1, 1])
    with left, st.container(border=True):
        st.markdown(head("🕸️", "Dashboard Explorer", "lilac") + '<div class="csub">Choose what to measure and how to break it down.</div>', unsafe_allow_html=True)
        a, b, c_, d_ = st.columns(4)
        m = a.selectbox("Measure", num or ["(row count)"], index=num.index(core.main_measure(num)) if num else 0); g = b.selectbox("Break down by", cat + dt or ["(none)"])
        ag = c_.selectbox("Aggregation", ["sum", "mean", "count"]); ch = d_.selectbox("Chart", ["Bar", "Pie", "Line"])
        if g in cat + dt:
            isd = g in dt
            plan = dict(op="trend" if isd else ("share" if ch == "Pie" else "compare"), metric=m if num else None,
                        dimension=None if isd else g, time=g if isd else None, agg=ag, grain=None, n=10, asc=False, cm=[], q="")
            r = core.execute(f, fprof, plan)
            if r["fig"] is not None:
                if isd and ch == "Bar": r["fig"] = px.bar(r["table"], x=g, y=r["table"].columns[1], title=f"{m} by {g}")
                st.plotly_chart(style(r["fig"]), use_container_width=True, key="explorer")
            st.markdown(f'<div class="insight">💡 {E(r["text"])}</div>', unsafe_allow_html=True)
        else: st.info("This dataset has no categorical or date column to break down by.")
    with right, st.container(border=True):
        t0, t1, t2 = st.tabs(["Column Details", "Statistics", "Insights"])
        opts = [c for c in df.columns if search.lower() in c.lower()] or list(df.columns)
        with t0:
            col = st.selectbox("Column", opts, index=opts.index(core.main_measure(num)) if core.main_measure(num) in opts else 0, label_visibility="collapsed"); s = f[col]
            comp = 100 - s.isna().mean() * 100
            st.markdown(f'<div class="chead"><span class="ico lilac">{ROLE_ICO[roles[col]]}</span><span class="ctitle">{E(col)}</span><span class="chip">{roles[col].title()}</span></div>'
                        f'<div class="row"><span>Completeness</span><b>{comp:.1f}%</b></div><div class="bar"><i style="width:{comp:.0f}%"></i></div>'
                        f'<div class="row"><span>Unique values</span><b>{s.nunique():,}</b></div><div class="row"><span>Missing (raw)</span><b>{int(raw[col].isna().sum()):,}</b></div>'
                        '<div class="csub" style="margin-top:10px">Top values</div>' +
                        "".join(f'<div class="rel"><span>{E(str(k))}</span><b>{v:,}</b></div>' for k, v in s.astype(str).value_counts().head(4).items()), unsafe_allow_html=True)
        with t1:
            st.dataframe(s.describe().to_frame("value").astype(str), use_container_width=True)
        with t2:
            st.markdown("".join(f'<div class="rel">{E(x)}</div>' for x in core.auto_insights(f, fprof)[:5]), unsafe_allow_html=True)
        st.button("View Full Details →", type="primary", use_container_width=True, on_click=lambda: st.session_state.update(nav=NAV[1]))
    st.write("")
    b1, b2, b3 = st.columns(3)
    hist = st.session_state["history"][-4:][::-1]
    b1.markdown('<div class="card">' + head("💬", "Recent Questions") + ("".join(f'<div class="act"><span class="ico">❓</span><span class="t"><b>{E(q)}</b><br><span class="sm">{E(r["text"][:70])}</span></span></div>' for q, r in hist)
                or '<div class="sm">No questions yet. Try “Ask a Question”.</div>') + "</div>", unsafe_allow_html=True)
    b2.markdown('<div class="card">' + head("⚠️", "Detected Anomalies", "rose") + ("".join(f'<div class="alert"><b>{E(t)}</b><span class="tag {s.lower()}">{s}</span><div class="sm">{E(d)}</div></div>' for t, d, s in anomalies()[:3])
                or '<div class="sm">No anomalies detected.</div>') + "</div>", unsafe_allow_html=True)
    ic = lambda x: "🗓️" if "date" in x else "🧹" if "Removed" in x else "🩹" if "Filled" in x else "🔢" if "numeric" in x else "✅"
    b3.markdown('<div class="card">' + head("🕘", "Recent Activity", "blue") + "".join(f'<div class="act"><span class="ico">{ic(x)}</span><span class="t">{E(x)}</span><span class="w">on upload</span></div>' for x in log[:5]) + "</div>", unsafe_allow_html=True)

# ================= Data Explorer =================
elif page == NAV[1]:
    banner(f"{up.name} · {raw.shape[0]:,} rows × {raw.shape[1]} columns. {prof['summary']}")
    cols = [c for c in df.columns if search.lower() in c.lower()] or list(df.columns)
    with st.container(border=True):
        st.markdown(head("🧬", "Column Profile", "lilac"), unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({"role": pd.Series(roles), "dtype": df.dtypes.astype(str), "missing (raw)": raw.isna().sum(), "unique": df.nunique()}).loc[cols], use_container_width=True)
    with st.container(border=True):
        st.markdown(head("📄", "Data Preview (filtered)"), unsafe_allow_html=True)
        st.dataframe(f[cols].head(200), use_container_width=True)
        st.dataframe(f.describe(include="all").T, use_container_width=True)

# ================= Ask =================
elif page == NAV[2]:
    banner("Ask anything about your data in plain English. Answers are calculated from your dataset.")
    sugg = ([f"Show {core.main_measure(num)} by month"] if num and dt else []) + (
        [f"Which {cat[0]} has the highest {core.main_measure(num)}?", f"Compare {core.main_measure(num)} by {cat[0]}"] if num and cat else []) + (
        ["Is there a relationship between the numeric columns?"] if len(num) > 1 else []) + ["Find unusual values in this dataset"]
    clicked = None
    for i, (col_, s_) in enumerate(zip(st.columns(min(4, len(sugg))), sugg[:4])):
        if col_.button(s_, key=f"sg{i}", use_container_width=True): clicked = s_
    q = st.chat_input("e.g. Show monthly sales and which product has the highest revenue") or clicked
    if q:
        for part in [s for s in re.split(r"[?.]\s+|\s+and\s+(?=(?:show|which|what|how|find|compare|give|list|tell|who|is|are|create|generate|plot|draw)\b)", q, flags=re.I) if s and s.strip()]:
            plan = core.parse_llm(part, fprof) or core.parse_rules(part, fprof)
            st.session_state["history"].append((part.strip(), core.execute(f, fprof, plan)))
    if not st.session_state["history"]:
        st.info("No questions yet. Pick a suggestion above or type your own below.")
    for i, (qq, r) in enumerate(st.session_state["history"]):
        with st.chat_message("user"): st.write(qq)
        with st.chat_message("assistant"):
            st.write(r["text"])
            if r["fig"] is not None: st.plotly_chart(style(r["fig"]), use_container_width=True, key=f"chat{i}")
            if r["table"] is not None:
                with st.expander("Show table"): st.dataframe(r["table"], use_container_width=True)
            with st.expander("How I understood this"):
                p = r["plan"]; st.write(f"Operation: **{p['op']}** · Measure: **{p['metric']}** · Group by: **{p['dimension'] or p['time']}** · Aggregation: **{p['agg']}**")
    if st.session_state["history"] and st.button("Clear conversation"):
        st.session_state["history"] = []; st.rerun()

# ================= Quality =================
elif page == NAV[3]:
    banner("Missing values, duplicates, outliers and the cleaning steps applied.")
    a, b = st.columns(2)
    with a, st.container(border=True):
        st.markdown(head("⚠️", "Detected Anomalies", "rose"), unsafe_allow_html=True)
        st.markdown("".join(f'<div class="alert"><b>{E(t)}</b><span class="tag {s.lower()}">{s}</span><div class="sm">{E(d)}</div></div>' for t, d, s in anomalies()) or "No anomalies detected.", unsafe_allow_html=True)
    with b, st.container(border=True):
        st.markdown(head("🩹", "Cleaning Performed", "blue"), unsafe_allow_html=True)
        st.markdown("".join(f'<div class="rel">{E(x)}</div>' for x in log), unsafe_allow_html=True)
    ms = raw.isna().sum(); ms = ms[ms > 0]
    if len(ms): st.plotly_chart(style(px.bar(ms.reset_index(), x="index", y=0, title="Missing values by column")), use_container_width=True, key="miss")

# ================= Reports =================
elif page == NAV[4]:
    banner("Download a full analysis report including your questions and charts.")
    rep = core.report_html(up.name, raw, df, prof, log, st.session_state["history"])
    st.download_button("⬇ Download HTML report", rep, "report.html", "text/html", type="primary")
    st.components.v1.html(rep, height=650, scrolling=True)

# ================= Settings =================
else:
    banner("Personalise the app.")
    with st.container(border=True):
        st.session_state.user = st.text_input("Your name", st.session_state.user)
        import os
        st.write("LLM query understanding:", "✅ enabled" if os.getenv("ANTHROPIC_API_KEY") else "⚪ off (rule-based parser in use)")
        st.write(f"Upload limit: {core.MAX_MB} MB · Formats: {', '.join(sorted(core.EXTS))}")