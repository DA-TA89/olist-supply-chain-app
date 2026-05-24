import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.db import run_query

st.set_page_config(page_title="Doanh Thu & Đơn Hàng", page_icon="📊", layout="wide")

st.markdown("## 📊 Doanh thu & Đơn hàng")
st.markdown("Phân tích xu hướng doanh thu, đơn hàng và danh mục sản phẩm.")

# ── Filters ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Bộ lọc")
    years = st.multiselect("Năm", [2016, 2017, 2018], default=[2017, 2018])
    if not years:
        years = [2017, 2018]
    year_filter = ",".join(str(y) for y in years)

    status_opts = ["delivered", "shipped", "canceled", "processing", "invoiced"]
    statuses = st.multiselect("Trạng thái đơn", status_opts, default=["delivered"])
    if not statuses:
        statuses = ["delivered"]
    status_filter = "','".join(statuses)

# ── KPIs ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_revenue_kpis(year_filter, status_filter):
    return run_query(f"""
        SELECT
            SUM(o.price)                    AS total_revenue,
            SUM(o.price - o.cost)           AS total_profit,
            COUNT(DISTINCT o.order_id)      AS total_orders,
            COUNT(*)                        AS total_items,
            AVG(o.price)                    AS avg_item_price,
            SUM(o.price - o.cost)*100.0/SUM(o.price) AS profit_margin
        FROM gold_fact_orders o
        JOIN gold_dim_date d ON o.DateKey = d.DateKey
        WHERE d.year_number IN ({year_filter})
          AND o.order_status IN ('{status_filter}')
    """)

kpi = load_revenue_kpis(year_filter, status_filter).iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Tổng doanh thu",   f"R$ {kpi['total_revenue']:,.0f}")
c2.metric("📈 Tổng lợi nhuận",   f"R$ {kpi['total_profit']:,.0f}",  f"{kpi['profit_margin']:.1f}% margin")
c3.metric("📦 Tổng đơn hàng",    f"{kpi['total_orders']:,}")
c4.metric("🛒 Giá TB / SP",     f"R$ {kpi['avg_item_price']:.1f}")

st.markdown("---")

# ── Revenue by Month ──────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 2])

with col1:
    st.markdown("#### 📅 Doanh thu theo tháng")
    @st.cache_data(ttl=600)
    def load_monthly(year_filter, status_filter):
        return run_query(f"""
            SELECT d.year_number AS year, d.month_number AS month,
                   d.month_name AS month_name,
                   SUM(o.price) AS revenue,
                   COUNT(DISTINCT o.order_id) AS orders
            FROM gold_fact_orders o
            JOIN gold_dim_date d ON o.DateKey = d.DateKey
            WHERE d.year_number IN ({year_filter})
              AND o.order_status IN ('{status_filter}')
            GROUP BY d.year_number, d.month_number, d.month_name
            ORDER BY d.year_number, d.month_number
        """)
    df_monthly = load_monthly(year_filter, status_filter)
    df_monthly["period"] = df_monthly["month_name"].str[:3] + " " + df_monthly["year"].astype(str)

    fig = go.Figure()
    for yr in sorted(df_monthly["year"].unique()):
        df_yr = df_monthly[df_monthly["year"] == yr]
        fig.add_trace(go.Bar(
            x=df_yr["period"], y=df_yr["revenue"],
            name=str(yr), text=df_yr["revenue"].apply(lambda x: f"R${x/1e3:.0f}K"),
            textposition="outside"
        ))
    fig.update_layout(barmode="group", height=340, margin=dict(t=20, b=20),
                      yaxis_title="Doanh thu (BRL)", xaxis_title="",
                      legend_title="Năm", plot_bgcolor="white",
                      yaxis=dict(gridcolor="#f1f5f9"))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("#### 📋 Phân bố trạng thái đơn")
    @st.cache_data(ttl=600)
    def load_status_dist(year_filter):
        return run_query(f"""
            SELECT o.order_status, COUNT(DISTINCT o.order_id) AS cnt
            FROM gold_fact_orders o
            JOIN gold_dim_date d ON o.DateKey = d.DateKey
            WHERE d.year_number IN ({year_filter})
            GROUP BY o.order_status ORDER BY cnt DESC
        """)
    df_status = load_status_dist(year_filter)
    color_map = {
        "delivered": "#16a34a", "shipped": "#2563eb",
        "canceled": "#dc2626",  "processing": "#d97706",
        "invoiced": "#7c3aed",  "approved": "#0891b2", "unavailable": "#94a3b8"
    }
    fig2 = px.pie(df_status, names="order_status", values="cnt",
                  color="order_status", color_discrete_map=color_map,
                  hole=0.45)
    fig2.update_layout(height=340, margin=dict(t=20, b=20))
    fig2.update_traces(textposition="outside", textinfo="percent+label")
    st.plotly_chart(fig2, use_container_width=True)

# ── Top Categories ────────────────────────────────────────────────────────────
st.markdown("#### 🏷️ Top 15 danh mục sản phẩm theo doanh thu")
@st.cache_data(ttl=600)
def load_categories(year_filter, status_filter):
    return run_query(f"""
        SELECT p.product_category_name AS category,
               SUM(o.price)            AS revenue,
               COUNT(DISTINCT o.order_id) AS orders,
               AVG(o.price)            AS avg_price
        FROM gold_fact_orders o
        JOIN gold_dim_product p ON o.ProductKey = p.ProductKey
        JOIN gold_dim_date d    ON o.DateKey    = d.DateKey
        WHERE d.year_number IN ({year_filter})
          AND o.order_status IN ('{status_filter}')
          AND p.product_category_name IS NOT NULL
        GROUP BY p.product_category_name
        ORDER BY revenue DESC
        LIMIT 15
    """)
df_cat = load_categories(year_filter, status_filter)
df_cat["category"] = df_cat["category"].str.replace("_", " ").str.title()

fig3 = px.bar(df_cat, x="revenue", y="category", orientation="h",
              color="revenue", color_continuous_scale="Blues",
              text=df_cat["revenue"].apply(lambda x: f"R${x/1e3:.0f}K"),
              labels={"revenue": "Doanh thu (BRL)", "category": ""})
fig3.update_layout(height=480, margin=dict(t=20, b=20),
                   yaxis={"categoryorder": "total ascending"},
                   coloraxis_showscale=False, plot_bgcolor="white",
                   xaxis=dict(gridcolor="#f1f5f9"))
fig3.update_traces(textposition="outside")
st.plotly_chart(fig3, use_container_width=True)

# ── Revenue by Warehouse ──────────────────────────────────────────────────────
st.markdown("#### 🏭 Doanh thu theo kho")
@st.cache_data(ttl=600)
def load_warehouse_rev(year_filter, status_filter):
    return run_query(f"""
        SELECT w.warehouse_name, w.location_state,
               SUM(o.price)  AS revenue,
               COUNT(DISTINCT o.order_id) AS orders
        FROM gold_fact_orders o
        JOIN gold_dim_warehouse w ON o.WarehouseKey = w.WarehouseKey
        JOIN gold_dim_date d      ON o.DateKey      = d.DateKey
        WHERE d.year_number IN ({year_filter})
          AND o.order_status IN ('{status_filter}')
        GROUP BY w.warehouse_name, w.location_state
        ORDER BY revenue DESC
    """)
df_wh = load_warehouse_rev(year_filter, status_filter)
fig4 = px.bar(df_wh, x="warehouse_name", y="revenue",
              color="revenue", color_continuous_scale="Blues",
              text=df_wh["revenue"].apply(lambda x: f"R${x/1e3:.0f}K"),
              labels={"revenue": "Doanh thu (BRL)", "warehouse_name": "Kho"})
fig4.update_layout(height=350, margin=dict(t=20, b=20),
                   coloraxis_showscale=False, plot_bgcolor="white",
                   yaxis=dict(gridcolor="#f1f5f9"))
fig4.update_traces(textposition="outside")
st.plotly_chart(fig4, use_container_width=True)

# ── Raw Data ──────────────────────────────────────────────────────────────────
with st.expander("📄 Xem dữ liệu chi tiết"):
    @st.cache_data(ttl=600)
    def load_raw(year_filter, status_filter):
        return run_query(f"""
            SELECT o.short_order_id, o.order_purchase_date,
                   p.product_category_name AS category,
                   w.warehouse_name, o.order_status,
                   o.price, o.cost, ROUND(o.price-o.cost,2) AS profit,
                   o.delay_days, o.is_late_delivery
            FROM gold_fact_orders o
            JOIN gold_dim_product p  ON o.ProductKey  = p.ProductKey
            JOIN gold_dim_warehouse w ON o.WarehouseKey = w.WarehouseKey
            JOIN gold_dim_date d      ON o.DateKey      = d.DateKey
            WHERE d.year_number IN ({year_filter})
              AND o.order_status IN ('{status_filter}')
            ORDER BY o.order_purchase_date DESC
            LIMIT 500
        """)
    df_raw = load_raw(year_filter, status_filter)
    st.dataframe(df_raw, use_container_width=True, height=300)
    csv = df_raw.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Tải CSV", csv, "orders.csv", "text/csv")
