# Software Requirements Specification (SRS)
## Hệ Thống Zalo Customer Support Tracker

- **Tên dự án**: Zalo Customer Support Tracker
- **Phiên bản**: 1.1.0
- **Ngày phát hành**: 23/07/2026
- **Trạng thái**: Hoàn thiện & Sẵn sàng vận hành

---

## 1. Giới Thệu & Mục Tiêu Hệ Thống

### 1.1 Mục đích
Tài liệu **Software Requirements Specification (SRS)** định nghĩa đầy đủ các yêu cầu chức năng và phi chức năng cho hệ thống **Zalo Customer Support Tracker**. Tài liệu này làm căn cứ cho việc nghiệm thu, chuyển giao kỹ thuật và tiếp tục phát triển/mở rộng hệ thống trong tương lai.

### 1.2 Phạm vi hệ thống
Hệ thống **Zalo Customer Support Tracker** là ứng dụng Desktop hỗ trợ bộ phận Chăm sóc khách hàng (CS), Kỹ thuật viên (KTV) và Quản lý doanh nghiệp:
- Đăng nhập và tự động đồng bộ danh sách nhóm chat Zalo Web.
- Quản lý danh sách thành viên nhóm và phân công Nhân viên Hỗ trợ theo từng nhóm Zalo.
- Theo dõi tin nhắn hỗ trợ từ khách hàng theo thời gian thực (Real-time Live Listener).
- Sử dụng AI (Google Gemini AI / Rule Engine) để tự động phân loại bản chất tin nhắn: Yêu cầu mới (`REQUEST`), Phản hồi hỗ trợ (`RESPONSE`), hoặc Xác nhận hoàn thành (`RESOLVE`).
- Đếm ngược hạn cam kết chất lượng dịch vụ SLA Tiếp nhận (Response SLA) và SLA Hoàn thành (Resolve SLA).
- Tự động đóng Ticket khi khách hàng xác nhận đã xử lý xong và cung cấp nút mở lại Ticket thủ công.
- Cung cấp Dashboard báo cáo thống kê SLA theo nhóm Zalo và đánh giá năng suất nhân viên hỗ trợ theo từng nhóm.

---

## 2. Yêu Cầu Chức Năng (Functional Requirements - FR)

### FR-01: Đăng Nhập & Quản Lý Session Zalo Web
- **FR-01.1**: Hệ thống cung cấp cơ chế đăng nhập bằng trình duyệt tự động (Playwright/Chromium) qua mã QR code.
- **FR-01.2**: Hệ thống hỗ trợ phương thức nhập Cookie Zalo Web thủ công.
- **FR-01.3**: Tự động lưu trữ session đăng nhập vào `zalo_session.json` và tái sử dụng cho các lần khởi động tiếp theo mà không cần đăng nhập lại.

### FR-02: Theo Dõi Nhóm Zalo & Lắng Nghe Tin Nhắn Thời Gian Thực
- **FR-02.1**: Cho phép tìm kiếm và tích chọn các nhóm Zalo cần đưa vào danh sách theo dõi.
- **FR-02.2**: Lắng nghe tin nhắn mới đến theo thời gian thực (Live Messages Listener) từ các nhóm được chọn.
- **FR-02.3**: Hiển thị bảng tin nhắn live thời gian thực ở Cột thứ 2.

### FR-03: Phân Loại Tin Nhắn Bằng AI & Rule Engine
- **FR-03.1**: Tự động phân loại tin nhắn của người dùng thành 3 nhóm bản chất:
  - `REQUEST`: Khách hàng báo lỗi, đặt câu hỏi hoặc yêu cầu hỗ trợ mới.
  - `RESPONSE`: Nhân viên hỗ trợ trả lời khách hàng, hoặc khách hàng gửi thêm ảnh/thông tin bổ sung cho Ticket hiện tại.
  - `RESOLVE`: Khách hàng cám ơn, báo sự cố đã được khắc phục hoặc xác nhận đóng yêu cầu.
- **FR-03.2**: Tự động lọc bỏ các tin nhắn dạng Sticker, thả biểu tượng cảm xúc, tin nhắn chứa hình ảnh (`[Hình ảnh đính kèm...]`, `[Tập tin...]`, `Photo`, `File`, `Sticker`) khỏi AI Queue và tự động gán nhãn `OTHER`.
- **FR-03.3**: Cung cấp nút `✂️ Tách Ticket` ở Cột 3 cho phép người dùng tích chọn 1 hoặc nhiều tin nhắn phản hồi dưới cây Cột 3 để tách thành Ticket mới độc lập.

### FR-04: Quản Lý Vòng Đời Ticket (Ticket Lifecycle)
- **FR-04.1**: Tạo Ticket mới ở trạng thái `PENDING` khi nhận tin nhắn `REQUEST` từ khách hàng.
- **FR-04.2**: Chuyển Ticket sang `PROCESSING` khi Nhân viên Hỗ trợ được phân công gửi phản hồi (`RESPONSE`).
- **FR-04.3**: Lưu trữ đầy đủ lịch sử trao đổi 2 chiều (kể cả phản hồi bổ sung của Khách hàng) trong bảng `responses` để hiển thị trên cây Cột 3 với chiều cao dòng thoáng (`rowheight=32`).
- **FR-04.4**: Chuyển Ticket sang `RESOLVED` khi:
  - Khách hàng gửi tin nhắn `RESOLVE` (AI tự động đóng Ticket với `auto_resolved = 1` và icon `🤖`).
  - Người dùng bấm nút check `✅ Đóng Yêu Cầu` thủ công (đóng Ticket bởi người dùng với icon `✅`).
- **FR-04.5**: Cho phép mở lại Ticket (`RESOLVED` ➔ `PENDING`/`PROCESSING`) thông qua nút `🔓 Mở Lại Yêu Cầu`.
- **FR-04.6**: Cho phép tách 1 hoặc nhiều tin nhắn phản hồi thành Ticket mới (`✂️ Tách Ticket`). AI phân tích và liên kết thông minh các phản hồi liên quan, tự động xác định trạng thái `PENDING` hay `PROCESSING` cho Ticket mới.

### FR-05: Thiết Lập & Đếm Ngược SLA (Service Level Agreement)
- **FR-05.1**: Cung cấp cửa sổ thiết lập thời gian SLA Tiếp nhận (`max_response_time`) và SLA Xử lý (`max_resolve_time`) cho từng nhóm Zalo (mặc định 15 phút / 60 phút).
- **FR-05.2**: Hiển thị thông số SLA ngay sau tên nhóm ở Cột 1: `[Pending/Processing] Tên Nhóm (ResponseM/ResolveM)`.
- **FR-05.3**: Cảnh báo trễ SLA tiếp nhận ở Cột 1: Nhóm có ticket trễ tiếp nhận được tô màu chữ đỏ `#C0392B`, nền hồng `#FDEDEC` và biểu tượng `⚠️`.
- **FR-05.4**: Hiển thị thời gian SLA xử lý còn lại đếm ngược tự động tại Khung Header Cột 3 với quy tắc đổi màu:
  - 🔴 **Màu Đỏ (`#C0392B`)**: Khi quá hạn SLA (`< 0` phút).
  - 🟡 **Màu Vàng/Cam (`#D35400`)**: Khi còn dưới 10% SLA thời gian xử lý.
  - 🟢 **Màu Xanh Lá (`#27AE60`)**: Khi còn thời gian bình thường.

### FR-06: Dashboard Báo Cáo SLA & Thống Kê Năng Suất
- **FR-06.1**: Cho phép chọn khoảng thời gian lọc thống kê `Từ ngày` đến `Ngày` (mặc định từ ngày 1 đến ngày cuối tháng hiện tại).
- **FR-06.2**: **Tab Thống Kê Nhóm Zalo**:
  - Bảng dữ liệu hiển thị các cột: `Nhóm Zalo`, `Open Trước Kỳ`, `Ticket Mới`, `Ticket Đã Đóng`, `Trễ Tiếp Nhận`, `Trễ Xử Lý`, `Open Tồn`.
  - Các thẻ KPI phía trên hiển thị động số liệu SLA của nhóm Zalo đang được click chọn trong bảng bên dưới.
  - Biểu đồ cột Canvas trực quan so sánh chỉ số giữa các nhóm.
- **FR-06.3**: **Tab Thống Kê Nhân Viên Hỗ Trợ**:
  - Cung cấp Dropdown chọn lọc nhân viên theo từng Nhóm Zalo cụ thể hoặc tất cả các nhóm.
  - Bảng dữ liệu hiển thị các cột: `Nhân Viên / KTV Hỗ Trợ`, `Đã Tiếp Nhận`, `Đã Hoàn Thành (Resolved)`, `Ticket Quá Hạn Xử Lý`, `Ticket Đang Open`.
  - Thẻ KPI và biểu đồ cột năng suất nhân viên chỉ lọc hiển thị các nhân viên thuộc danh sách được phân công.

### FR-07: Giao Diện Multi-Monitor & Lưu Trạng Thái Ứng Dụng
- **FR-07.1**: Tự động lưu kích thước và vị trí cửa sổ ứng dụng vào `app_config.json` khi thoát chương trình và khôi phục khi khởi động lại.
- **FR-07.2**: Tự động canh giữa tất cả các cửa sổ Popup dialog (`LoginDialog`, `SlaSettingsDialog`, `GroupSelectDialog`, `StaffManagementDialog`, `DashboardWindow`) đè lên cửa sổ chính trên bất kỳ màn hình nào trong hệ thống đa màn hình (Multi-monitor setups).

### FR-08: Quản Lý Nhân Viên Hỗ Trợ Theo Nhóm Zalo (Support Staff Management)
- **FR-08.1**: Lấy danh sách toàn bộ thành viên của từng nhóm Zalo (`fetch_group_members`).
- **FR-08.2**: Cho phép chọn và lưu danh sách Nhân viên Hỗ trợ của nhóm qua cửa sổ `StaffManagementDialog` (`👥 QL Nhân Viên`).
- **FR-08.3**: Chỉ công nhận tin nhắn phản hồi từ các nhân viên này là tin tiếp nhận/xử lý Ticket. Tin nhắn từ người khác giữ nguyên Ticket ở trạng thái `PENDING`.

---

## 3. Yêu Cầu Phi Chức Năng (Non-Functional Requirements - NFR)

### NFR-01: Hiệu Năng & Trải Nghiệm Nguồn Tài Nguyên (Performance)
- Vòng lặp đếm ngược SLA quét 1 giây/lần chiếm dưới 0.1% CPU.
- Thao tác click chọn nhóm trong Dashboard cập nhật thẻ KPI dưới 0.05ms (sử dụng cơ chế Static Widget Allocation), không gây chớp nháy hay giật màn hình.

### NFR-02: Độ Cậy & Khả Năng Khôi Phục (Reliability & Fault Tolerance)
- Cơ sở dữ liệu SQLite đảm bảo tính toàn vẹn dữ liệu qua transaction (ACID).
- Tự động bắt ngoại lệ mạng và cơ chế Retry khi mất kết nối Zalo Web.

### NFR-03: Bảo Mật (Security & Privacy)
- Không chia sẻ Cookie Zalo session hay thông tin tài khoản ra ngoài.
- File `.env`, `zalo_session.json` và cơ sở dữ liệu SQLite local được loại trừ khỏi Git repository qua `.gitignore`.
