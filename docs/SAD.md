# Software Architecture Document (SAD)
## Hệ Thống Zalo Customer Support Tracker

- **Tên dự án**: Zalo Customer Support Tracker
- **Phiên bản kiến trúc**: 1.0.0 (Baseline Architecture)
- **Ngày lập**: 23/07/2026

---

## 1. Tổng Quan Kiến Trúc (Architectural Overview)

Hệ thống **Zalo Customer Support Tracker** được thiết kế theo mô hình **Layered Architecture (Kiến trúc phân tầng)** và **DAO Pattern (Data Access Object Pattern)** nhằm đảm bảo tính cô lập giữa giao diện người dùng (UI), luồng nghiệp vụ (Business Core) và tầng dữ liệu (Data Access Layer).

```
+-----------------------------------------------------------------------+
|                         GUI LAYER (Tkinter/ttk)                       |
|   MainWindow (ui/main_window.py)     |  DashboardWindow (ui/dashboard.py)|
|   Dialogs (ui/dialogs.py)            |  Widgets & Canvas Charts       |
+-----------------------------------++----------------------------------+
                                    ||
                                    \/
+-----------------------------------------------------------------------+
|                    APPLICATION CORE / BUSINESS LOGIC                  |
|   TicketManager (app_core.py)        |  AIService (ai_service.py)     |
|   SLA Calculators & Timers           |  Gemini Classifier / Mock      |
+-----------------------------------++----------------------------------+
                                    ||
                                    \/
+-----------------------------------++----------------------------------+
|                   SERVICES & DATA ACCESS LAYER (DAO)                  |
|   ZaloService (zalo_service.py)      |  TicketDAO (database.py)       |
|   Playwright Automation              |  GroupDAO / MessageDAO         |
+-----------------------------------++----------------------------------+
                                    ||
                                    \/
+-----------------------------------------------------------------------+
|                   INFRASTRUCTURE & PERSISTENCE LAYER                  |
|   SQLite Database (zalo_cs_tracker.db)  | App Config (app_config.json) |
|   Session Storage (zalo_session.json)   | Environment (.env)           |
+-----------------------------------------------------------------------+
```

---

## 2. Chi Tiết Thành Phần Cấu Trúc (Component Architecture)

### 2.1 Tầng Giao Diện (Presentation / GUI Layer)
- **`ui/main_window.py` (`MainWindow`)**:
  - Giao diện chính phân 3 cột (PanedWindow):
    - **Cột 1 (Bên trái)**: Trạng thái kết nối, nút đăng nhập QR, cài đặt SLA nhóm và danh sách các nhóm Zalo đang theo dõi (`group_listbox`).
    - **Cột 2 (Ở giữa)**: Thẻ Ticket đang chờ hỗ trợ (`ticket_cards`) và Bảng tin nhắn thời gian thực (`live_tree`).
    - **Cột 3 (Bên phải)**: Header chi tiết thông tin Ticket kèm thời gian SLA xử lý đếm ngược (tô màu Đỏ/Vàng/Xanh) và Cây phản hồi (`response_tree`).
  - Tự động duy trì vòng lặp 1s (`update_sla_loop`) để đếm ngược SLA và cập nhật UI.
- **`ui/dashboard.py` (`DashboardWindow`)**:
  - Cửa sổ báo cáo & thống kê SLA với 2 Tab:
    - **Tab Nhóm Zalo**: Thẻ KPI động + Bảng dữ liệu + Biểu đồ Canvas so sánh SLA nhóm.
    - **Tab Nhân Viên Hỗ Trợ**: Dropdown lọc theo từng nhóm Zalo + Bảng năng suất nhân viên + Cột Ticket Quá Hạn Xử Lý + Biểu đồ cột Canvas.
- **`ui/dialogs.py`**:
  - Định nghĩa các cửa sổ Modal popup: `LoginDialog`, `SlaSettingsDialog`, `GroupSelectDialog`.
  - Chứa hàm utility `center_window_over_parent(dlg, parent)` tự động căn giữa popup trên đúng màn hình phụ đối với máy tính đa màn hình.

### 2.2 Tầng Nghiệp Vụ & AI (Business Core Layer)
- **`app_core.py` (`TicketManager`)**:
  - Quản lý máy trạng thái Ticket (Ticket State Machine).
  - Tự động tạo Ticket khi nhậntin nhắn `REQUEST`.
  - Tự động liên kết tin nhắn `RESPONSE` của KTV vào Ticket duy nhất đang open của người dùng và chuyển trạng thái sang `PROCESSING`.
  - Xử lý tin nhắn `RESOLVE` của khách hàng và tự động đóng Ticket (`auto_resolved = 1`).
  - Cung cấp hàm static `get_remaining_sla(ticket)` tính toán số phút còn lại của Response SLA và Resolve SLA.
- **`ai_service.py` (`AIService`)**:
  - Giao tiếp với Google Generative AI (Gemini API) hoặc bộ phân loại Mock Classifier fallback.
  - Phân loại ý định tin nhắn: `REQUEST`, `RESPONSE`, `RESOLVE`.

### 2.3 Tầng Dịch Vụ & Truy Xuất Dữ Liệu (Service & Data Access Layer)
- **`zalo_service.py` (`ZaloService`)**:
  - Sử dụng Playwright / Chromium tự động hóa thao tác Zalo Web.
  - Quét mã QR code, quản lý session cookie `zalo_session.json`.
  - Đồng bộ danh sách nhóm chat và bắt sự kiện tin nhắn thời gian thực qua WebSocket / DOM Polling.
- **`database.py` (`GroupDAO`, `TicketDAO`, `MessageDAO`)**:
  - Quản lý SQLite Connection Pool và khởi tạo DB Schema.
  - Cung cấp các phương thức truy vấn tối ưu: `get_dashboard_group_metrics()`, `get_dashboard_staff_metrics()`, `has_overdue_pending_tickets()`, `reopen_ticket()`.

---

## 3. Máy Trạng Thái Ticket (Ticket State Machine)

```
        +------------------+
        |  Tin nhắn REQUEST|
        +--------+---------+
                 |
                 v
           +-----+------+
           |  PENDING   |
           +-----+------+
                 |
                 | (KTV gửi RESPONSE)
                 v
          +------+------+
          | PROCESSING  |
          +------+------+
                 |
                 | (Khách gửi RESOLVE / Bấm nút Check ✅)
                 v
           +-----+------+
           |  RESOLVED  |<---+ (AI auto-resolve auto_resolved=1
           +-----+------+    |  hoặc người dùng đóng thủ công)
                 |           |
                 +-----------+
                 |
                 | (Nút 🔓 Mở Lại Yêu Cầu)
                 v
        +--------+---------+
        | PENDING /        |
        | PROCESSING       |
        +------------------+
```

---

## 4. Sơ Đồ Cơ Sở Dữ Liệu (Database ERD & Schema)

### 4.1 Bảng `groups` (Nhóm Zalo theo dõi)
- `id` (TEXT, PRIMARY KEY): Mã nhóm Zalo.
- `name` (TEXT): Tên nhóm Zalo.
- `is_tracked` (INTEGER): `1` nếu đang theo dõi, `0` nếu không.
- `max_response_time` (INTEGER): SLA thời gian tiếp nhận tối đa (phút).
- `max_resolve_time` (INTEGER): SLA thời gian xử lý tối đa (phút).

### 4.2 Bảng `tickets` (Yêu cầu hỗ trợ)
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT): Mã Ticket.
- `group_id` (TEXT): FK liên kết bảng `groups`.
- `requester_id` (TEXT): Mã ID người yêu cầu (khách hàng).
- `requester_name` (TEXT): Tên khách hàng.
- `request_content` (TEXT): Nội dung yêu cầu hỗ trợ.
- `created_at` (INTEGER): Timestamp thời điểm tạo Ticket (ms).
- `status` (TEXT): Trạng thái (`PENDING`, `PROCESSING`, `RESOLVED`).
- `response_deadline` (INTEGER): Timestamp hạn tiếp nhận (ms).
- `resolve_deadline` (INTEGER): Timestamp hạn xử lý hoàn thành (ms).
- `acknowledged_at` (INTEGER): Timestamp KTV tiếp nhận (ms).
- `resolved_at` (INTEGER): Timestamp đóng Ticket (ms).
- `auto_resolved` (INTEGER): `1` nếu AI tự động đóng, `0` nếu đóng thủ công/chưa đóng.

### 4.3 Bảng `messages` (Lịch sử tin nhắn)
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT).
- `msg_id` (TEXT): Mã tin nhắn Zalo.
- `group_id` (TEXT): FK liên kết nhóm.
- `sender_id` (TEXT): ID người gửi.
- `sender_name` (TEXT): Tên người gửi.
- `content` (TEXT): Nội dung tin nhắn.
- `timestamp` (INTEGER): Thời điểm gửi (ms).

### 4.4 Bảng `responses` (Lịch sử phản hồi KTV)
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT).
- `ticket_id` (INTEGER): FK liên kết `tickets`.
- `responder_id` (TEXT): ID KTV phản hồi.
- `responder_name` (TEXT): Tên KTV phản hồi.
- `content` (TEXT): Nội dung phản hồi.
- `created_at` (INTEGER): Timestamp phản hồi (ms).

---

## 5. Hướng Dẫn Tiếp Nhận & Mở Rộng Dành Cho Lập Trình Viên (Developer Handover)

### 5.1 Cài đặt môi trường phát triển
1. Yêu cầu Python version >= 3.12.
2. Tạo môi trường ảo virtualenv:
   ```bash
   py -3.12 -m venv venv
   venv\Scripts\activate
   ```
3. Cài đặt các thư viện phụ thuộc:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

### 5.2 Khởi chạy ứng dụng
```bash
py -3.12 main.py
```

### 5.3 Chạy bộ kiểm thử tự động (Unit Test Suite)
Bộ unit test suite nằm tại `tests/test_tracker.py` bao gồm **20 unit test cases** bao phủ toàn bộ DAO, AI Classifier, Ticket State Machine, Window Centering và Dashboard Metrics:
```bash
py -3.12 -m unittest discover -s tests
```

### 5.4 Các điểm cần lưu ý khi phát triển tính năng mới
- **Thêm tính năng UI**: Mọi cửa sổ `Toplevel` mới khởi tạo cần gọi `center_window_over_parent(self, parent)` từ `ui/dialogs.py` để đảm bảo định vị chuẩn trên hệ thống đa màn hình.
- **Tối ưu hóa UI**: Tránh việc destroy/re-create widget trong các sự kiện lặp (`<<TreeviewSelect>>` hoặc loop timers). Hãy áp dụng cơ chế **Static Widget Allocation** và cập nhật trực tiếp qua `.configure(text=...)`.
- **Database Migrations**: Nếu bổ sung cột mới vào cơ sở dữ liệu SQLite, cập nhật hàm `initialize_database()` trong `database.py` để tự động kiểm tra `PRAGMA table_info` và thêm cột nếu chưa tồn tại mà không làm mất dữ liệu hiện có.
