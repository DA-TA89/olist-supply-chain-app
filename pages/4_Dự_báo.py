import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.db import run_query

st.set_page_config(page_title="Dự Báo Nhu Cầu", page_icon="📈", layout="wide")

st.markdown("## 📈 Dự báo nhu cầu")
st.markdown("Dự báo doanh thu và số đơn hàng sử dụng mô hình **Prophet** (Meta).")

with st.sidebar:
    st.header("⚙️ Cài đặt dự báo")
    forecast_target  = st.radio("Đối tượng dự báo", ["Doanh thu", "Số đơn hàng"])
    forecast_period  = st.slider("Số tháng dự báo", 1, 12, 6)
    granularity      = st.radio("Độ chi tiết", ["Tháng", "Tuần"])
    show_components  = st.checkbox("Hiển thị thành phần (trend, seasonality)", value=True)

    st.markdown("---")
    st.markdown("### ℹ️ Ghi chú dữ liệu")
    st.info(
        "Dữ liệu thực tế kết thúc ngày **2018-09-03** "
        "(tháng 9/2018 chỉ có 3 ngày). "
        "Tháng cuối bị loại để tránh làm lệch mô hình."
    )

# ── Load historical data ──────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_daily_revenue():
    return run_query("""
        SELECT o.order_purchase_date AS ds,
               SUM(o.price)              AS revenue,
               COUNT(DISTINCT o.order_id) AS orders
        FROM gold_fact_orders o
        WHERE o.order_status = 'delivered'
          AND o.order_purchase_date IS NOT NULL
        GROUP BY o.order_purchase_date
        ORDER BY o.order_purchase_date
    """)

with st.spinner("Đang tải dữ liệu lịch sử..."):
    df_hist = load_daily_revenue()
    df_hist["ds"] = pd.to_datetime(df_hist["ds"])
    df_hist = df_hist.dropna()

# ── Aggregate theo tháng / tuần ───────────────────────────────────────────────
if granularity == "Tháng":
    df_agg = df_hist.copy()
    df_agg["ds"] = df_agg["ds"].values.astype("datetime64[M]").astype("datetime64[ms]")
    df_agg = df_agg.groupby("ds").agg({"revenue": "sum", "orders": "sum"}).reset_index()
else:
    df_agg = df_hist.set_index("ds").resample("W-MON").agg(
        {"revenue": "sum", "orders": "sum"}
    ).reset_index()

# ── FIX 1: Bỏ tháng/tuần cuối bị cắt ngắn (incomplete period) ───────────────
# Tháng 9/2018 chỉ có 3 ngày → giá trị bất thường thấp → làm lệch forecast
df_agg = df_agg.iloc[:-1].copy()   # loại period cuối cùng

# ── FIX 2: Loại outlier cực đoan (ngoài 3 sigma) ─────────────────────────────
target_col  = "revenue" if forecast_target == "Doanh thu" else "orders"
df_prophet  = df_agg[["ds", target_col]].rename(columns={target_col: "y"})

mean_y, std_y = df_prophet["y"].mean(), df_prophet["y"].std()
df_prophet = df_prophet[
    (df_prophet["y"] >= mean_y - 3 * std_y) &
    (df_prophet["y"] <= mean_y + 3 * std_y)
].copy()

# ── Run Prophet ───────────────────────────────────────────────────────────────
try:
    from prophet import Prophet

    with st.spinner("🔮 Đang huấn luyện mô hình Prophet..."):
        m = Prophet(
            weekly_seasonality  = (granularity == "Tuần"),
            daily_seasonality   = False,
            # FIX 3: Đổi sang additive — multiplicative gây khuếch đại khi trend âm/thấp
            seasonality_mode    = "additive",
            # FIX 4: Tăng changepoint_prior → mô hình bám sát trend thực tế hơn
            changepoint_prior_scale = 0.3,
            # FIX 5: Giới hạn yearly_seasonality_order thấp để tránh overfit (chỉ 24 tháng)
            yearly_seasonality  = 5,
        )
        m.fit(df_prophet)

        # Tạo future dataframe thủ công (tránh lỗi pandas >= 2.2)
        if granularity == "Tháng":
            future_dates = pd.date_range(
                start   = df_prophet["ds"].min(),
                periods = len(df_prophet) + forecast_period,
                freq    = "MS"
            )
        else:
            future_dates = pd.date_range(
                start   = df_prophet["ds"].min(),
                periods = len(df_prophet) + forecast_period * 4,
                freq    = "W"
            )
        future   = pd.DataFrame({"ds": future_dates})
        forecast = m.predict(future)

        # FIX 6: Clamp giá trị âm về 0 (doanh thu / đơn hàng không thể âm)
        forecast["yhat"]       = forecast["yhat"].clip(lower=0)
        forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0)
        forecast["yhat_upper"] = forecast["yhat_upper"].clip(lower=0)

    # ── Main forecast chart ───────────────────────────────────────────────────
    st.markdown(f"#### 🔮 Dự báo {forecast_target} — {forecast_period} tháng tới")

    forecast_future = forecast[forecast["ds"] > df_prophet["ds"].max()]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_prophet["ds"], y=df_prophet["y"],
        mode="lines+markers", name="Thực tế",
        line=dict(color="#2563eb", width=2), marker=dict(size=4)
    ))
    fig.add_trace(go.Scatter(
        x=forecast_future["ds"], y=forecast_future["yhat"],
        mode="lines+markers", name="Dự báo",
        line=dict(color="#f97316", width=2.5, dash="dash"), marker=dict(size=5)
    ))
    fig.add_trace(go.Scatter(
        x=pd.concat([forecast_future["ds"], forecast_future["ds"][::-1]]),
        y=pd.concat([forecast_future["yhat_upper"], forecast_future["yhat_lower"][::-1]]),
        fill="toself", fillcolor="rgba(249,115,22,0.12)",
        line=dict(color="rgba(255,255,255,0)"),
        name="Khoảng tin cậy 80%"
    ))

    # Đường phân cách — tách add_vline và add_annotation để tránh bug Plotly _mean()
    split_date_str = df_prophet["ds"].max().isoformat()
    fig.add_vline(x=split_date_str, line_dash="dot", line_color="#94a3b8")
    fig.add_annotation(
        x=split_date_str, y=1, yref="paper",
        text="Bắt đầu dự báo", showarrow=False,
        xanchor="left", yanchor="top",
        font=dict(color="#64748b", size=11),
        bgcolor="white", borderpad=3
    )

    unit = "BRL" if forecast_target == "Doanh thu" else "đơn"
    fig.update_layout(
        height=430, margin=dict(t=20, b=20),
        yaxis_title=f"{forecast_target} ({unit})",
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#f1f5f9", rangemode="tozero"),
        legend=dict(orientation="h", y=1.08)
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Forecast table ────────────────────────────────────────────────────────
    st.markdown("#### 📋 Bảng dự báo chi tiết")
    df_display = forecast_future[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    df_display.columns = ["Thời gian", "Dự báo", "Thấp nhất", "Cao nhất"]
    df_display["Thời gian"] = df_display["Thời gian"].dt.strftime(
        "%Y-%m" if granularity == "Tháng" else "%Y-%W"
    )
    for col in ["Dự báo", "Thấp nhất", "Cao nhất"]:
        if forecast_target == "Doanh thu":
            df_display[col] = df_display[col].apply(lambda x: f"R$ {x:,.0f}")
        else:
            df_display[col] = df_display[col].apply(lambda x: f"{x:,.0f}")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── Components ────────────────────────────────────────────────────────────
    if show_components:
        st.markdown("#### 🔍 Phân tích thành phần xu hướng")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**📈 Trend (xu hướng dài hạn)**")
            fig_t = go.Figure()
            fig_t.add_trace(go.Scatter(
                x=forecast["ds"], y=forecast["trend"],
                line=dict(color="#2563eb", width=2), name="Trend"
            ))
            fig_t.update_layout(height=280, margin=dict(t=10, b=10),
                                 plot_bgcolor="white",
                                 yaxis=dict(gridcolor="#f1f5f9", rangemode="tozero"))
            st.plotly_chart(fig_t, use_container_width=True)

        with c2:
            st.markdown("**📆 Seasonality (mùa vụ theo năm)**")
            if "yearly" in forecast.columns:
                fig_s = go.Figure()
                df_seas   = forecast[["ds", "yearly"]].dropna().copy()
                df_seas["month"] = df_seas["ds"].dt.month
                df_seas_m = df_seas.groupby("month")["yearly"].mean().reset_index()
                month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                               "Jul","Aug","Sep","Oct","Nov","Dec"]
                df_seas_m["month_name"] = df_seas_m["month"].apply(lambda x: month_names[x-1])
                fig_s.add_trace(go.Bar(
                    x=df_seas_m["month_name"], y=df_seas_m["yearly"],
                    marker_color="#8b5cf6"
                ))
                fig_s.update_layout(height=280, margin=dict(t=10, b=10),
                                     plot_bgcolor="white",
                                     yaxis=dict(gridcolor="#f1f5f9"))
                st.plotly_chart(fig_s, use_container_width=True)

    # ── Summary metrics ───────────────────────────────────────────────────────
    st.markdown("#### 📊 Tóm tắt kết quả dự báo")
    hist_avg     = df_prophet["y"].tail(12).mean()
    forecast_avg = forecast_future["yhat"].mean()
    growth       = (forecast_avg - hist_avg) / hist_avg * 100 if hist_avg else 0

    m1, m2, m3 = st.columns(3)
    prefix = "R$ " if forecast_target == "Doanh thu" else ""
    m1.metric("📊 TB Lịch Sử (12 kỳ gần nhất)", f"{prefix}{hist_avg:,.0f}")
    m2.metric("🔮 TB Dự Báo",                   f"{prefix}{forecast_avg:,.0f}")
    m3.metric("📈 Tăng trưởng dự kiến",         f"{growth:+.1f}%", delta_color="normal")

    # ── Model info box ────────────────────────────────────────────────────────
    with st.expander("🔬 Thông số mô hình đã dùng"):
        st.markdown("""
| Tham số | Giá trị | Lý do |
|---|---|---|
| `seasonality_mode` | `additive` | Tránh khuếch đại sai số khi trend thấp |
| `changepoint_prior_scale` | `0.3` | Bám sát thay đổi xu hướng thực tế hơn |
| `yearly_seasonality` | `5` (Fourier terms) | Tránh overfit với chỉ 24 tháng dữ liệu |
| Loại period cuối | ✅ | Tháng 9/2018 chỉ có 3 ngày — incomplete |
| Clamp âm về 0 | ✅ | Doanh thu/đơn hàng không thể âm |
| Loại outlier 3σ | ✅ | Loại điểm bất thường trước khi fit |
        """)

except ImportError:
    st.error("⚠️ Thư viện Prophet chưa được cài đặt.")
    st.code("pip install prophet", language="bash")

    st.markdown("#### 📅 Dữ liệu lịch sử (chưa có dự báo)")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Scatter(
        x=df_prophet["ds"], y=df_prophet["y"],
        mode="lines", name="Thực tế",
        line=dict(color="#2563eb", width=2)
    ))
    fig_hist.update_layout(height=380, margin=dict(t=20, b=20),
                            plot_bgcolor="white", yaxis=dict(gridcolor="#f1f5f9"))
    st.plotly_chart(fig_hist, use_container_width=True)

except Exception as e:
    st.error(f"❌ Lỗi khi chạy mô hình: {str(e)}")
    st.exception(e)