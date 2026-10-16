"""Nassau Candy Distributor - Shipping Route Efficiency Dashboard (Streamlit)."""
import pandas as pd
import plotly.express as px
import streamlit as st
from analysis import load_clean, route_table

st.set_page_config(page_title="Nassau Candy - Route Efficiency", layout="wide")


@st.cache_data
def get_data():
    return load_clean("Nassau_Candy_Distributor.csv")


df, log = get_data()

# ------------------------------------------------------------------ sidebar
st.sidebar.title("Filters")
d0, d1 = df["Order Date"].min().date(), df["Order Date"].max().date()
date_range = st.sidebar.date_input("Order date range", (d0, d1), min_value=d0, max_value=d1)
regions = st.sidebar.multiselect("Region", sorted(df["Region"].unique()), default=sorted(df["Region"].unique()))
state_pool = sorted(df[df["Region"].isin(regions)]["State/Province"].unique())
states = st.sidebar.multiselect("State / Province (empty = all)", state_pool)
modes = st.sidebar.multiselect("Ship mode", sorted(df["Ship Mode"].unique()), default=sorted(df["Ship Mode"].unique()))
factories = st.sidebar.multiselect("Factory", sorted(df["Factory"].unique()), default=sorted(df["Factory"].unique()))
threshold = st.sidebar.slider("Delay threshold (days)", 1, 10, 5,
                              help="A shipment counts as delayed if its lead time exceeds this.")
min_orders = st.sidebar.slider("Minimum shipments per route", 1, 100, 10,
                               help="Hides routes with too few orders to rank fairly.")

f = df.copy()
if len(date_range) == 2:
    f = f[(f["Order Date"].dt.date >= date_range[0]) & (f["Order Date"].dt.date <= date_range[1])]
f = f[f["Region"].isin(regions) & f["Ship Mode"].isin(modes) & f["Factory"].isin(factories)]
if states:
    f = f[f["State/Province"].isin(states)]

st.title("🍬 Nassau Candy - Shipping Route Efficiency")
if f.empty:
    st.warning("No shipments match the current filters.")
    st.stop()

# ------------------------------------------------------------------ KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Shipments", f"{len(f):,}")
k2.metric("Avg lead time", f"{f['Lead Time'].mean():.2f} days")
k3.metric("Delay frequency", f"{(f['Lead Time'] > threshold).mean() * 100:.1f}%")
k4.metric("Routes (state level)", f"{f['Route (State)'].nunique():,}")

with st.expander("Data cleaning notes"):
    st.write(
        f"Rows loaded: {log['rows_raw']:,}. Invalid dates: {log['invalid_dates']}. "
        f"Negative lead times removed: {log['negative_lead_time_removed']}. "
        f"Unmapped products: {log['unmapped_products']}."
    )
    st.write(
        "**Date correction:** raw ship dates in the file sit 904-1,642 days after the order date "
        "(a fixed block of days per Order-ID year, "
        f"offsets {log['offsets']}). These offsets were subtracted so lead times fall in a realistic "
        "0-11 day range. Lead times shown everywhere in this app are the corrected values."
    )

tab1, tab2, tab3, tab4 = st.tabs(["Route Efficiency", "Geographic Map", "Ship Mode Comparison", "Route Drill-Down"])

# ------------------------------------------------------------------ tab 1
with tab1:
    level = st.radio("Route level", ["Route (State)", "Route (Region)"], horizontal=True)
    rt = route_table(f, level, threshold, min_orders if level == "Route (State)" else 1)
    if rt.empty:
        st.info("No routes meet the minimum shipment count. Lower the slider in the sidebar.")
    else:
        n = min(10, len(rt))
        c1, c2 = st.columns(2)
        cols = ["Rank", level, "Shipments", "Avg_Lead_Time", "Std_Lead_Time", "Delay_Frequency_%", "Efficiency_Score"]
        c1.subheader(f"Top {n} most efficient")
        c1.dataframe(rt.head(n)[cols], hide_index=True, use_container_width=True)
        c2.subheader(f"Bottom {n} least efficient")
        c2.dataframe(rt.tail(n).iloc[::-1][cols], hide_index=True, use_container_width=True)

        st.subheader("Average lead time by route")
        show = pd.concat([rt.head(n), rt.tail(n)]).drop_duplicates(level)
        fig = px.bar(show, x="Avg_Lead_Time", y=level, orientation="h", color="Efficiency_Score",
                     color_continuous_scale="RdYlGn", hover_data=["Shipments", "Delay_Frequency_%"])
        fig.update_layout(yaxis={"categoryorder": "total descending"}, height=520)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Route performance leaderboard")
        st.dataframe(rt, hide_index=True, use_container_width=True)
        st.download_button("Download leaderboard (CSV)", rt.to_csv(index=False), "route_leaderboard.csv")

# ------------------------------------------------------------------ tab 2
with tab2:
    us = f[f["State Code"].notna()]
    sg = us.groupby(["State Code", "State/Province"]).agg(
        Avg_Lead_Time=("Lead Time", "mean"), Shipments=("Lead Time", "size"),
        Delay_Pct=("Lead Time", lambda s: (s > threshold).mean() * 100)).reset_index()
    metric = st.radio("Colour by", ["Avg_Lead_Time", "Delay_Pct", "Shipments"], horizontal=True)
    fig = px.choropleth(sg, locations="State Code", locationmode="USA-states", scope="usa",
                        color=metric, hover_name="State/Province",
                        hover_data=["Avg_Lead_Time", "Delay_Pct", "Shipments"],
                        color_continuous_scale="RdYlGn_r" if metric != "Shipments" else "Blues")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Regional bottlenecks")
    reg = f.groupby("Region").agg(Shipments=("Lead Time", "size"), Avg_Lead_Time=("Lead Time", "mean"),
                                  Delay_Pct=("Lead Time", lambda s: (s > threshold).mean() * 100)).reset_index().round(2)
    c1, c2 = st.columns(2)
    c1.dataframe(reg, hide_index=True, use_container_width=True)
    c2.plotly_chart(px.scatter(reg, x="Shipments", y="Avg_Lead_Time", size="Shipments", text="Region",
                               title="Volume vs lead time (top-right = high volume + slow)"),
                    use_container_width=True)
    st.subheader("Congestion-prone states (high volume AND above-average lead time)")
    cong = sg[(sg["Shipments"] >= sg["Shipments"].median()) & (sg["Avg_Lead_Time"] > f["Lead Time"].mean())]
    st.dataframe(cong.sort_values("Avg_Lead_Time", ascending=False).round(2), hide_index=True,
                 use_container_width=True)

# ------------------------------------------------------------------ tab 3
with tab3:
    ms = f.groupby("Ship Mode").agg(Shipments=("Lead Time", "size"), Avg_Lead_Time=("Lead Time", "mean"),
                                    Std=("Lead Time", "std"), Avg_Sales=("Sales", "mean"),
                                    Avg_Gross_Profit=("Gross Profit", "mean"), Avg_Cost=("Cost", "mean"),
                                    Delay_Pct=("Lead Time", lambda s: (s > threshold).mean() * 100)).reset_index().round(2)
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(ms, x="Ship Mode", y="Avg_Lead_Time", color="Ship Mode", text="Avg_Lead_Time",
                           title="Average lead time by ship mode"), use_container_width=True)
    c2.plotly_chart(px.box(f, x="Ship Mode", y="Lead Time", color="Ship Mode",
                           title="Lead time distribution"), use_container_width=True)
    st.dataframe(ms, hide_index=True, use_container_width=True)
    st.caption("Cost-time trade-off (descriptive): the file has no shipping-fee column, so average product cost, "
               "sales and gross profit per line are shown. They barely differ by mode, so faster modes are not "
               "visibly priced into order value in this data.")
    mr = f.groupby(["Region", "Ship Mode"])["Lead Time"].mean().reset_index()
    st.plotly_chart(px.bar(mr, x="Region", y="Lead Time", color="Ship Mode", barmode="group",
                           title="Lead time by region and ship mode"), use_container_width=True)

# ------------------------------------------------------------------ tab 4
with tab4:
    st.subheader("State-level performance")
    pool = sorted(f["State/Province"].unique())
    pick = st.selectbox("State / Province", pool)
    s = f[f["State/Province"] == pick]
    a, b, c = st.columns(3)
    a.metric("Shipments", f"{len(s):,}")
    b.metric("Avg lead time", f"{s['Lead Time'].mean():.2f} days")
    c.metric("Delay frequency", f"{(s['Lead Time'] > threshold).mean() * 100:.1f}%")
    sr = route_table(s, "Route (State)", threshold)
    st.dataframe(sr, hide_index=True, use_container_width=True)
    st.plotly_chart(px.histogram(s, x="Lead Time", color="Ship Mode", nbins=12,
                                 title=f"Lead-time distribution - {pick}"), use_container_width=True)
    trend = s.set_index("Order Date")["Lead Time"].resample("MS").mean().reset_index()
    st.plotly_chart(px.line(trend, x="Order Date", y="Lead Time", markers=True,
                            title=f"Monthly average lead time - {pick}"), use_container_width=True)

    st.subheader("Order-level shipment timeline")
    orders = s.sort_values("Order Date", ascending=False).head(200).copy()
    orders["Corrected Ship Date"] = orders["Order Date"] + pd.to_timedelta(orders["Lead Time"], unit="D")
    gantt = px.timeline(orders.head(40), x_start="Order Date", x_end="Corrected Ship Date",
                        y="Order ID", color="Ship Mode", hover_data=["Factory", "Lead Time"])
    gantt.update_yaxes(autorange="reversed")
    st.caption("Showing the 40 most recent orders (bars are order date → corrected ship date).")
    st.plotly_chart(gantt, use_container_width=True)
    st.dataframe(orders[["Order ID", "Order Date", "Corrected Ship Date", "Lead Time", "Ship Mode", "Factory",
                         "City", "Product Name", "Sales"]], hide_index=True, use_container_width=True)
