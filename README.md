# Zalo Customer Support Tracker

Ứng dụng desktop hỗ trợ theo dõi, quản lý và phân tích các yêu cầu hỗ trợ khách hàng trên các nhóm chat Zalo bằng AI (Gemini). Hệ thống tự động phân biệt tin nhắn yêu cầu hỗ trợ, phản hồi kỹ thuật và giám sát thời gian SLA (Service Level Agreement) theo thời gian thực.

---

## 📚 Tài Liệu Kỹ Thuật & Chuyển Giao

Dự án cung cấp bộ tài liệu kỹ thuật chuẩn mực phục vụ đọc hiểu, chuyển giao và tiếp tục phát triển:
- 📋 [**Software Requirements Specification (SRS)**](file:///d:/Projects/CustomerSupportZalo/docs/SRS.md): Mô tả chi tiết các yêu cầu chức năng (FR-01 đến FR-07), phi chức năng và môi trường vận hành.
- 🏗️ [**Software Architecture Document (SAD)**](file:///d:/Projects/CustomerSupportZalo/docs/SAD.md): Mô tả sơ đồ kiến trúc phân tầng, máy trạng thái Ticket, sơ đồ cơ sở dữ liệu SQLite ERD và hướng dẫn cho lập trình viên mở rộng.

---

## Tính Năng Nổi Bật

- **Cấu hình môi trường bảo mật (.env)**: Tách biệt cấu hình khóa bảo mật và thông tin nhạy cảm khỏi mã nguồn chính. Cung cấp tệp `.env.example` và thiết lập `.gitignore` đầy đủ để tránh sơ suất đẩy khóa bí mật lên Git repository.
- **Đăng nhập bằng quét mã QR tự động (Khuyên dùng)**: Không cần copy-paste cookies thủ công phức tạp. Chỉ cần nhấn nút, hệ thống sẽ mở trình duyệt Zalo Web chính thức để bạn quét mã QR bằng điện thoại, sau đó tự động trích xuất cookies đăng nhập và đóng trình duyệt.
- **Không phụ thuộc thư viện đồ họa ngoài**: Giao diện viết hoàn toàn bằng **Tkinter/Ttk** tiêu chuẩn của Python, chạy mượt mà trực tiếp trên Python 3.14 mới nhất.
- **Đồng bộ tự động & Chống mất mát tin nhắn**: Bật luồng lắng nghe tin nhắn trực tiếp ngay khi mở ứng dụng và đồng bộ song song các tin nhắn cũ từ lần đóng ứng dụng trước.
- **Phân loại AI thông minh**: Sử dụng Gemini API phân tích ngữ nghĩa tin nhắn để phân loại:
  - `REQUEST` (Tin nhắn yêu cầu hỗ trợ mới).
  - `RESPONSE` (Tin nhắn phản hồi từ nhân viên hỗ trợ).
  - `OTHER` (Các tin nhắn thông thường).
- **Thuật toán ghép nối thông minh**: Tự động ghép nối các tin nhắn phản hồi (`RESPONSE`) vào đúng Ticket yêu cầu hỗ trợ (`REQUEST`) chưa xử lý cùng nhóm.
- **Quản lý SLA trực quan**: Theo dõi thời gian tiếp nhận tối đa và xử lý tối đa dưới dạng đếm ngược thời gian thực trên giao diện, tự động đổi màu sắc khi gần quá hạn hoặc quá hạn.
- **Kiểm soát RAM an toàn (Backpressure)**: Giới hạn hàng đợi phân tích AI trên RAM. Khi hàng đợi đầy, tin nhắn sẽ được đệm an toàn dưới SQLite và nạp lại khi hàng đợi trống.
- **Bảo trì tối giản**: Tự động sao lưu database khi tắt ứng dụng (giữ tối đa 5 bản gần nhất) và chạy `VACUUM` dọn dẹp dung lượng thủ công.

---

## Yêu Cầu Hệ Thống

- Hệ điều hành: Windows 10/11
- Phiên bản Python: **Python 3.10** trở lên
- Trình duyệt: **Google Chrome** (để thực hiện tính năng quét mã QR tự động)
- Cơ sở dữ liệu: SQLite (tích hợp sẵn trong Python)
- Giao diện: Tkinter (tích hợp sẵn trong Python)

---

## Hướng Dẫn Cài Đặt & Cấu Hình

1. **Tải mã nguồn về máy**:
   ```bash
   git clone <url-repository>
   cd CustomerSupportZalo
   ```

2. **Cài đặt thư viện cần thiết**:
   ```bash
   pip install -r requirements.txt
   ```
   *(Thư viện bao gồm: `google-generativeai`, `zlapi`, `selenium`, `python-dotenv`)*

3. **Cấu hình API Key (Gemini)**:
   - Đổi tên tệp `.env.example` thành `.env`:
     ```bash
     ren .env.example .env
     ```
   - Mở tệp `.env` bằng trình chỉnh sửa và thay đổi giá trị API Key thực tế của bạn:
     ```env
     GEMINI_API_KEY=your_actual_gemini_api_key_here
     ```

---

## Hướng Dẫn Đăng Nhập Zalo

Ứng dụng hỗ trợ 2 chế độ đăng nhập linh hoạt tại nút **🔑 Đăng nhập Zalo Web** (ở góc trái bên dưới):

### Cách 1: Quét Mã QR Tự Động (Khuyên dùng)
1. Nhấn nút **"🌐 Mở trình duyệt quét mã QR"**.
2. Một cửa sổ Google Chrome nhỏ sẽ hiện ra trang đăng nhập của Zalo Web (`chat.zalo.me`).
3. Mở ứng dụng Zalo trên điện thoại, chọn tính năng quét mã QR và quét mã hiển thị trên màn hình máy tính.
4. Xác nhận đăng nhập trên điện thoại.
5. Ứng dụng sẽ tự động đóng Chrome, lưu phiên đăng nhập và kích hoạt dịch vụ theo dõi.

### Cách 2: Nhập Cookie Thủ Công (Dự phòng)
1. Đăng nhập vào [Zalo Web](https://chat.zalo.me) trên Chrome.
2. Nhấn `F12` -> Tab **Application** -> **Cookies** -> Chọn trang `https://chat.zalo.me`.
3. Sao chép giá trị của `zpsid` và `zpw_sek`.
4. Mở tab **Nhập Cookie Thủ Công** trên ứng dụng, điền số điện thoại, mật khẩu, dán chuỗi cookies và nhấn đăng nhập.

---

## Hướng Dẫn Sử Dụng

1. **Khởi chạy ứng dụng**:
   ```bash
   python main.py
   ```
2. **Thêm nhóm theo dõi**:
   - Nhấn **"Thêm Nhóm Theo Dõi"** -> Tích chọn nhóm -> Xác nhận.
3. **Thiết lập SLA**:
   - Chọn một nhóm chat -> Nhấn **"Thiết lập SLA nhóm"** để chỉnh sửa thời gian.
4. **Giám sát yêu cầu hỗ trợ**:
   - **Cột giữa**: Hiển thị các yêu cầu chưa xử lý (đếm ngược SLA).
     - **Xanh**: An toàn.
     - **Cam**: Sắp hết hạn (SLA tiếp nhận <= 5p hoặc xử lý <= 15p).
     - **Đỏ**: Quá hạn (Trễ X phút).
     - Nhãn `[⚠️ Cần duyệt]` màu vàng xuất hiện khi độ tin cậy AI dưới 70%.
   - **Cột phải**: Hiển thị cây chi tiết tin nhắn của khách hàng và phản hồi của kỹ thuật viên theo thời gian.
5. **Hành động**:
   - Nhấn **"Đóng Yêu Cầu (Resolved)"** để hoàn thành hỗ trợ.
   - Nhấn **"AI Phân Tích Lại"** để phân loại lại nếu phát hiện AI nhận diện sai lệch.

---

## Quản Lý Nhật Ký (Logs)

Các file log nằm ở thư mục `logs/`:
- `app.log`: Nhật ký hệ thống, kết nối Zalo và đồng bộ.
- `ai.log`: Lịch sử phân loại và kết quả từ Gemini API.
- `error.log`: Chỉ ghi nhận lỗi nghiêm trọng.
