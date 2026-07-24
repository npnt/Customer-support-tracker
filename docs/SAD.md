# Software Architecture Document (SAD)
## Hệ Thống Zalo Customer Support Tracker

- **Tên dự án**: Zalo Customer Support Tracker
- **Phiên bản kiến trúc**: 1.1.0
- **Ngày lập**: 23/07/2026

---

## 1. Tổng Quan Kiến Trúc (Architectural Overview)

Hệ thống **Zalo Customer Support Tracker** được thiết kế theo mô hình **Layered Architecture (Kiến trúc phân tầng)** và **DAO Pattern (Data Access Object Pattern)** nhằm đảm bảo tính cô lập giữa giao diện người dùng (UI), luồng nghiệp vụ (Business Core) và tầng dữ liệu (Data Access Layer).

```
+-----------------------------------------------------------------------+
|                         GUI LAYER (Tkinter/ttk)                       |
|   MainWindow (ui/main_window.py)     |  DashboardWindow (ui/dashboard.py)|
|   Dialogs & StaffManagementDialog    |  Widgets & Canvas Charts       |
+-----------------------------------++----------------------------------+
                                    ||
                                    \/
+-----------------------------------------------------------------------+
|                    APPLICATION CORE / BUSINESS LOGIC                  |
|   TicketManager (app_core.py)        |  AIService (ai_service.py)     |
|   SLA Calculators & Timers           |  Support Staff Filter Rules    |
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
    - **Cột 1 (Bên trái)**: Trạng thái kết nối, nút đăng nhập QR, nút `⚙️ Thiết lập SLA`, nút `👥 QL Nhân Viên` và danh sách các nhóm Zalo đang theo dõi (`group_listbox` tô màu trực quan 3 mức độ trễ SLA: Cam `⚠️`, Tím `🛠️`, Đỏ `🚨`).
    - **Cột 2 (Ở giữa)**: Thẻ Ticket đang chờ hỗ trợ (`ticket_cards`) và Bảng tin nhắn thời gian thực (`live_tree`).
    - **Cột 3 (Bên phải)**: Header chi tiết thông tin Ticket kèm thời gian SLA xử lý đếm ngược (tô màu Đỏ/Vàng/Xanh), Cây phản hồi trao đổi 2 chiều (`response_tree` có `rowheight=32`), và bộ nút hành động (`✅ Đóng Yêu Cầu`, `🔓 Mở Lại Yêu Cầu`, `✂️ Tách Ticket`, `🔗 Gán Vào Ticket Khác`).
- **`ui/dashboard.py` (`DashboardWindow`)**:
  - Cửa sổ báo cáo & thống kê SLA với 2 Tab:
    - **Tab Nhóm Zalo**: Thẻ KPI động + Bảng dữ liệu + Biểu đồ Canvas so sánh SLA nhóm.
    - **Tab Nhân Viên Hỗ Trợ**: Dropdown lọc theo từng nhóm Zalo + Bảng năng suất nhân viên (chỉ lọc nhân viên được phân công) + Cột Ticket Quá Hạn Xử Lý + Biểu đồ cột Canvas.
- **`ui/dialogs.py`**:
  - Định nghĩa các cửa sổ Modal popup: `LoginDialog`, `SlaSettingsDialog`, `GroupSelectDialog`, `StaffManagementDialog`, `MergeTicketDialog`.
  - Tích hợp Combobox chọn nhóm trực tiếp trong `StaffManagementDialog` và bảng chọn Ticket mục tiêu trong `MergeTicketDialog`.
  - Chứa hàm utility `center_window_over_parent(dlg, parent)` tự động căn giữa popup (bảo toàn kích thước `dw x dh + cx + cy`) trên đúng màn hình phụ đối với máy tính đa màn hình.

### 2.2 Tầng Nghiệp Vụ & AI (Business Core Layer)
- **`app_core.py` (`TicketManager`, `AppCore`)**:
  - Quản lý máy trạng thái Ticket (Ticket State Machine).
  - Lọc bỏ triệt để các tin nhắn hình ảnh, file đính kèm, photo (`is_ai_eligible_message`) khỏi AI Queue và tự động gán nhãn `OTHER`.
  - Tự động tạo Ticket khi nhận tin nhắn `REQUEST`.
  - Lưu trữ đầy đủ tin nhắn phản hồi 2 chiều của cả Khách hàng và KTV vào bảng `responses`. Chỉ chuyển Ticket `PENDING` ➔ `PROCESSING` khi người phản hồi là **Nhân viên Hỗ trợ được phân công**.
  - Thực hiện tách Ticket (`split_ticket`): Chuyển phản hồi được chọn thành Ticket mới và liên kết thông minh các phản hồi liên quan.
  - Thực hiện gán/gộp Ticket (`merge_ticket`): Chuyển tin nhắn yêu cầu gốc của Ticket nguồn thành phản hồi của Ticket đích, di chuyển lịch sử phản hồi và dọn dẹp CSDL.
  - Xử lý tin nhắn `RESOLVE` của khách hàng và tự động đóng Ticket (`auto_resolved = 1`).
- **`ai_service.py` (`AIService`)**:
  - Phân loại ý định tin nhắn (`REQUEST`, `RESPONSE`, `RESOLVE`, `OTHER`).
  - Hệ thống Prompt cấm tuyệt đối phân loại chỉ báo hình ảnh thành `REQUEST`/`RESPONSE`/`RESOLVE` và ưu tiên khớp `sender_name` với `requester_name`.

### 2.3 Tầng Dịch Vụ & Truy Xuất Dữ Liệu (Service & Data Access Layer)
- **`zalo_service.py` (`ZaloService`)**:
  - Quét mã QR code, quản lý session cookie `zalo_session.json`.
  - Bắt sự kiện tin nhắn thời gian thực qua WebSocket / DOM Polling.
  - Bổ sung hàm `fetch_group_members(group_id)` truy vấn danh sách toàn bộ thành viên nhóm.
- **`database.py` (`GroupDAO`, `TicketDAO`, `MessageDAO`)**:
  - Quản lý bảng `group_support_staff` và các phương thức `get_group_support_staff()`, `set_group_support_staff()`, `is_support_staff()`.

---

## 3. Máy Trạng Thái Ticket & Quy Tắc Lọc Nhân Viên (Ticket State Machine & Staff Filter)

```
        +------------------+
        |  Tin nhắn REQUEST|
        +--------+---------+
                 |
                 v
           +-----+------+
           |  PENDING   |<-------------------+ (Khách hàng hoặc thành viên khác nhắn
           +-----+------+                    |  --> Giữ nguyên trạng thái PENDING)
                 |                           |
                 | (KTV thuộc group_support_staff gửi RESPONSE)
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

### 4.2 Bảng `group_support_staff` (Nhân viên Hỗ trợ được phân công)
- `group_id` (TEXT, PRIMARY KEY): Mã nhóm Zalo (FK).
- `staff_name` (TEXT, PRIMARY KEY): Tên nhân viên/KTV hỗ trợ được tích chọn.

### 4.3 Bảng `tickets` (Yêu cầu hỗ trợ)
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT): Mã Ticket.
- `group_id` (TEXT): FK liên kết bảng `groups`.
- `requester_name` (TEXT): Tên khách hàng.
- `request_content` (TEXT): Nội dung yêu cầu hỗ trợ.
- `status` (TEXT): Trạng thái (`PENDING`, `PROCESSING`, `RESOLVED`).
- `acknowledged_at` (INTEGER): Timestamp KTV chính thức tiếp nhận (ms).
- `resolved_at` (INTEGER): Timestamp đóng Ticket (ms).
- `auto_resolved` (INTEGER): `1` nếu AI tự động đóng, `0` nếu đóng thủ công/chưa đóng.

### 4.4 Bảng `responses` (Lịch sử phản hồi KTV)
- `id` (INTEGER, PRIMARY KEY AUTOINCREMENT).
- `ticket_id` (INTEGER): FK liên kết `tickets`.
- `responder_name` (TEXT): Tên KTV hỗ trợ phản hồi.
- `response_content` (TEXT): Nội dung phản hồi.
- `created_at` (INTEGER): Timestamp phản hồi (ms).

---

## 5. Hướng Dẫn Chạy Kiểm Thử (Unit Tests)

Chạy bộ kiểm thử tự động gồm **21 unit test cases**:
```bash
py -3.12 -m unittest discover -s tests
```
