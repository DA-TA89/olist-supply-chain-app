import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.db import run_query

st.set_page_config(page_title="Tồn Kho", page_icon="📦", layout="wide")

st.markdown("## 📦 Phân tích tồn kho")
st.markdown("Theo dõi mức tồn kho, tỷ lệ hết hàng và hiệu quả sử dụng kho.")

with st.sidebar:
    st.header("🔧 Bộ lọc")
    years = st.multiselect("Năm", [2016, 2017, 2018], default=[2017, 2018])
    if not years:
        years = [2017, 2018]
    year_filter = ",".join(str(y) for y in years)

    wh_df = run_query("SELECT warehouse_name FROM gold_dim_warehouse ORDER BY WarehouseKey")
    wh_names = wh_df["warehouse_name"].tolist()
    selected_wh = st.multiselect("Kho hàng", wh_names, default=wh_names)
    if not selected_wh:
        selected_wh = wh_names
    wh_filter = "','".join(selected_wh)

# ── KPIs ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_inv_kpis(year_filter, wh_filter):
    return run_query(f"""
        SELECT
            AVG(i.stock_quantity)  AS avg_stock,
            SUM(i.stock_quantity)  AS total_stock,
            SUM(i.is_stock_out)*100.0/COUNT(*) AS stockout_pct,
            COUNT(DISTINCT i.ProductKey)       AS products_tracked
        FROM gold_fact_inventory i
        JOIN gold_dim_date d      ON i.DateKey      = d.DateKey
        JOIN gold_dim_warehouse w ON i.WarehouseKey = w.WarehouseKey
        WHERE d.year_number IN ({year_filter})
          AND w.warehouse_name IN ('{wh_filter}')
    """)

kpi = load_inv_kpis(year_filter, wh_filter).iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("📦 Tồn kho TB",       f"{kpi['avg_stock']:,.1f} SP")
c2.metric("🔢 Tổng tồn kho",    f"{kpi['total_stock']:,.0f} SP")
c3.metric("⚠️ Tỷ lệ hết hàng",  f"{kpi['stockout_pct']:.2f}%",
          delta_color="inverse")
c4.metric("🏷️ SP Theo Dõi",     f"{kpi['products_tracked']:,}")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 🏭 Tồn kho trung bình theo kho")
    @st.cache_data(ttl=600)
    def load_wh_stock(year_filter, wh_filter):
        return run_query(f"""
            SELECT w.warehouse_name, w.capacity,
                   AVG(i.stock_quantity) AS avg_stock,
                   SUM(i.is_stock_out)*100.0/COUNT(*) AS stockout_pct
            FROM gold_fact_inventory i
            JOIN gold_dim_warehouse w ON i.WarehouseKey = w.WarehouseKey
            JOIN gold_dim_date d      ON i.DateKey      = d.DateKey
            WHERE d.year_number IN ({year_filter})
              AND w.warehouse_name IN ('{wh_filter}')
            GROUP BY w.warehouse_name, w.capacity
            ORDER BY avg_stock DESC
        """)
    df_wh = load_wh_stock(year_filter, wh_filter)
    fig1 = px.bar(df_wh, x="warehouse_name", y="avg_stock",
                  color="stockout_pct", color_continuous_scale="RdYlGn_r",
                  text=df_wh["avg_stock"].apply(lambda x: f"{x:.0f}"),
                  labels={"avg_stock": "Tồn kho TB", "warehouse_name": "", "stockout_pct": "Stockout%"})
    fig1.update_layout(height=340, margin=dict(t=20, b=20),
                       plot_bgcolor="white", yaxis=dict(gridcolor="#f1f5f9"))
    fig1.update_traces(textposition="outside")
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.markdown("#### 📅 Tỉ lệ hết hàng theo tháng")
    @st.cache_data(ttl=600)
    def load_monthly_stockout(year_filter, wh_filter):
        return run_query(f"""
            SELECT d.year_number AS year, d.month_number AS month,
                   d.month_name,
                   SUM(i.is_stock_out)*100.0/COUNT(*) AS stockout_pct
            FROM gold_fact_inventory i
            JOIN gold_dim_date d      ON i.DateKey      = d.DateKey
            JOIN gold_dim_warehouse w ON i.WarehouseKey = w.WarehouseKey
            WHERE d.year_number IN ({year_filter})
              AND w.warehouse_name IN ('{wh_filter}')
            GROUP BY d.year_number, d.month_number, d.month_name
            ORDER BY d.year_number, d.month_number
        """)
    df_so = load_monthly_stockout(year_filter, wh_filter)
    df_so["period"] = df_so["month_name"].str[:3] + " " + df_so["year"].astype(str)
    fig2 = px.line(df_so, x="period", y="stockout_pct", color="year",
                   markers=True, labels={"stockout_pct": "Stockout (%)", "period": ""})
    fig2.update_layout(height=340, margin=dict(t=20, b=20),
                       plot_bgcolor="white", yaxis=dict(gridcolor="#f1f5f9"))
    st.plotly_chart(fig2, use_container_width=True)

# ── Warehouse Utilization ──────────────────────────────────────────────────────
st.markdown("#### 🔋 Mức độ sử dụng kho")
@st.cache_data(ttl=600)
def load_utilization(year_filter, wh_filter):
    return run_query(f"""
        SELECT w.warehouse_name, w.capacity,
               AVG(i.stock_quantity) AS avg_stock,
               MAX(i.stock_quantity) AS max_stock,
               AVG(i.stock_quantity)*100.0/w.capacity AS utilization_pct
        FROM gold_fact_inventory i
        JOIN gold_dim_warehouse w ON i.WarehouseKey = w.WarehouseKey
        JOIN gold_dim_date d      ON i.DateKey      = d.DateKey
        WHERE d.year_number IN ({year_filter})
          AND w.warehouse_name IN ('{wh_filter}')
        GROUP BY w.warehouse_name, w.capacity
        ORDER BY utilization_pct DESC
    """)
df_util = load_utilization(year_filter, wh_filter)

fig3 = go.Figure()
for _, row in df_util.iterrows():
    fig3.add_trace(go.Bar(
        x=[row["warehouse_name"]],
        y=[row["avg_stock"]],
        name=row["warehouse_name"],
        text=f"{row['utilization_pct']:.1f}%",
        textposition="outside"
    ))
    fig3.add_trace(go.Scatter(
        x=[row["warehouse_name"]],
        y=[row["capacity"]],
        mode="markers",
        marker=dict(symbol="line-ew", size=20, color="red", line=dict(width=3)),
        name="Capacity" if _ == 0 else None,
        showlegend=(_ == 0)
    ))
fig3.update_layout(height=350, barmode="group", showlegend=False,
                   margin=dict(t=20, b=20), plot_bgcolor="white",
                   yaxis=dict(title="Units", gridcolor="#f1f5f9"),
                   xaxis_title="")
st.plotly_chart(fig3, use_container_width=True)

# ── Top Stockout Products ──────────────────────────────────────────────────────
st.markdown("#### 🔴 Top 15 Sản phẩm hay hết hàng nhất")
@st.cache_data(ttl=600)
def load_top_stockout(year_filter, wh_filter):
    return run_query(f"""
        SELECT p.product_category_name AS category,
               COUNT(*) AS total_snapshots,
               SUM(i.is_stock_out) AS stockout_days,
               SUM(i.is_stock_out)*100.0/COUNT(*) AS stockout_pct
        FROM gold_fact_inventory i
        JOIN gold_dim_product p   ON i.ProductKey   = p.ProductKey
        JOIN gold_dim_warehouse w ON i.WarehouseKey = w.WarehouseKey
        JOIN gold_dim_date d      ON i.DateKey      = d.DateKey
        WHERE d.year_number IN ({year_filter})
          AND w.warehouse_name IN ('{wh_filter}')
          AND p.product_category_name IS NOT NULL
        GROUP BY p.product_category_name
        HAVING total_snapshots > 100
        ORDER BY stockout_pct DESC
        LIMIT 15
    """)
df_top = load_top_stockout(year_filter, wh_filter)
df_top["category"] = df_top["category"].str.replace("_", " ").str.title()
fig4 = px.bar(df_top, x="stockout_pct", y="category", orientation="h",
              color="stockout_pct", color_continuous_scale="Reds",
              text=df_top["stockout_pct"].apply(lambda x: f"{x:.1f}%"),
              labels={"stockout_pct": "Stockout Rate (%)", "category": ""})
fig4.update_layout(height=460, margin=dict(t=20, b=20),
                   yaxis={"categoryorder": "total ascending"},
                   coloraxis_showscale=False, plot_bgcolor="white",
                   xaxis=dict(gridcolor="#f1f5f9"))
fig4.update_traces(textposition="outside")
st.plotly_chart(fig4, use_container_width=True)
