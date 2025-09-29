# Bookstore Chatbot 📚🤖

Trợ lý ảo thông minh giúp khách hàng tìm kiếm sách, kiểm tra thông tin, và thực hiện đặt hàng (order) thông qua giao diện chat. Chatbot được xây dựng dựa trên kiến trúc Modular, sử dụng Python, FastAPI cho backend, và SQLite cho cơ sở dữ liệu.

## 1. Kiến Trúc Dự Án (Architecture)

Dự án được tổ chức theo mô hình Chatbot truyền thống với các thành phần chính: NLU (Natural Language Understanding), Dialog Manager (Quản lý hội thoại), Database, và Response Generator.

```
bookstore-chatbot/
│
├── api/                      # Backend API
│   └── main.py               # Server API (FastAPI) nhận request từ frontend
│
├── app/                      # Frontend đơn giản (optional)
│   └── chat.html             # Giao diện chat cơ bản
│
├── bot/                      # Xử lý logic chatbot
│   ├── db.py                 # Kết nối và truy vấn CSDL (SQLite)
│   ├── dialog_manager.py     # Quản lý trạng thái & ngữ cảnh hội thoại (State & Context)
│   ├── nlu.py                # Phân tích ý định (Intent) và thực thể (Entity)
│   └── response.py           # Logic chính: Sinh phản hồi & Điều phối luồng (Flow Control)
│
├── data/                     # Dữ liệu & Schema CSDL
│   ├── sessions/             # Lưu session người dùng (do dialog_manager.py tạo)
│   ├── books.csv             # Dữ liệu sách mẫu (để import)
│   └── schema.sql            # Định nghĩa cấu trúc bảng (Books, Orders, Conversations)
│
├── bookstore.db              # (Tự sinh) File cơ sở dữ liệu SQLite
├── check_db.py               # Script kiểm tra và in dữ liệu các bảng CSDL
├── importbook_db.py          # Script import dữ liệu từ books.csv vào CSDL
├── README.md                 # Hướng dẫn cài đặt & chạy
├── requirements.txt          # Danh sách thư viện Python
├── run.py                    # File chạy server chính (uvicorn)
└── test.py                   # Script chạy chatbot trong console để debug
```

## 2. Công Nghệ Sử Dụng

- Ngôn ngữ: Python 3.8+
- Backend: FastAPI
- CSDL: SQLite
- NLU: Sentence-Transformers (Vietnamese Embedding) kết hợp với Google Gemini API (LLM cho Entity Extraction).
- Quản lý phiên: File JSON (trong thư mục sessions/).

## 3. Cài Đặt và Khởi Chạy

### 3.1. Cài đặt môi trường

Clone repository (nếu có) hoặc tạo cấu trúc thư mục như trên.

Cài đặt các thư viện cần thiết:

```bash
pip install -r requirements.txt
```

Thiết lập Gemini API Key:

Tạo tài khoản và lấy API Key từ Google AI Studio.

Mở file bot/nlu.py và thay thế placeholder key bằng key thực tế của bạn:

```python
# bot/nlu.py
genai.configure(api_key="AIzasaSyCJxQsH_U1-zVNLnm-CKbaNx8ZPGoYhg") # Đặt key thật của bạn vào đây
```

### 3.2. Khởi tạo Cơ sở Dữ liệu

Dự án sử dụng SQLite (bookstore.db). Bạn cần khởi tạo cấu trúc bảng và nhập dữ liệu mẫu.

Khởi tạo CSDL (bookstore.db):
File bot/db.py sẽ tự động chạy init_db() khi đối tượng Database được tạo lần đầu, sử dụng data/schema.sql.

Chạy file check_db.py để tạo CSDL rỗng:

```bash
python check_db.py
```

Nhập dữ liệu sách mẫu:

```bash
python importbook_db.py
```

Lệnh này sẽ đọc dữ liệu từ data/books.csv và chèn vào bảng Books.

### 3.3. Chạy Server Backend

Sử dụng run.py để khởi động server FastAPI bằng Uvicorn:

```bash
python run.py
```

Server sẽ chạy tại: http://0.0.0.0:5000 (hoặc http://127.0.0.1:5000).

## 4. Kiểm Tra và Sử Dụng

### 4.1. Chạy Debug Console

Bạn có thể kiểm tra logic chính của chatbot mà không cần API Backend bằng cách chạy file test.py:

```bash
python test.py
```

Bạn có thể nhập các câu lệnh như:

- xin chào
- có những sách gì
- tìm sách giáo trình python
- tôi muốn mua sách Lập Trình Python nâng cao
- hủy
- tôi tên An, sđt 0987654321 (khi đang trong luồng đặt hàng)

### 4.2. Kiểm tra CSDL

Bạn có thể kiểm tra dữ liệu hiện tại trong CSDL sau khi đặt hàng bằng cách chạy lại:

```bash
python check_db.py
```

Lệnh này sẽ in ra nội dung của các bảng books, orders, và conversations.

### 4.3. Sử dụng API (Sử dụng cho Frontend)

Khi server đang chạy, endpoint chính là:

- Endpoint: /chat
- Method: POST
- Body (JSON):

```json
{
    "session_id": "user_123",
    "user_message": "Tôi muốn mua cuốn nhà giả kim"
}
```

- Response (JSON):

```json
{
    "bot_response": "Bạn muốn mua mấy cuốn ạ? (Còn lại: 10 cuốn)",
    "session_id": "user_123"
}
```

## 5. Cấu Trúc Logic Chính (response.py)

File bot/response.py chứa logic cốt lõi:

- `generate_response(session_id, user_message)`: Hàm chính điều phối mọi thứ.
  - Thực hiện phân tích Intent và Entities (dùng nlu.py).
  - Lấy State (trạng thái) hiện tại từ dialog_manager.py.
  - Xử lý ưu tiên: Nếu đang trong luồng đặt hàng (state bắt đầu bằng order_), gọi `_handle_order_flow()`.
  - Xử lý thông thường: Nếu state là idle, xử lý theo intent (greeting, search_book, order_book, v.v.).
  - Lưu lịch sử hội thoại vào CSDL.

- `_handle_start_order()`: Bắt đầu luồng đặt hàng. Tìm sách, kiểm tra tồn kho, chuẩn hóa entities (nếu có trong tin nhắn đầu), và gọi `_proceed_to_next_step()`.

- `_proceed_to_next_step()`: Logic kiểm tra các trường còn thiếu (quantity, customer_name, phone, address) và chuyển trạng thái/hỏi người dùng trường tiếp theo.

- `_handle_order_flow()`: Xử lý từng bước trong luồng đặt hàng (order_ask_quantity, order_ask_phone, order_confirm, v.v.), bao gồm cả logic sửa thông tin và xác nhận/hủy đơn hàng.
