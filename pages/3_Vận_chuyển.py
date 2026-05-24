import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from utils.db import run_query

st.set_page_config(page_title="Vận Chuyển", page_icon="🚚", layout="wide")

st.markdown("## 🚚 Phân tích vận chuyển")
st.markdown("Theo dõi thời gian giao hàng, tỷ lệ giao đúng hạn, chi phí vận chuyển và hiệu suất từng kho.")

with st.sidebar:
    st.header("🔧 Bộ lọc")
    years = st.multiselect("Năm", [2016, 2017, 2018], default=[2017, 2018])
    if not years:
        years = [2017, 2018]
    year_filter = ",".join(str(y) for y in years)

# ── KPIs ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_ship_kpis(year_filter):
    return run_query(f"""
        SELECT
            AVG(s.lead_time_days)                             AS avg_lead_time,
            AVG(s.total_shipping_days)                        AS avg_ship_days,
            SUM(s.is_late_delivery)*100.0/COUNT(*)            AS late_pct,
            AVG(s.freight_value)                              AS avg_freight,
            SUM(s.freight_value)                              AS total_freight,
            COUNT(*)                                          AS total_shipments
        FROM gold_fact_shipment s
        JOIN gold_dim_date d ON s.PurchaseDateKey = d.DateKey
        WHERE d.year_number IN ({year_filter})
    """)

kpi = load_ship_kpis(year_filter).iloc[0]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("⏱️ Thời gian nhận hàng TB",        f"{kpi['avg_lead_time']:.1f} ngày")
c2.metric("📦 Thời gian ship TB",   f"{kpi['avg_ship_days']:.1f} ngày")
c3.metric("🔴 Tỷ lệ trễ",          f"{kpi['late_pct']:.1f}%", delta_color="inverse")
c4.metric("💸 Phí ship TB",        f"R$ {kpi['avg_freight']:.1f}")
c5.metric("📬 Tổng đơn ship",      f"{kpi['total_shipments']:,}")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 📅 Tỷ lệ giao trễ theo tháng")
    @st.cache_data(ttl=600)
    def load_late_monthly(year_filter):
        return run_query(f"""
            SELECT d.year_number AS year, d.month_number AS month, d.month_name,
                   SUM(s.is_late_delivery)*100.0/COUNT(*) AS late_pct,
                   AVG(s.lead_time_days) AS avg_lead
            FROM gold_fact_shipment s
            JOIN gold_dim_date d ON s.PurchaseDateKey = d.DateKey
            WHERE d.year_number IN ({year_filter})
            GROUP BY d.year_number, d.month_number, d.month_name
            ORDER BY d.year_number, d.month_number
        """)
    df_late = load_late_monthly(year_filter)
    df_late["period"] = df_late["month_name"].str[:3] + " " + df_late["year"].astype(str)
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(x=df_late["period"], y=df_late["late_pct"],
                          name="Tỷ lệ trễ (%)", marker_color="#ef4444",
                          text=df_late["late_pct"].apply(lambda x: f"{x:.0f}%"),
                          textposition="outside"))
    fig1.add_trace(go.Scatter(x=df_late["period"], y=df_late["avg_lead"],
                               name="Lead Time TB (ngày)", yaxis="y2",
                               line=dict(color="#2563eb", width=2.5), mode="lines+markers"))
    fig1.update_layout(
        height=360, margin=dict(t=20, b=20),
        yaxis=dict(title="Tỷ lệ trễ (%)", gridcolor="#f1f5f9"),
        yaxis2=dict(title="Ngày", overlaying="y", side="right"),
        plot_bgcolor="white", legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.markdown("#### 🏭 Thời gian vận chuyển theo kho")
    @st.cache_data(ttl=600)
    def load_wh_leadtime(year_filter):
        return run_query(f"""
            SELECT w.warehouse_name,
                   AVG(s.lead_time_days) AS avg_lead,
                   AVG(s.total_shipping_days) AS avg_ship,
                   SUM(s.is_late_delivery)*100.0/COUNT(*) AS late_pct,
                   AVG(s.freight_value) AS avg_freight
            FROM gold_fact_shipment s
            JOIN gold_dim_warehouse w ON s.WarehouseKey = w.WarehouseKey
            JOIN gold_dim_date d      ON s.PurchaseDateKey = d.DateKey
            WHERE d.year_number IN ({year_filter})
            GROUP BY w.warehouse_name
            ORDER BY avg_lead
        """)
    df_wh = load_wh_leadtime(year_filter)
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(y=df_wh["warehouse_name"], x=df_wh["avg_lead"],
                          orientation="h", name="Lead Time", marker_color="#2563eb",
                          text=df_wh["avg_lead"].apply(lambda x: f"{x:.1f}d"),
                          textposition="outside"))
    fig2.add_trace(go.Bar(y=df_wh["warehouse_name"], x=df_wh["avg_ship"],
                          orientation="h", name="Ship Days", marker_color="#93c5fd",
                          text=df_wh["avg_ship"].apply(lambda x: f"{x:.1f}d"),
                          textposition="outside"))
    fig2.update_layout(barmode="group", height=360, margin=dict(t=20, b=20),
                       xaxis_title="Ngày", plot_bgcolor="white",
                       xaxis=dict(gridcolor="#f1f5f9"))
    st.plotly_chart(fig2, use_container_width=True)

# ── Freight Cost Analysis ──────────────────────────────────────────────────────
st.markdown("#### 💸 Chi phí vận chuyển theo tháng")
@st.cache_data(ttl=600)
def load_freight_monthly(year_filter):
    return run_query(f"""
        SELECT d.year_number AS year, d.month_number AS month, d.month_name,
               SUM(s.freight_value) AS total_freight,
               AVG(s.freight_value) AS avg_freight,
               COUNT(*) AS shipments
        FROM gold_fact_shipment s
        JOIN gold_dim_date d ON s.PurchaseDateKey = d.DateKey
        WHERE d.year_number IN ({year_filter})
        GROUP BY d.year_number, d.month_number, d.month_name
        ORDER BY d.year_number, d.month_number
    """)
df_fr = load_freight_monthly(year_filter)
df_fr["period"] = df_fr["month_name"].str[:3] + " " + df_fr["year"].astype(str)
fig3 = go.Figure()
fig3.add_trace(go.Bar(x=df_fr["period"], y=df_fr["total_freight"],
                      name="Tổng phí ship", marker_color="#8b5cf6",
                      text=df_fr["total_freight"].apply(lambda x: f"R${x/1e3:.0f}K"),
                      textposition="outside"))
fig3.add_trace(go.Scatter(x=df_fr["period"], y=df_fr["avg_freight"],
                           name="Phí TB/đơn", yaxis="y2",
                           line=dict(color="#f97316", width=2.5), mode="lines+markers"))
fig3.update_layout(
    height=340, margin=dict(t=20, b=20),
    yaxis=dict(title="Tổng phí (BRL)", gridcolor="#f1f5f9"),
    yaxis2=dict(title="Phí TB (BRL)", overlaying="y", side="right"),
    plot_bgcolor="white", legend=dict(orientation="h", y=1.1)
)
st.plotly_chart(fig3, use_container_width=True)

# ── Delay Distribution ────────────────────────────────────────────────────────
st.markdown("#### 📊 Phân phối số ngày trễ")
@st.cache_data(ttl=600)
def load_delay_dist(year_filter):
    return run_query(f"""
        SELECT o.delay_days
        FROM gold_fact_orders o
        JOIN gold_dim_date d ON o.DateKey = d.DateKey
        WHERE d.year_number IN ({year_filter})
          AND o.delay_days IS NOT NULL
          AND o.order_status = 'delivered'
        LIMIT 20000
    """)
df_delay = load_delay_dist(year_filter)
fig4 = px.histogram(df_delay, x="delay_days", nbins=60,
                    color_discrete_sequence=["#2563eb"],
                    labels={"delay_days": "Ngày trễ (âm = sớm, dương = trễ)"})
fig4.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Đúng hạn")
fig4.update_layout(height=320, margin=dict(t=20, b=20), plot_bgcolor="white",
                   yaxis=dict(gridcolor="#f1f5f9"))
st.plotly_chart(fig4, use_container_width=True)

# ── Performance Table ──────────────────────────────────────────────────────────
with st.expander("📋 Bảng hiệu suất vận chuyển theo kho"):
    df_wh2 = load_wh_leadtime(year_filter).copy()
    df_wh2.columns = ["Kho", "Thời gian nhận hàng TB (ngày)", "Số ngày ship TB (ngày)", "Tỷ lệ trễ (%)", "Phí ship TB (BRL)"]
    df_wh2 = df_wh2.round(2)
    st.dataframe(df_wh2, use_container_width=True, hide_index=True)
