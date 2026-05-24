import google.generativeai as genai
import sqlite3
import re
import os
import pandas as pd
from utils.db import DB_PATH, get_schema_info

def init_gemini(api_key: str):
    genai.configure(api_key=api_key)

def extract_sql(text: str) -> str | None:
    """Trích xuất câu lệnh SQL từ phản hồi văn bản của Gemini."""
    patterns = [
        r"```sql\s*(.*?)\s*```",
        r"```\s*(SELECT.*?)\s*```",
        r"(SELECT\s+.+?;)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def run_sql_safe(sql: str) -> tuple[pd.DataFrame | None, str | None]:
    """Thực thi câu lệnh SQL an toàn, ngăn chặn các lệnh phá hoại cấu trúc DB."""
    forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"]
    sql_upper = sql.upper()
    for kw in forbidden:
        if kw in sql_upper:
            return None, f"⚠️ Từ khóa `{kw}` bị từ chối hệ thống. Chỉ cho phép thực hiện truy vấn SELECT dữ liệu."
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return df, None
    except Exception as e:
        return None, str(e)

def chat_with_data(api_key: str, user_question: str, history: list) -> tuple[str, str | None, pd.DataFrame | None]:
    """
    Xử lý câu hỏi người dùng bằng quy trình Agentic RAG 2 bước nâng cao:
    Bước 1: Sử dụng Schema chi tiết từ db.py để biên dịch chính xác thành SQL.
    Bước 2: Sử dụng dữ liệu thực tế thu được để viết báo cáo phân tích chuỗi cung ứng.
    """
    init_gemini(api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    # ── LẤY ĐÚNG NGUYÊN BẢN SCHEMA CHI TIẾT TỪ FILE DB.PY CỦA BẠN ──
    schema_warehouse = get_schema_info()

    # ==========================================
    # NHỊP 1: TEXT-TO-SQL (Đọc Schema để sinh mã lệnh truy vấn)
    # ==========================================
    system_prompt_sql = f"""Bạn là một Chuyên gia Kỹ thuật Dữ liệu cấp cao (Senior Data Engineer).
Bạn có quyền truy cập vào hệ thống SQLite Data Warehouse tầng Gold (Gold Layer) phân tích Chuỗi cung ứng với cấu trúc Schema chi tiết sau:

{schema_warehouse}

NHIỆM VỤ CỦA BẠN:
1. Dựa vào câu hỏi của người dùng và tài liệu Schema chi tiết ở trên, hãy viết duy nhất 1 câu lệnh SQL phù hợp để trích xuất chính xác số liệu cần thiết.
2. Câu lệnh SQL phải tuân thủ nghiêm ngặt cú pháp SQLite (Ví dụ: Xử lý chuỗi thời gian dùng strftime hoặc toán tử nối chuỗi tương ứng).
3. Hãy chú ý JOIN các bảng Dimension (Bảng dim) tương ứng để lấy thông tin dạng 'Chữ văn bản' (Tên ngành hàng, tên kho hàng, tên tháng, bang địa lý) thay vì chỉ lấy mã Key định danh khô khan, giúp báo cáo trực quan hơn.
4. Tự động thêm mệnh đề LIMIT 100 vào cuối câu lệnh nếu người dùng không yêu cầu lấy toàn bộ dữ liệu, nhằm bảo vệ tài nguyên hệ thống.
5. BẮT BUỘC phải bọc câu lệnh SQL trong block định dạng ```sql ... ```.
6. TUYỆT ĐỐI KHÔNG giải thích, không thêm văn bản chào hỏi, không nhận xét ở bước này. Chỉ trả về duy nhất khối mã SQL.

Câu hỏi từ người dùng: "{user_question}"
"""

    # Gọi Gemini sinh câu lệnh SQL
    response_step_1 = model.generate_content(system_prompt_sql)
    sql = extract_sql(response_step_1.text)

    df_result = None
    error = None
    ai_text = ""

    if sql:
        # Chạy câu lệnh SQL do AI sinh ra vào file SQLite thực tế
        df_result, error = run_sql_safe(sql)
        
        if error:
            ai_text = f"⚠️ Hệ thống ghi nhận lỗi biên dịch SQL ngầm từ AI: `{error}`. Vui lòng làm rõ câu hỏi."
        elif df_result is not None and not df_result.empty:
            
            # ==========================================
            # NHỊP 2: DATA INTERPRETATION (Đọc số liệu thật để phân tích)
            # ==========================================
            # Đóng gói tối đa 30 dòng dữ liệu thật làm ngữ cảnh vàng cho AI phân tích
            data_context = df_result.head(30).to_string()
            
            system_prompt_analysis = f"""Bạn là Giám đốc Quản trị Chuỗi cung ứng (Chief Supply Chain Officer / Business Analyst).
Người dùng đã đưa ra bài toán: "{user_question}"

Dưới đây là bảng số liệu thống kê CHÍNH XÁC VÀ THỰC TẾ được trích xuất trực tiếp từ Hệ thống Kho dữ liệu Data Warehouse để giải quyết bài toán trên:
{data_context}

NHIỆM VỤ CỦA BẠN:
1. Hãy dựa ĐÚNG và DUY NHẤT vào kết quả bảng số liệu thực tế ở trên để phân tích và trả lời câu hỏi của người dùng. Không được tự bịa ra hoặc suy diễn các con số nằm ngoài bảng dữ liệu này.
2. Trình bày báo cáo bằng tiếng Việt một cách chuyên nghiệp, cấu trúc luận điểm rõ ràng, lập luận chặt chẽ theo tư duy quản trị doanh nghiệp (Business-oriented).
3. Đơn vị tiền tệ mặc định của dự án là BRL (Real Brazil), hãy luôn ký hiệu là R$ khi xuất hiện các con số doanh thu/chi phí trong lời thoại.
4. Đưa ra các nhận xét, đánh giá ngắn gọn hoặc đề xuất giải pháp vận hành nếu số liệu thể hiện các điểm bất thường (Ví dụ: Tỷ lệ giao hàng trễ của một hãng vận chuyển quá cao, hoặc một SKU đang có nguy cơ cháy kho nghiêm trọng).
5. Tuyệt đối không giải thích về cú pháp lập trình hay nhắc lại câu lệnh SQL ở bước này. Tập trung hoàn toàn vào Insight kinh doanh.
"""
            # Gọi Gemini đọc số liệu thật và viết báo cáo
            response_step_2 = model.generate_content(system_prompt_analysis)
            ai_text = response_step_2.text
        else:
            ai_text = "Hệ thống đã thực thi câu lệnh truy vấn thành công, tuy nhiên hiện tại không tìm thấy bản ghi dữ liệu nào trong kho đáp ứng điều kiện lọc cho câu hỏi của bạn."
    else:
        # Trường hợp người dùng chỉ chào hỏi, chat bâng quơ hoặc hỏi định nghĩa không liên quan đến data
        prompt_chat = f"Bạn là trợ lý ảo phân tích chuỗi cung ứng thông minh Olist. Người dùng nói: '{user_question}'. Hãy phản hồi một cách ngắn gọn, lịch sự bằng tiếng Việt."
        response_chat = model.generate_content(prompt_chat)
        ai_text = response_chat.text

    return ai_text, sql, df_result