

"""Core engine: load -> clean -> profile -> parse question -> safe execute -> insights."""
import io, json, os, re, warnings
import numpy as np, pandas as pd, plotly.express as px
 
MAX_MB = 20
EXTS = {"csv", "xlsx", "xls", "json", "txt"}
OPS = {"total", "trend", "top", "compare", "share", "correlation", "outliers",
       "distribution", "summary", "dashboard", "report"}
SYN = {"revenue": ["sales", "revenue", "amount", "total", "income"],
       "sales": ["sales", "revenue", "amount"], "profit": ["profit", "margin"],
       "score": ["score", "marks", "grade", "gpa"], "salary": ["salary", "pay", "wage"]}
 
def _to_date(s):
    """Parse dates trying day-first and month-first; keep whichever parses more values."""
    best = None
    for dayfirst in (True, False):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)
        d = d.where((d.dt.year >= 1900) & (d.dt.year <= 2100))
        if best is None or d.notna().mean() > best.notna().mean(): best = d
    return best

def _auto_grain(s):
    span = (s.max() - s.min()).days
    return "D" if span <= 92 else "M" if span <= 1100 else "Y"

def main_measure(num):
    return next((c for c in num if re.search(r"sales|revenue|amount|profit|price|salary|score|total|cost|income|marks|bytes|value", c.lower())), num[0] if num else None)

# ---------- load / validate ----------
def load_file(name, data):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in EXTS:
        raise ValueError(f"Unsupported file type '.{ext}'. Supported: {', '.join(sorted(EXTS))}.")
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_MB * 1024 * 1024:
        raise ValueError(f"File exceeds the {MAX_MB} MB limit.")
    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(data), encoding_errors="replace")
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(data))
        elif ext == "json":
            obj = json.loads(data.decode("utf-8", "replace"))
            if isinstance(obj, dict):
                obj = next((v for v in obj.values() if isinstance(v, list)), [obj])
            df = pd.json_normalize(obj)
        else:  # txt: sniff delimiter
            df = pd.read_csv(io.BytesIO(data), sep=None, engine="python", encoding_errors="replace")
    except Exception as e:
        raise ValueError(f"Could not parse the {ext.upper()} file: {e}")
    if df.empty or df.shape[1] < 1:
        raise ValueError("No tabular data could be extracted from the file.")
    return df
 
# ---------- clean ----------
def clean(df):
    log, df = [], df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    n0 = len(df); df = df.dropna(how="all")
    if len(df) < n0: log.append(f"Removed {n0-len(df)} fully empty rows.")
    d = int(df.duplicated().sum())
    if d: df = df.drop_duplicates(); log.append(f"Removed {d} duplicate rows.")
    for c in df.select_dtypes("object"):
        df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v).replace("", np.nan)
        s = df[c].dropna().astype(str)
        if s.empty: continue
        num = pd.to_numeric(s.str.replace(r"[,$₹€£%\s]", "", regex=True), errors="coerce")
        if num.notna().mean() >= .9:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(r"[,$₹€£%\s]", "", regex=True), errors="coerce")
            log.append(f"Converted '{c}' to numeric."); continue
        if s.str.contains(r"\d").mean() > .9:
            dt = _to_date(s)
            if dt.notna().mean() >= .9:
                df[c] = _to_date(df[c])
                log.append(f"Converted '{c}' to date.")
    for c in df.columns:
        k = int(df[c].isna().sum())
        if not k: continue
        if pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].fillna(df[c].median()); log.append(f"Filled {k} missing in '{c}' with median.")
        elif not pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].fillna("Unknown"); log.append(f"Filled {k} missing in '{c}' with 'Unknown'.")
    return df.reset_index(drop=True), log or ["No cleaning was required."]
 
# ---------- profile ----------
def profile(raw, df):
    roles, out = {}, {}
    for c in df.columns:
        s, u = df[c], df[c].nunique()
        if pd.api.types.is_datetime64_any_dtype(s): r = "datetime"
        elif pd.api.types.is_numeric_dtype(s):
            r = "identifier" if ((s.dropna() % 1 == 0).all() and u > .95 * len(df) and (s.max() - s.min() + 1) <= 1.15 * u) or re.search(r"(^|[_ ])(id|code|key|no|number|index)$|^id[_ ]", c.lower()) else "numeric"
        elif u <= max(20, .05 * len(df)): r = "categorical"
        else: r = "identifier" if u > .95 * len(df) else "text"
        roles[c] = r
        if r == "numeric":
            q1, q3 = s.quantile([.25, .75]); i = q3 - q1
            out[c] = int(((s < q1 - 1.5 * i) | (s > q3 + 1.5 * i)).sum())
    cnt = pd.Series(roles).value_counts().to_dict()
    summary = (f"Dataset contains {len(df):,} records and {df.shape[1]} columns: "
               + ", ".join(f"{v} {k}" for k, v in cnt.items()) + " columns.")
    return {"roles": roles, "outliers": out, "summary": summary, "counts": cnt,
            "missing": int(raw.isna().sum().sum()), "duplicates": int(raw.duplicated().sum())}
 
# ---------- question -> plan (rules, or optional LLM) ----------
def _match(q, cols):
    best, score = None, 0
    for c in cols:
        name = c.lower().replace("_", " ")
        sc = 3 if name in q else sum(2 for t in re.split(r"\W+", name) if t and t in q)
        sc += sum(1 for k, v in SYN.items() if k in q and any(w in name for w in v))
        if sc > score: best, score = c, sc
    return best
 
def parse_rules(q, prof):
    ql, roles = q.lower(), prof["roles"]
    by = lambda r: [c for c, x in roles.items() if x == r]
    num, cat, dt = by("numeric"), by("categorical"), by("datetime")
    m = _match(ql, num) or main_measure(num)
    d = _match(ql, cat) or (cat[0] if cat else None)
    t = _match(ql, dt) or (dt[0] if dt else None)
    grain = "D" if re.search(r"hour|daily|per day|by day|each day|\bday\b", ql) else "W" if "week" in ql else "Q" if "quarter" in ql else "Y" if re.search(r"year|annual", ql) else "M" if "month" in ql else None
    agg = "mean" if re.search(r"average|mean|avg", ql) else "sum"
    if re.search(r"count|how many|number of", ql): agg = "count"
    elif not _match(ql, num) and re.search(r"event|record|row|entr|order|transaction|incident|log|attempt|case|student|employee|customer|user|patient|visit|ticket|request", ql): agg = "count"
    n = int(x.group(1)) if (x := re.search(r"top\s+(\d+)", ql)) else 10
    asc = bool(re.search(r"lowest|least|worst|bottom", ql))
    if re.search(r"outlier|unusual|anomal", ql): op = "outliers"
    elif re.search(r"relationship|correlat", ql): op = "correlation"
    elif "dashboard" in ql: op = "dashboard"
    elif "report" in ql: op = "report"
    elif re.search(r"summar|overview", ql): op = "summary"
    elif t and re.search(r"trend|month|over time|daily|yearly|quarter|weekly|hourly|per (day|week|year|hour)|by (day|week|year|date|hour)|each (day|week|year)|timeline|\b(day|week|year)\b", ql): op = "trend"
    elif re.search(r"share|proportion|percent|contribution|pie", ql): op = "share"
    elif re.search(r"distribut|histogram", ql): op = "distribution"
    elif re.search(r"highest|top|best|lowest|worst|most|least|which", ql): op = "top"
    elif re.search(r"compare|comparison|\bby\b|per |each", ql): op = "compare"
    elif re.search(r"total|average|mean|what is|sum|count|how many|number of", ql): op = "total"
    else: op = "summary"
    cm = [c for c in num if any(len(w) > 2 and w in ql for w in re.split(r"\W+", c.lower().replace("_", " ")))]
    return dict(op=op, metric=m, dimension=d, time=t, agg=agg, grain=grain, n=n, asc=asc, cm=cm, q=ql)
 
def parse_llm(q, prof):
    """Optional: LLM returns a JSON plan (never code). Falls back to rules if unavailable/invalid."""
    if not os.getenv("ANTHROPIC_API_KEY"): return None
    try:
        import anthropic
        msg = anthropic.Anthropic().messages.create(model="claude-sonnet-4-6", max_tokens=300, messages=[{"role": "user", "content":
            f"Columns and roles: {json.dumps(prof['roles'])}\nQuestion: {q}\nReturn ONLY JSON with keys op (one of {sorted(OPS)}), "
            "metric, dimension, time (column names or null), agg (sum|mean|count), grain (M|Y|Q|W|D), n (int), asc (bool)."}])
        p = json.loads(re.sub(r"```(json)?", "", msg.content[0].text).strip())
        ok = p.get("op") in OPS and p.get("agg") in {"sum", "mean", "count"} and p.get("grain") in {"M", "Y", "Q", "W", "D"}
        cols_ok = all(p.get(k) in (None, *prof["roles"]) for k in ("metric", "dimension", "time"))
        return {**parse_rules(q, prof), **p} if ok and cols_ok else None
    except Exception:
        return None
 
# ---------- safe execution (whitelisted pandas ops only; no eval/exec) ----------
def execute(df, prof, p):
    op, m, d, t, agg = p["op"], p["metric"], p["dimension"], p["time"], p["agg"]
    r = dict(plan=p, fig=None, table=None, text="")
    if len(df) == 0:
        r["text"] = "No data matches the current filters."; return r
    if op == "total":
        if agg == "count" or not m: r["text"] = f"There are {len(df):,} records."
        else: v = getattr(df[m], agg)(); r["text"] = f"The {'average' if agg=='mean' else 'total'} {m} is {v:,.2f}."
    elif op == "trend" and t:
        dd = df.dropna(subset=[t])
        if dd.empty: r["text"] = f"Column '{t}' has no valid dates, so a trend cannot be drawn."; return r
        key = dd[t].dt.to_period(p["grain"] or _auto_grain(dd[t])).astype(str)
        mc = m if (m and agg != "count") else "count"
        g = (dd.groupby(key)[m].agg(agg) if mc != "count" else dd.groupby(key).size()).reset_index()
        g.columns = [t, mc]; r["table"] = g
        r["fig"] = px.line(g, x=t, y=mc, markers=True, title=f"{mc} by {t}")
        hi, lo = g.loc[g[mc].idxmax()], g.loc[g[mc].idxmin()]
        ch = (g[mc].iloc[-1] - g[mc].iloc[0]) / g[mc].iloc[0] * 100 if len(g) > 1 and g[mc].iloc[0] else 0
        r["text"] = f"{mc} peaked in {hi[t]} ({hi[mc]:,.2f}) and was lowest in {lo[t]} ({lo[mc]:,.2f}). From first to last period it changed by {ch:+.1f}%."
    elif op in ("top", "compare", "share") and d:
        mc = m if (m and agg != "count") else "count"
        g = (df.groupby(d)[m].agg(agg) if mc != "count" else df.groupby(d).size()).sort_values(ascending=p["asc"]).reset_index()
        g.columns = [d, mc]; tot = g[mc].sum(); note = ""
        if op == "top":
            w2 = re.search(r"top\s+\d*\s*([a-z_]+)", p.get("q", ""))
            if w2 and not any(w2.group(1).rstrip("s") in c.lower().replace("_", " ") for c in df.columns):
                note = f'I could not find a "{w2.group(1)}" column, so I used "{d}". '
            g = g.head(p["n"])
        if g.empty: r["text"] = "No data available for this comparison."; return r
        r["table"] = g
        r["fig"] = px.pie(g, names=d, values=mc, hole=.4) if op == "share" else px.bar(g, x=d, y=mc, title=f"{mc} by {d}")
        w = g.iloc[0]
        fv = f"{w[mc]:,.0f}" if mc == "count" else f"{w[mc]:,.2f}"
        r["text"] = f"{note}{w[d]} has the {'lowest' if p['asc'] else 'highest'} {mc} ({fv})" + (
            f", about {w[mc]/tot*100:.1f}% of the total." if agg in ("sum", "count") and tot else ".")
    elif op == "correlation":
        if len(p.get("cm") or []) >= 2:
            a_, b_ = p["cm"][:2]; rr = df[a_].corr(df[b_])
            r["fig"] = px.scatter(df, x=a_, y=b_, title=f"{a_} vs {b_}")
            r["text"] = f"{a_} and {b_}: r = {rr:.2f} ({'strong' if abs(rr) > .6 else 'moderate' if abs(rr) > .3 else 'weak'} {'positive' if rr > 0 else 'negative'} relationship). Correlation does not imply causation."
            return r
        num = [c for c, x in prof["roles"].items() if x == "numeric"]
        if len(num) < 2: r["text"] = "Need at least two numeric columns."; return r
        if m and (o := _match(" ".join(str(p.get("q", ""))), [c for c in num if c != m])) is None: o = None
        c = df[num].corr(); r["table"] = c.round(2)
        r["fig"] = px.imshow(c, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, title="Correlation matrix")
        s = c.where(np.triu(np.ones(c.shape), 1).astype(bool)).stack().sort_values(key=abs, ascending=False)
        (a, b), v = s.index[0], s.iloc[0]
        r["text"] = f"Strongest relationship: {a} vs {b} (r = {v:.2f}, {'strong' if abs(v)>.6 else 'moderate' if abs(v)>.3 else 'weak'} {'positive' if v>0 else 'negative'}). Correlation does not imply causation."
    elif op == "outliers":
        o = {k: v for k, v in prof["outliers"].items() if v}
        r["text"] = ("IQR-rule outliers: " + ", ".join(f"{k}: {v}" for k, v in o.items())) if o else "No outliers were detected (IQR rule)."
        if o: r["fig"] = px.box(df, y=max(o, key=o.get), title=f"Outliers in {max(o, key=o.get)}")
    elif op == "distribution" and m:
        r["fig"] = px.histogram(df, x=m, nbins=30, title=f"Distribution of {m}")
        r["text"] = f"{m}: mean {df[m].mean():,.2f}, median {df[m].median():,.2f}, std {df[m].std():,.2f}, range {df[m].min():,.2f}–{df[m].max():,.2f}."
    else:
        r["text"] = prof["summary"]; r["table"] = df.describe().T.round(2)
        if op not in ("summary", "dashboard", "report"):
            r["text"] += " (I could not map that question to specific columns, so here is an overview.)"
    return r
 
# ---------- insights (computed from data only) ----------
def auto_insights(df, prof):
    ins, roles = [], prof["roles"]
    num = [c for c, x in roles.items() if x == "numeric"]; cat = [c for c, x in roles.items() if x == "categorical"]
    dt = [c for c, x in roles.items() if x == "datetime"]
    if num and cat:
        m = next((c for c in num if re.search("sales|revenue|amount|profit|price|salary|score", c.lower())), num[0])
        for d in cat[:2]:
            g = df.groupby(d)[m].sum().sort_values(ascending=False)
            if g.sum(): ins.append(f"'{g.index[0]}' has the highest total {m} by {d}, contributing {g.iloc[0]/g.sum()*100:.1f}% of the total.")
    if num and dt:
        m = num[0]; g = df.groupby(df[dt[0]].dt.to_period("M"))[m].sum()
        if len(g) > 1: ins.append(f"Monthly {m} moved from {g.iloc[0]:,.0f} to {g.iloc[-1]:,.0f}; peak month was {g.idxmax()}.")
    for c, k in prof["outliers"].items():
        if k: ins.append(f"'{c}' has {k} outlier value(s) ({k/len(df)*100:.1f}% of rows).")
    if len(num) > 1:
        s = df[num].corr().where(np.triu(np.ones((len(num),) * 2), 1).astype(bool)).stack()
        if len(s) and abs(s).max() > .5: (a, b) = abs(s).idxmax(); ins.append(f"'{a}' and '{b}' are notably correlated (r = {s[(a,b)]:.2f}).")
    return ins or ["No notable patterns were detected."]
 
# ---------- HTML report ----------
def report_html(name, raw, df, prof, log, items):
    h = lambda t: f"<h2>{t}</h2>"
    parts = [f"<h1>Automated Analysis Report — {name}</h1>", h("1. Dataset Overview"), f"<p>{prof['summary']}</p>",
             h("2. Data Quality"), f"<p>Missing values (raw): {prof['missing']}. Duplicate rows (raw): {prof['duplicates']}.</p>",
             h("3. Cleaning Performed"), "<ul>" + "".join(f"<li>{x}</li>" for x in log) + "</ul>",
             h("4. Descriptive Statistics"), df.describe().T.round(2).to_html(classes="t"),
             h("5. Key Findings"), "<ul>" + "".join(f"<li>{x}</li>" for x in auto_insights(df, prof)) + "</ul>"]
    if items:
        parts.append(h("6. Analyses and Charts"))
        for q, r in items:
            parts.append(f"<h3>{q}</h3><p>{r['text']}</p>")
            if r["fig"] is not None: parts.append(r["fig"].to_html(full_html=False, include_plotlyjs="cdn"))
    parts += [h("7. Conclusions"), "<p>All figures above were computed directly from the uploaded data; recommendations should be drawn only from these observed patterns.</p>"]
    return "<html><head><meta charset='utf-8'><style>body{font-family:Arial;max-width:960px;margin:auto}.t{border-collapse:collapse}.t td,.t th{border:1px solid #ccc;padding:4px}</style></head><body>" + "".join(parts) + "</body></html>"
 
