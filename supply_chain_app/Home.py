import streamlit as st
from utils.db import run_query

st.set_page_config(
    page_title="Supply Chain BI Dashboard",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #3b82f6 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 2rem;
    }
    .main-header h1 { font-size: 2.2rem; font-weight: 700; margin: 0; }
    .main-header p  { font-size: 1rem; opacity: 0.85; margin: 0.4rem 0 0; }

    .kpi-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,.06);
    }
    .kpi-label  { font-size: .8rem; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; }
    .kpi-value  { font-size: 1.9rem; font-weight: 700; color: #0f172a; margin: .25rem 0; }
    .kpi-delta  { font-size: .8rem; }
    .kpi-delta.up   { color: #16a34a; }
    .kpi-delta.down { color: #dc2626; }

    .nav-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        transition: box-shadow .2s;
        cursor: pointer;
    }
    .nav-card:hover { box-shadow: 0 4px 12px rgba(37,99,235,.15); border-color: #2563eb; }
    .nav-icon  { font-size: 2.5rem; }
    .nav-title { font-weight: 700; color: #0f172a; margin: .5rem 0 .25rem; }
    .nav-desc  { font-size: .82rem; color: #64748b; }

    [data-testid="stSidebar"] { background: #f8fafc; }
    .stMetric label { font-size: .78rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🔗 Supply Chain BI Dashboard</h1>
    <p>Hệ thống phân tích hiệu quả chuỗi cung ứng — E-commerce Data Warehouse</p>
</div>
""", unsafe_allow_html=True)

# ── KPI Summary ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_kpis():
    orders = run_query("""
        SELECT
            SUM(price)                                      AS total_revenue,
            COUNT(DISTINCT order_id)                        AS total_orders,
            AVG(price)                                      AS avg_order_value,
            SUM(CASE WHEN is_late_delivery=1 THEN 1 ELSE 0 END)*100.0/COUNT(*) AS late_pct
        FROM gold_fact_orders WHERE is_successful_order = 1
    """)
    inventory = run_query("""
        SELECT SUM(is_stock_out)*100.0/COUNT(*) AS stockout_pct
        FROM gold_fact_inventory
    """)
    shipment = run_query("""
        SELECT AVG(lead_time_days) AS avg_lead_time FROM gold_fact_shipment
    """)
    return orders.iloc[0], inventory.iloc[0], shipment.iloc[0]

with st.spinner("Đang tải dữ liệu tổng quan..."):
    ord_kpi, inv_kpi, ship_kpi = load_kpis()

c1, c2, c3, c4, c5 = st.columns(5)
kpis = [
    (c1, "💰 Tổng Doanh Thu",    f"R$ {ord_kpi['total_revenue']:,.0f}",  "2016 – 2018",       ""),
    (c2, "📦 Tổng Đơn Hàng",    f"{ord_kpi['total_orders']:,}",          "đơn thành công",    ""),
    (c3, "🛒 Giá Trị TB/Đơn",   f"R$ {ord_kpi['avg_order_value']:,.1f}", "per order line",    ""),
    (c4, "🚚 Giao Hàng Trễ",    f"{ord_kpi['late_pct']:.1f}%",           "tỷ lệ trễ",         "down" if ord_kpi['late_pct'] > 10 else "up"),
    (c5, "⏱️ Lead Time TB",     f"{ship_kpi['avg_lead_time']:.1f} ngày", "từ khi đặt→giao",  ""),
]
for col, label, value, delta, cls in kpis:
    with col:
        arrow = "▼" if cls == "down" else ("▲" if cls == "up" else "")
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-delta {cls}">{arrow} {delta}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Navigation Cards ──────────────────────────────────────────────────────────
st.markdown("### 📌 Điều hướng nhanh")
n1, n2, n3, n4, n5 = st.columns(5)
nav_items = [
    (n1, "📊", "Doanh Thu & Đơn Hàng", "Phân tích revenue, order trends, top categories", "pages/1_📊_Doanh_Thu.py"),
    (n2, "📦", "Tồn Kho",              "Stock levels, stockout rate, warehouse capacity",   "pages/2_📦_Ton_Kho.py"),
    (n3, "🚚", "Vận Chuyển",           "Lead time, on-time rate, freight cost",              "pages/3_🚚_Van_Chuyen.py"),
    (n4, "📈", "Dự Báo Nhu Cầu",      "Forecasting doanh thu và tồn kho (Prophet)",         "pages/4_📈_Du_Bao.py"),
    (n5, "🤖", "AI Chatbot",           "Hỏi đáp dữ liệu tự nhiên qua Gemini API",           "pages/5_🤖_Chatbot.py"),
]
for col, icon, title, desc, _ in nav_items:
    with col:
        st.markdown(f"""
        <div class="nav-card">
            <div class="nav-icon">{icon}</div>
            <div class="nav-title">{title}</div>
            <div class="nav-desc">{desc}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Quick Stats ───────────────────────────────────────────────────────────────
st.markdown("### 🗃️ Thông tin Dataset")
d1, d2 = st.columns(2)
with d1:
    st.markdown("**Các bảng trong Data Warehouse (Gold Layer)**")
    table_info = {
        "gold_fact_orders":    "112,650 dòng — dữ liệu đơn hàng",
        "gold_fact_shipment":  "110,197 dòng — dữ liệu vận chuyển",
        "gold_fact_inventory": "7,117,416 dòng — snapshot tồn kho hàng ngày",
        "gold_dim_product":    "32,951 sản phẩm",
        "gold_dim_customer":   "99,441 khách hàng",
        "gold_dim_warehouse":  "6 kho hàng (SP, RJ, MG, PR, RS, BA)",
        "gold_dim_date":       "1,096 ngày (2016–2018)",
    }
    for tbl, desc in table_info.items():
        st.markdown(f"- `{tbl}` — {desc}")

with d2:
    st.markdown("**6 Kho hàng**")
    wh = run_query("SELECT warehouse_name, location_state, capacity FROM gold_dim_warehouse ORDER BY capacity DESC")
    st.dataframe(wh, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("📚 Đồ án: Xây dựng hệ thống Data Warehouse & BI phân tích hiệu quả chuỗi cung ứng — E-commerce")
