import streamlit as st
import pandas as pd
import matplotlib  # noqa: F401 – required for pandas Styler.background_gradient
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Clutch User LTV Dashboard", layout="wide")
st.title("Clutch User LTV Dashboard")

# --- File upload ---
uploaded_file = st.file_uploader("Upload your user export CSV", type=["csv"])
if uploaded_file is None:
    st.info("Drop your **data.csv** export above to get started.")
    st.stop()

# --- Load & prep data ---
@st.cache_data
def load_data(file_bytes):
    from io import BytesIO
    df = pd.read_csv(BytesIO(file_bytes))
    df = df[df["username"] != "Danny"]  # exclude internal user

    # Parse dates
    df["registration_date"] = pd.to_datetime(df["registration_date"], errors="coerce")
    df["reg_month"] = df["registration_date"].dt.to_period("M").astype(str)

    # Acquisition source — detect all tracker columns present in the file
    tracker_cols = ["gclid", "gbraid", "wbraid", "cxd", "affid",
                    "afp", "utm_campaign", "afp1", "afp2", "afp3"]
    for c in tracker_cols:
        if c not in df.columns:
            df[c] = ""
        else:
            df[c] = df[c].fillna("")

    def source(row):
        if row["gclid"] or row["gbraid"] or row["wbraid"]:
            return "Google Ads"
        if row["cxd"]:
            return "CXD"
        if row["afp"]:
            return "AFP"
        if row["utm_campaign"]:
            return f"UTM: {row['utm_campaign']}"
        if row["afp1"]:
            return "AFP1"
        if row["afp2"]:
            return "AFP2"
        if row["afp3"]:
            return "AFP3"
        if row["affid"]:
            return "Affiliate"
        return "Organic/Direct"

    df["source"] = df.apply(source, axis=1)

    # Ensure numeric
    num_cols = [
        "cp_revenue_total", "cp_gross_profit", "cash_in_total",
        "cp_revenue_pack_purchases", "cp_revenue_buyback_service_fees",
        "purchases_count", "purchases_amount", "buybacks_count", "buybacks_amount",
        "shipments_count", "cash_out_total",
        "bonus_cost_total",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["is_active"] = df["cp_revenue_total"] > 0
    return df

df = load_data(uploaded_file.getvalue())

# --- Sidebar filters ---
st.sidebar.header("Filters")

sources = st.sidebar.multiselect(
    "Acquisition Source", df["source"].unique().tolist(),
    default=df["source"].unique().tolist(),
)
months = sorted(df["reg_month"].dropna().unique())
month_range = st.sidebar.select_slider(
    "Registration Month Range", options=months,
    value=(months[0], months[-1]),
)
only_active = st.sidebar.checkbox("Only active users (revenue > 0)", value=False)

# Apply filters
mask = (
    df["source"].isin(sources)
    & df["reg_month"].between(month_range[0], month_range[1])
)
if only_active:
    mask &= df["is_active"]
fdf = df[mask]

# --- KPI cards ---
st.markdown("---")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Users", f"{len(fdf):,}")
c2.metric("Active Users", f"{fdf['is_active'].sum():,}")
conv = fdf["is_active"].mean() * 100 if len(fdf) else 0
c3.metric("Conversion %", f"{conv:.1f}%")
c4.metric("Total Revenue", f"${fdf['cp_revenue_total'].sum():,.0f}")
c5.metric("Total Gross Profit", f"${fdf['cp_gross_profit'].sum():,.0f}")

st.markdown("---")

# --- Charts ---

# 1. Registrations over time by source
st.subheader("User Registrations by Month & Source")
reg = fdf.groupby(["reg_month", "source"]).size().reset_index(name="count")
fig1 = px.bar(reg, x="reg_month", y="count", color="source",
              barmode="stack", labels={"reg_month": "Month", "count": "Users"})
st.plotly_chart(fig1, use_container_width=True)

# 2. Avg Revenue per User (LTV) - heatmap table
st.subheader("Average Revenue per User (LTV) by Month & Source")
ltv = fdf.groupby(["reg_month", "source"]).agg(
    users=("id", "count"),
    revenue=("cp_revenue_total", "sum"),
).reset_index()
ltv["avg_revenue"] = (ltv["revenue"] / ltv["users"]).round(0)
ltv_pivot = ltv.pivot(index="source", columns="reg_month", values="avg_revenue").fillna(0)
# Add a Total column
ltv_totals = fdf.groupby("source").agg(users=("id", "count"), revenue=("cp_revenue_total", "sum")).reset_index()
ltv_totals["Total"] = (ltv_totals["revenue"] / ltv_totals["users"]).round(0)
ltv_pivot = ltv_pivot.join(ltv_totals.set_index("source")["Total"])
st.dataframe(
    ltv_pivot.style.format("${:,.2f}")
    .background_gradient(cmap="Greens", axis=None)
    .set_properties(**{"text-align": "right"}),
    use_container_width=True,
)

# 3. Avg Gross Profit per User - heatmap table
st.subheader("Average Gross Profit per User by Month & Source")
gp = fdf.groupby(["reg_month", "source"]).agg(
    users=("id", "count"),
    gross_profit=("cp_gross_profit", "sum"),
).reset_index()
gp["avg_gp"] = (gp["gross_profit"] / gp["users"]).round(0)
gp_pivot = gp.pivot(index="source", columns="reg_month", values="avg_gp").fillna(0)
gp_totals = fdf.groupby("source").agg(users=("id", "count"), gross_profit=("cp_gross_profit", "sum")).reset_index()
gp_totals["Total"] = (gp_totals["gross_profit"] / gp_totals["users"]).round(0)
gp_pivot = gp_pivot.join(gp_totals.set_index("source")["Total"])
st.dataframe(
    gp_pivot.style.format("${:,.2f}")
    .background_gradient(cmap="RdYlGn", axis=None)
    .set_properties(**{"text-align": "right"}),
    use_container_width=True,
)

# 4. Conversion rate by month & source
st.subheader("Conversion Rate by Month & Source")
conv_df = fdf.groupby(["reg_month", "source"]).agg(
    users=("id", "count"),
    active=("is_active", "sum"),
).reset_index()
conv_df["conversion"] = conv_df["active"] / conv_df["users"] * 100
fig4 = px.line(conv_df, x="reg_month", y="conversion", color="source",
               markers=True,
               labels={"reg_month": "Month", "conversion": "Conversion %"})
st.plotly_chart(fig4, use_container_width=True)

# 5. Cumulative revenue by source (top N users)
st.subheader("Revenue Concentration (Cumulative % by Top Users)")
fig6 = go.Figure()
for src in sorted(fdf["source"].unique()):
    src_df = fdf[(fdf["source"] == src) & fdf["is_active"]].sort_values("cp_revenue_total", ascending=False).reset_index(drop=True)
    if len(src_df) == 0:
        continue
    src_df["cum_pct"] = src_df["cp_revenue_total"].cumsum() / src_df["cp_revenue_total"].sum() * 100
    src_df["user_rank_pct"] = (src_df.index + 1) / len(src_df) * 100
    fig6.add_trace(go.Scatter(x=src_df["user_rank_pct"], y=src_df["cum_pct"],
                              mode="lines", name=src))
fig6.update_layout(xaxis_title="% of Users (ranked by revenue)", yaxis_title="Cumulative % of Revenue")
st.plotly_chart(fig6, use_container_width=True)

# 6. User distribution by Revenue & Profit tiers
st.subheader("User Distribution by Revenue & Gross Profit Tiers")

def bucket_users(series, label):
    bins = [-float("inf"), 0, 1, 100, 500, 1000, 5000, 10000, 50000, float("inf")]
    labels = ["< $0", "$0", "$1–100", "$100–500", "$500–1K", "$1K–5K", "$5K–10K", "$10K–50K", "$50K+"]
    bucketed = pd.cut(series, bins=bins, labels=labels, right=True)
    counts = bucketed.value_counts().reindex(labels).fillna(0).astype(int)
    return counts

dist_col1, dist_col2 = st.columns(2)

with dist_col1:
    rev_buckets = fdf.groupby("source")["cp_revenue_total"].apply(
        lambda s: pd.cut(s, bins=[-float("inf"), 0, 0.01, 100, 500, 1000, 5000, 10000, 50000, float("inf")],
                         labels=["< $0", "$0", "$1–100", "$100–500", "$500–1K", "$1K–5K", "$5K–10K", "$10K–50K", "$50K+"],
                         right=True).value_counts()
    ).reset_index()
    rev_buckets.columns = ["source", "tier", "count"]
    fig_rev = px.bar(rev_buckets, x="tier", y="count", color="source", barmode="group",
                     title="Revenue Tier", labels={"tier": "", "count": "Users"})
    fig_rev.update_xaxes(categoryorder="array",
                         categoryarray=["< $0", "$0", "$1–100", "$100–500", "$500–1K", "$1K–5K", "$5K–10K", "$10K–50K", "$50K+"])
    st.plotly_chart(fig_rev, use_container_width=True)

with dist_col2:
    gp_buckets = fdf.groupby("source")["cp_gross_profit"].apply(
        lambda s: pd.cut(s, bins=[-float("inf"), 0, 0.01, 100, 500, 1000, 5000, 10000, 50000, float("inf")],
                         labels=["< $0", "$0", "$1–100", "$100–500", "$500–1K", "$1K–5K", "$5K–10K", "$10K–50K", "$50K+"],
                         right=True).value_counts()
    ).reset_index()
    gp_buckets.columns = ["source", "tier", "count"]
    fig_gp = px.bar(gp_buckets, x="tier", y="count", color="source", barmode="group",
                    title="Gross Profit Tier", labels={"tier": "", "count": "Users"})
    fig_gp.update_xaxes(categoryorder="array",
                        categoryarray=["< $0", "$0", "$1–100", "$100–500", "$500–1K", "$1K–5K", "$5K–10K", "$10K–50K", "$50K+"])
    st.plotly_chart(fig_gp, use_container_width=True)

# 6b. Revenue vs Gross Profit scatter (active users only)
st.subheader("Revenue vs Gross Profit per User")
scatter_df = fdf[fdf["is_active"]].copy()
if len(scatter_df) > 0:
    fig_scatter = px.scatter(
        scatter_df, x="cp_revenue_total", y="cp_gross_profit", color="source",
        hover_data=["username", "reg_month"],
        labels={"cp_revenue_total": "Total Revenue ($)", "cp_gross_profit": "Gross Profit ($)"},
        opacity=0.6,
    )
    fig_scatter.add_hline(y=0, line_dash="dash", line_color="red", opacity=0.5)
    fig_scatter.update_layout(height=500)
    st.plotly_chart(fig_scatter, use_container_width=True)

# 7. Detailed cohort table
st.subheader("Cohort Detail Table")
ct_col1, ct_col2 = st.columns(2)
with ct_col1:
    ct_months = st.multiselect(
        "Filter months", sorted(fdf["reg_month"].dropna().unique()),
        default=sorted(fdf["reg_month"].dropna().unique()),
        key="cohort_months",
    )
with ct_col2:
    ct_sources = st.multiselect(
        "Filter sources", sorted(fdf["source"].unique()),
        default=sorted(fdf["source"].unique()),
        key="cohort_sources",
    )
ct_df = fdf[fdf["reg_month"].isin(ct_months) & fdf["source"].isin(ct_sources)]
detail = ct_df.groupby(["reg_month", "source"]).agg(
    users=("id", "count"),
    active=("is_active", "sum"),
    total_revenue=("cp_revenue_total", "sum"),
    total_gp=("cp_gross_profit", "sum"),
    total_cash_in=("cash_in_total", "sum"),
    total_purchases=("purchases_count", "sum"),
    total_buybacks=("buybacks_count", "sum"),
    total_bonus_cost=("bonus_cost_total", "sum"),
).reset_index()
detail["conv_%"] = (detail["active"] / detail["users"] * 100).round(1)
detail["avg_revenue"] = (detail["total_revenue"] / detail["users"]).round(0)
detail["avg_gp"] = (detail["total_gp"] / detail["users"]).round(0)
detail = detail.sort_values(["reg_month", "source"])

def fmt_currency(val):
    """Format as $X,XXX.XX with red color for negatives."""
    s = f"${val:,.2f}"
    if val < 0:
        return f'<span style="color:red">{s}</span>'
    return s

def styled_html_table(dataframe, currency_cols, right_align_cols=None):
    """Render a dataframe as HTML with currency formatting and red negatives."""
    if right_align_cols is None:
        right_align_cols = currency_cols
    display = dataframe.copy()
    for c in currency_cols:
        display[c] = dataframe[c].apply(fmt_currency)
    html = display.to_html(escape=False, index=False)
    # Right-align currency columns via CSS on th/td
    css = """<style>
    .styled-table { width:100%; border-collapse:collapse; font-size:14px; color: inherit; }
    .styled-table th { text-align:left; padding:8px 10px; border-bottom:2px solid rgba(128,128,128,0.4); font-weight:600; }
    .styled-table td { padding:6px 10px; border-bottom:1px solid rgba(128,128,128,0.2); }
    .styled-table tr:hover td { background:rgba(128,128,128,0.08); }
    """ + "".join(
        f".styled-table td:nth-child({dataframe.columns.get_loc(c)+1}),"
        f".styled-table th:nth-child({dataframe.columns.get_loc(c)+1})"
        f"{{ text-align:right; }}\n"
        for c in right_align_cols
    ) + "</style>"
    html = html.replace("<table ", f'<table class="styled-table" ')
    st.html(css + html)

currency_cols = ["total_revenue", "total_gp", "total_cash_in", "avg_revenue", "avg_gp", "total_bonus_cost"]
styled_html_table(detail, currency_cols, right_align_cols=currency_cols + ["users", "active", "conv_%", "total_purchases", "total_buybacks"])

# 7. Top users table
st.subheader("Top 50 Users by Revenue")
top = fdf.nlargest(50, "cp_revenue_total")[
    ["username", "source", "reg_month", "registration_country",
     "cp_revenue_total", "cp_gross_profit", "cash_in_total",
     "purchases_count", "buybacks_count", "shipments_count"]
].reset_index(drop=True)
top.index = top.index + 1
top_money = ["cp_revenue_total", "cp_gross_profit", "cash_in_total"]
top_numeric = top_money + ["purchases_count", "buybacks_count", "shipments_count"]
styled_html_table(top, top_money, right_align_cols=top_numeric)
