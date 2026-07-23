import tkinter as tk
from tkinter import ttk, messagebox
import json

def center_window_over_parent(dlg, parent=None):
    """
    Căn giữa cửa sổ popup (dlg) đè lên cửa sổ cha (parent) trên đúng màn hình đang chứa cửa sổ cha (kể cả hệ thống nhiều màn hình).
    """
    dlg.update_idletasks()
    
    dw = dlg.winfo_width()
    dh = dlg.winfo_height()
    if dw <= 1:
        dw = dlg.winfo_reqwidth()
    if dh <= 1:
        dh = dlg.winfo_reqheight()

    if parent and parent.winfo_exists():
        parent.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()

        cx = px + max(0, (pw - dw) // 2)
        cy = py + max(0, (ph - dh) // 2)
    else:
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        cx = max(0, (sw - dw) // 2)
        cy = max(0, (sh - dh) // 2)

    dlg.geometry(f"+{cx}+{cy}")

class LoginDialog(tk.Toplevel):
    def __init__(self, zalo_service, parent=None):
        super().__init__(parent)
        self.title("Đăng nhập tài khoản Zalo")
        self.geometry("480x480")
        self.zalo_service = zalo_service
        self.result = None
        self.resizable(False, False)
        
        # Làm cho dialog ở dạng modal
        self.transient(parent)
        self.grab_set()
        
        self.init_ui()
        center_window_over_parent(self, parent)

    def init_ui(self):
        # Notebook cho 2 chế độ đăng nhập
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Đăng nhập bằng mã QR
        self.qr_tab = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(self.qr_tab, text="Quét Mã QR Tự Động")
        
        tk.Label(self.qr_tab, text="Đăng nhập bằng mã QR (Khuyên dùng)", font=("Arial", 12, "bold"), fg="#2C3E50").pack(pady=(10, 10))
        
        instructions = (
            "Hướng dẫn:\n"
            "1. Nhấn nút 'Mở trình duyệt quét QR' bên dưới.\n"
            "2. Trình duyệt Chrome sẽ mở ra trang Zalo Web.\n"
            "3. Quét mã QR hiển thị trên màn hình bằng điện thoại của bạn.\n"
            "4. Hệ thống sẽ tự động bắt lấy cookies đăng nhập và đóng trình duyệt."
        )
        instructions_lbl = tk.Label(self.qr_tab, text=instructions, font=("Arial", 9), justify="left", fg="#555555", bg="#F8F9FA", bd=1, relief="solid", padx=10, pady=10, wraplength=400)
        instructions_lbl.pack(fill="x", pady=10)
        
        self.status_lbl = ttk.Label(self.qr_tab, text="Trạng thái: Sẵn sàng", font=("Arial", 10, "italic"))
        self.status_lbl.pack(pady=15)
        
        self.open_qr_btn = ttk.Button(self.qr_tab, text="🌐 Mở trình duyệt quét mã QR", command=self.on_open_qr)
        self.open_qr_btn.pack(pady=10, ipady=5)

        # Tab 2: Nhập Cookie thủ công
        self.manual_tab = ttk.Frame(self.notebook, padding="15")
        self.notebook.add(self.manual_tab, text="Nhập Cookie Thủ Công")
        
        # Phone
        ttk.Label(self.manual_tab, text="Số điện thoại đăng ký Zalo:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.phone_entry = ttk.Entry(self.manual_tab, width=40)
        self.phone_entry.pack(fill="x", pady=(0, 10))

        # Password
        ttk.Label(self.manual_tab, text="Mật khẩu Zalo:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.pass_entry = ttk.Entry(self.manual_tab, show="*", width=40)
        self.pass_entry.pack(fill="x", pady=(0, 10))

        # Cookies
        ttk.Label(self.manual_tab, text="Chuỗi Cookies (chứa zpsid, zpw_sek...):", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.cookies_text = tk.Text(self.manual_tab, height=5, width=40)
        self.cookies_text.pack(fill="both", expand=True, pady=(0, 10))

        # IMEI
        ttk.Label(self.manual_tab, text="Mã IMEI (Để trống để tự sinh ngẫu nhiên):", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.imei_entry = ttk.Entry(self.manual_tab, width=40)
        self.imei_entry.pack(fill="x", pady=(0, 15))
        
        # Buttons manual
        btn_frame = ttk.Frame(self.manual_tab)
        btn_frame.pack(fill="x")
        self.login_btn = ttk.Button(btn_frame, text="Đăng nhập", command=self.on_manual_login)
        self.login_btn.pack(side="left", padx=(0, 10))
        self.cancel_btn = ttk.Button(btn_frame, text="Hủy", command=self.destroy)
        self.cancel_btn.pack(side="left")

    def on_open_qr(self):
        self.open_qr_btn.configure(state="disabled")
        self.zalo_service.start_qr_login(
            progress_cb=self.on_qr_progress,
            success_cb=self.on_qr_success,
            error_cb=self.on_qr_error
        )

    def on_qr_progress(self, msg):
        self.after(0, lambda: self.status_lbl.configure(text=f"Trạng thái: {msg}"))

    def on_qr_success(self, cookies, imei=None, user_agent=None):
        self.after(0, self.finish_qr_login, cookies, imei, user_agent)

    def on_qr_error(self, err_msg):
        self.after(0, self.finish_qr_login_error, err_msg)

    def finish_qr_login(self, cookies, imei=None, user_agent=None):
        self.result = {
            "phone": "0000000000",
            "password": "placeholder_pass",
            "cookies": cookies,
            "imei": imei,
            "user_agent": user_agent
        }
        messagebox.showinfo("Thành công", "Đăng nhập QR thành công!")
        self.destroy()

    def finish_qr_login_error(self, err_msg):
        messagebox.showerror("Lỗi đăng nhập QR", err_msg)
        self.status_lbl.configure(text="Trạng thái: Đăng nhập thất bại")
        self.open_qr_btn.configure(state="normal")

    def on_manual_login(self):
        phone = self.phone_entry.get().strip()
        password = self.pass_entry.get().strip()
        cookies_raw = self.cookies_text.get("1.0", "end").strip()
        
        if not phone or not password or not cookies_raw:
            messagebox.showwarning("Cảnh báo", "Vui lòng điền đầy đủ các thông tin bắt buộc.")
            return

        cookies_dict = {}
        try:
            cookies_dict = json.loads(cookies_raw)
        except Exception:
            parts = cookies_raw.split(";")
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies_dict[k.strip()] = v.strip()

        self.result = {
            "phone": phone,
            "password": password,
            "cookies": cookies_dict,
            "imei": self.imei_entry.get().strip() or None
        }
        self.destroy()

    def get_data(self):
        return self.result

class SlaSettingsDialog(tk.Toplevel):
    def __init__(self, group_name, current_sla=None, parent=None):
        super().__init__(parent)
        self.title(f"Thiết lập SLA - {group_name}")
        self.geometry("380x250")
        self.resizable(False, False)
        self.result = None
        
        self.transient(parent)
        self.grab_set()

        self.current_sla = current_sla or {"max_response_time": 15, "max_resolve_time": 60}
        self.init_ui()
        center_window_over_parent(self, parent)

    def init_ui(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        # Response SLA
        ttk.Label(main_frame, text="Thời gian tiếp nhận tối đa (Response SLA - phút):", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.response_var = tk.IntVar(value=self.current_sla["max_response_time"])
        self.response_spin = ttk.Spinbox(main_frame, from_=1, to=1440, textvariable=self.response_var, width=20)
        self.response_spin.pack(anchor="w", pady=(0, 15))

        # Resolve SLA
        ttk.Label(main_frame, text="Thời gian xử lý hoàn thành tối đa (Resolve SLA - phút):", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.resolve_var = tk.IntVar(value=self.current_sla["max_resolve_time"])
        self.resolve_spin = ttk.Spinbox(main_frame, from_=1, to=10080, textvariable=self.resolve_var, width=20)
        self.resolve_spin.pack(anchor="w", pady=(0, 20))

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x")
        
        self.save_btn = ttk.Button(btn_frame, text="Lưu cấu hình", command=self.on_save)
        self.save_btn.pack(side="left", padx=(0, 10))
        
        self.cancel_btn = ttk.Button(btn_frame, text="Hủy", command=self.destroy)
        self.cancel_btn.pack(side="left")

    def on_save(self):
        try:
            raw_resp = self.response_spin.get().strip() or str(self.response_var.get())
            raw_res = self.resolve_spin.get().strip() or str(self.resolve_var.get())
            resp = int(raw_resp)
            res = int(raw_res)
            if resp <= 0 or res <= 0:
                messagebox.showerror("Lỗi", "Thời gian SLA phải lớn hơn 0 phút.")
                return
            self.result = {
                "max_response_time": resp,
                "max_resolve_time": res
            }
            self.destroy()
        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng nhập giá trị số hợp lệ.")

    def get_data(self):
        return self.result

class GroupSelectDialog(tk.Toplevel):
    def __init__(self, zalo_groups, tracked_group_ids, zalo_service=None, parent=None):
        super().__init__(parent)
        self.title("Chọn nhóm Zalo để theo dõi")
        self.geometry("420x520")
        self.result = None
        self.zalo_service = zalo_service
        
        self.transient(parent)
        self.grab_set()

        self.zalo_groups = zalo_groups
        self.tracked_group_ids = tracked_group_ids
        self.checkbox_vars = {}
        self.group_names = {}
        self.group_checkbuttons = {}
        
        self.init_ui()
        center_window_over_parent(self, parent)

    def init_ui(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Danh sách nhóm chat Zalo của bạn:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))

        # Thanh tìm kiếm nhóm thời gian thực
        search_frame = ttk.LabelFrame(main_frame, text="🔍 Tìm kiếm nhóm", padding="5")
        search_frame.pack(fill="x", pady=(0, 8))
        
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<KeyRelease>", self.on_search_changed)
        
        clear_search_btn = ttk.Button(search_frame, text="✖ Clear", command=self.on_clear_search)
        clear_search_btn.pack(side="right")

        # Nhập ID thủ công dự phòng
        manual_frame = ttk.LabelFrame(main_frame, text="Thêm bằng Group ID thủ công (Dự phòng)", padding="5")
        manual_frame.pack(fill="x", pady=(0, 10))
        
        self.manual_id_entry = ttk.Entry(manual_frame)
        self.manual_id_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        add_id_btn = ttk.Button(manual_frame, text="+ Thêm ID", command=self.on_add_manual_id)
        add_id_btn.pack(side="right")

        # Khung chứa danh sách nhóm và thanh cuộn gọn gàng
        list_container = ttk.Frame(main_frame)
        list_container.pack(fill="both", expand=True, pady=(0, 15))

        list_canvas = tk.Canvas(list_container, borderwidth=1, relief="sunken")
        list_scroll = ttk.Scrollbar(list_container, orient="vertical", command=list_canvas.yview)
        self.scroll_frame = ttk.Frame(list_canvas)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: list_canvas.configure(
                scrollregion=list_canvas.bbox("all")
            )
        )

        def _on_canvas_configure(e):
            list_canvas.itemconfig(canvas_win, width=e.width)

        list_canvas.bind("<Configure>", _on_canvas_configure)
        canvas_win = list_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        list_canvas.configure(yscrollcommand=list_scroll.set)

        list_scroll.pack(side="right", fill="y")
        list_canvas.pack(side="left", fill="both", expand=True)

        for group in self.zalo_groups:
            gid = str(group["id"])
            name = str(group["name"])
            self.group_names[gid] = name
            
            var = tk.BooleanVar(value=(gid in [str(tid) for tid in self.tracked_group_ids]))
            self.checkbox_vars[gid] = var
            
            cb = ttk.Checkbutton(self.scroll_frame, text=f"{name} (ID: {gid})", variable=var, padding="5")
            cb.pack(anchor="w", fill="x")
            self.group_checkbuttons[gid] = cb

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x")
        
        self.ok_btn = ttk.Button(btn_frame, text="Xác nhận", command=self.on_ok)
        self.ok_btn.pack(side="left", padx=(0, 10))
        
        self.cancel_btn = ttk.Button(btn_frame, text="Hủy", command=self.destroy)
        self.cancel_btn.pack(side="left")

    def on_search_changed(self, event=None):
        keyword = self.search_entry.get().strip().lower()
        for gid, cb in self.group_checkbuttons.items():
            name = self.group_names.get(gid, "")
            search_text = f"{name} {gid}".lower()
            if not keyword or keyword in search_text:
                cb.pack(anchor="w", fill="x")
            else:
                cb.pack_forget()

    def on_clear_search(self):
        self.search_entry.delete(0, tk.END)
        self.on_search_changed()

    def on_add_manual_id(self):
        gid = self.manual_id_entry.get().strip()
        if not gid:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập Group ID.")
            return
            
        group_name = f"Nhóm {gid}"
        if self.zalo_service:
            fetched = self.zalo_service.fetch_group_info(gid)
            if fetched and fetched.get("name"):
                group_name = fetched["name"]

        self.group_names[gid] = group_name

        if gid in self.checkbox_vars:
            self.checkbox_vars[gid].set(True)
            messagebox.showinfo("Thông báo", f"Đã chọn nhóm: '{group_name}' (ID: {gid})")
        else:
            var = tk.BooleanVar(value=True)
            self.checkbox_vars[gid] = var
            cb = ttk.Checkbutton(self.scroll_frame, text=f"{group_name} (ID: {gid})", variable=var, padding="5")
            cb.pack(anchor="w", fill="x")
            self.group_checkbuttons[gid] = cb
            messagebox.showinfo("Thông báo", f"Đã tìm thấy và thêm nhóm '{group_name}' (ID: {gid}) vào danh sách!")
            
        self.manual_id_entry.delete(0, tk.END)

    def on_ok(self):
        self.result = [
            {"id": gid, "name": self.group_names.get(gid, f"Nhóm {gid}")}
            for gid, var in self.checkbox_vars.items() if var.get()
        ]
        self.destroy()

    def get_selected_group_ids(self):
        if not self.result:
            return None
        return [g["id"] for g in self.result]

    def get_selected_groups(self):
        return self.result

class StaffManagementDialog(tk.Toplevel):
    def __init__(self, group_id, group_name, zalo_service=None, parent=None):
        super().__init__(parent)
        self.title(f"Quản lý Nhân Viên Hỗ Trợ - {group_name}")
        self.geometry("460x540")
        self.resizable(False, False)
        
        self.group_id = group_id
        self.group_name = group_name
        self.zalo_service = zalo_service
        self.result = None

        self.transient(parent)
        self.grab_set()

        self.init_ui()
        center_window_over_parent(self, parent)

    def init_ui(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text=f"Tích chọn Nhân viên Hỗ trợ cho {self.group_name}:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Label(main_frame, text="* Chỉ tin nhắn từ các nhân viên được tích chọn mới được tính là tiếp nhận/xử lý Ticket.", font=("Arial", 8, "italic"), fg="#7F8C8D", wraplength=420).pack(anchor="w", pady=(0, 10))

        # Search Bar
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(search_frame, text="🔍 Tìm tên:").pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filter_members())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)

        # Container listbox frame with canvas/scrollbar
        list_container = ttk.LabelFrame(main_frame, text="Danh sách thành viên nhóm", padding="5")
        list_container.pack(fill="both", expand=True, pady=(0, 10))

        canvas = tk.Canvas(list_container, highlightthickness=0, bg="white")
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Load members & current staff
        from database import GroupDAO
        current_staff = set(GroupDAO.get_group_support_staff(self.group_id))
        
        all_members = []
        if self.zalo_service and hasattr(self.zalo_service, "fetch_group_members"):
            all_members = self.zalo_service.fetch_group_members(self.group_id)
        if not all_members:
            all_members = sorted(list(current_staff)) or ["Admin", "KTV Hỗ Trợ"]

        self.member_vars = {}
        self.check_widgets = []

        for name in all_members:
            var = tk.BooleanVar(value=(name in current_staff))
            cb = ttk.Checkbutton(self.scrollable_frame, text=name, variable=var)
            cb.pack(anchor="w", pady=2, padx=5)
            self.member_vars[name] = (var, cb)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x")

        ttk.Button(btn_frame, text="💾 Lưu danh sách Nhân viên", command=self.on_save).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Hủy", command=self.destroy).pack(side="left")

    def filter_members(self):
        query = self.search_var.get().strip().lower()
        for name, (var, cb) in self.member_vars.items():
            if not query or query in name.lower():
                cb.pack(anchor="w", pady=2, padx=5)
            else:
                cb.pack_forget()

    def on_save(self):
        selected_staff = [name for name, (var, cb) in self.member_vars.items() if var.get()]
        from database import GroupDAO
        GroupDAO.set_group_support_staff(self.group_id, selected_staff)
        self.result = selected_staff
        messagebox.showinfo("Thành công", f"Đã lưu {len(selected_staff)} nhân viên hỗ trợ cho nhóm {self.group_name}.")
        self.destroy()

    def get_data(self):
        return self.result
