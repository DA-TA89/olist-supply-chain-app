import streamlit as st
import pandas as pd
from utils.gemini import chat_with_data

st.set_page_config(page_title="AI Chatbot", page_icon="🤖", layout="wide")

st.markdown("## 🤖 AI Data Analyst Chatbot")
st.markdown("Hỏi bất kỳ câu hỏi nào về dữ liệu chuỗi cung ứng — Gemini sẽ viết SQL và phân tích cho bạn.")

# ── API Key Input ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔑 Cấu hình Gemini")
    api_key = st.text_input("Gemini API Key", type="password",
                             placeholder="AIza...",
                             help="Lấy API key tại: https://aistudio.google.com")
    if api_key:
        st.success("✅ API key đã được nạp")
    else:
        st.warning("⚠️ Cần nhập API key để sử dụng chatbot")

    st.markdown("---")
    st.markdown("### 💡 Gợi ý câu hỏi")
    example_questions = [
        "Top 5 danh mục sản phẩm doanh thu cao nhất?",
        "Kho nào có tỷ lệ giao trễ cao nhất?",
        "Doanh thu theo từng tháng năm 2017?",
        "Sản phẩm nào hay hết hàng nhất?",
    ]
    for q in example_questions:
        # Nhấn nút gợi ý sẽ tự động đẩy câu hỏi vào khung chat
        if st.button(q, use_container_width=True):
            st.session_state["pending_question"] = q

    st.markdown("---")
    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()

# ── Khởi tạo bộ nhớ Chat ───────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# ── Render Lịch sử Chat bằng Giao diện chuẩn của Streamlit ───────────────────
if not st.session_state["messages"]:
    st.info("👋 Xin chào! Tôi là Trợ lý AI. Hãy nhập câu hỏi bên dưới hoặc chọn gợi ý ở thanh bên trái.")

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sql"):
            with st.expander("🔍 Xem SQL đã thực thi"):
                st.code(msg["sql"], language="sql")
        if msg.get("dataframe") is not None:
            df = msg["dataframe"]
            st.dataframe(df, use_container_width=True)
            
            # Vẽ biểu đồ tự động nếu có 1 cột chuỗi và 1 cột số
            if len(df) > 1 and len(df.columns) >= 2:
                try:
                    num_cols = df.select_dtypes(include="number").columns.tolist()
                    str_cols = df.select_dtypes(include="object").columns.tolist()
                    if num_cols and str_cols:
                        import plotly.express as px
                        fig = px.bar(df.head(20), x=str_cols[0], y=num_cols[0], color_discrete_sequence=["#2563eb"])
                        fig.update_layout(height=300, margin=dict(t=10,b=10), plot_bgcolor="white")
                        st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    pass

# ── Xử lý Input MỚI: Bắt sự kiện Enter cực mượt ───────────────────────────────
pending = st.session_state.pop("pending_question", None)
user_input = st.chat_input("Ví dụ: Doanh thu tháng 8/2018 là bao nhiêu?")

# Kích hoạt chat nếu người dùng gõ phím (user_input) HOẶC bấm nút gợi ý (pending)
prompt = user_input or pending

if prompt:
    if not api_key:
        st.error("⚠️ Vui lòng nhập Gemini API Key ở thanh công cụ bên trái trước khi chat!")
        st.stop()

    # 1. In ngay câu hỏi của người dùng ra màn hình
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Xử lý AI suy nghĩ và trả lời
    with st.chat_message("assistant"):
        with st.spinner("🤖 Trợ lý đang đọc dữ liệu và phân tích..."):
            try:
                # Lấy lịch sử ngữ cảnh
                history = [{"role": m["role"], "content": m["content"]} for m in st.session_state["messages"][:-1]]
                
                # Gọi sang file gemini.py của bạn
                ai_text, sql, df_result = chat_with_data(api_key, prompt, history)
                
                st.markdown(ai_text)
                if sql:
                    with st.expander("🔍 Xem SQL đã thực thi"):
                        st.code(sql, language="sql")
                if df_result is not None:
                    st.dataframe(df_result, use_container_width=True)
                
                # Lưu vào bộ nhớ
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": ai_text,
                    "sql": sql,
                    "dataframe": df_result,
                })
            except Exception as e:
                err = str(e)
                if "API_KEY" in err.upper():
                    st.error("❌ API Key không hợp lệ. Vui lòng kiểm tra lại.")
                else:
                    st.error(f"❌ Lỗi: {err}")