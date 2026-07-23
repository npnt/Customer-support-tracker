import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import calendar
import time
from database import TicketDAO, GroupDAO
from ui.dialogs import center_window_over_parent

class DashboardWindow(tk.Toplevel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("📊 Dashboard Báo Cáo & Đánh Giá Hỗ Trợ Khách Hàng")
        self.geometry("1150x750")
        self.minsize(950, 600)
        
        self.transient(parent)
        self.grab_set()

        self.init_default_dates()
        self.init_ui()
        self.load_data()
        center_window_over_parent(self, parent)

    def init_default_dates(self):
        now = datetime.datetime.now()
        # Từ ngày 1 tháng hiện tại đến ngày cuối cùng tháng hiện tại
        first_day = datetime.datetime(now.year, now.month, 1, 0, 0, 0)
        last_day_num = calendar.monthrange(now.year, now.month)[1]
        last_day = datetime.datetime(now.year, now.month, last_day_num, 23, 59, 59)
        
        self.default_from_str = first_day.strftime("%Y-%m-%d")
        self.default_to_str = last_day.strftime("%Y-%m-%d")

    def init_ui(self):
        # 1. Top Filter Frame (Từ ngày -> Đến ngày)
        filter_frame = ttk.LabelFrame(self, text="⏱️ Bộ Lọc Khoảng Thời Gian Báo Cáo", padding="10")
        filter_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(filter_frame, text="Từ ngày (YYYY-MM-DD):", font=("Arial", 9, "bold")).pack(side="left", padx=(5, 5))
        self.from_entry = ttk.Entry(filter_frame, width=12)
        self.from_entry.insert(0, self.default_from_str)
        self.from_entry.pack(side="left", padx=(0, 15))

        ttk.Label(filter_frame, text="Đến ngày (YYYY-MM-DD):", font=("Arial", 9, "bold")).pack(side="left", padx=(5, 5))
        self.to_entry = ttk.Entry(filter_frame, width=12)
        self.to_entry.insert(0, self.default_to_str)
        self.to_entry.pack(side="left", padx=(0, 15))

        self.filter_btn = ttk.Button(filter_frame, text="🔍 Lọc Báo Cáo", command=self.load_data)
        self.filter_btn.pack(side="left", padx=5)

        self.reset_btn = ttk.Button(filter_frame, text="🔄 Reset Tháng Hiện Tại", command=self.reset_dates)
        self.reset_btn.pack(side="left", padx=5)

        # 2. Main Notebook Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Tab 1: Group SLA Metrics
        self.group_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.group_tab, text=" 👥 Thống Kê Theo Nhóm Zalo ")

        # Tab 2: Staff Support Metrics
        self.staff_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.staff_tab, text=" 👨‍💻 Thống Kê Nhân Viên Hỗ Trợ ")

        self.init_group_tab()
        self.init_staff_tab()

    def reset_dates(self):
        self.from_entry.delete(0, tk.END)
        self.from_entry.insert(0, self.default_from_str)
        self.to_entry.delete(0, tk.END)
        self.to_entry.insert(0, self.default_to_str)
        self.load_data()

    def parse_timestamps(self):
        from_str = self.from_entry.get().strip()
        to_str = self.to_entry.get().strip()

        try:
            from_dt = datetime.datetime.strptime(from_str, "%Y-%m-%d")
            to_dt = datetime.datetime.strptime(to_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            messagebox.showerror("Lỗi ngày tháng", "Vui lòng nhập ngày theo định dạng YYYY-MM-DD (Ví dụ: 2026-07-01).")
            return None, None

        if from_dt > to_dt:
            messagebox.showwarning("Cảnh báo", "Ngày bắt đầu (Từ ngày) không được lớn hơn Ngày kết thúc (Đến ngày).")
            return None, None

        from_ts = int(from_dt.timestamp() * 1000)
        to_ts = int(to_dt.timestamp() * 1000)
        return from_ts, to_ts

    def init_group_tab(self):
        # KPI Cards Top Frame
        self.group_kpi_frame = ttk.Frame(self.group_tab)
        self.group_kpi_frame.pack(fill="x", pady=(0, 10))

        self.group_hdr_lbl = tk.Label(self.group_kpi_frame, text="📍 Chỉ Số Đang Chọn: (Chưa chọn nhóm)", font=("Arial", 10, "bold"), fg="#2C3E50")
        self.group_hdr_lbl.pack(anchor="w", pady=(0, 4))

        sub_frame = ttk.Frame(self.group_kpi_frame)
        sub_frame.pack(fill="x")

        self.group_kpi_labels = {}
        self.group_kpi_labels["open_before"] = self.create_kpi_card_widget(sub_frame, "Open Trước Kỳ", "0", "#2980B9")
        self.group_kpi_labels["new_tickets"] = self.create_kpi_card_widget(sub_frame, "Ticket Mới", "0", "#27AE60")
        self.group_kpi_labels["resolved_tickets"] = self.create_kpi_card_widget(sub_frame, "Ticket Đã Đóng", "0", "#16A085")
        self.group_kpi_labels["overdue_response"] = self.create_kpi_card_widget(sub_frame, "Trễ Tiếp Nhận", "0", "#E67E22")
        self.group_kpi_labels["overdue_resolve"] = self.create_kpi_card_widget(sub_frame, "Trễ Xử Lý", "0", "#C0392B")
        self.group_kpi_labels["open_remaining"] = self.create_kpi_card_widget(sub_frame, "Open Tồn Hiện Tại", "0", "#8E44AD")

        # Paned Window Splitter: Table (Left) + Bar Chart (Right)
        paned = ttk.Panedwindow(self.group_tab, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        # Table Frame
        tbl_frame = ttk.LabelFrame(paned, text="Chi Tiết Số Liệu SLA Nhóm (Bấm vào dòng để xem KPI nhóm đó)", padding="5")
        paned.add(tbl_frame, weight=3)

        cols = ("name", "open_before", "new", "resolved", "overdue_resp", "overdue_res", "open_rem")
        self.group_tree = ttk.Treeview(tbl_frame, columns=cols, show="headings")
        self.group_tree.heading("name", text="Nhóm Zalo")
        self.group_tree.heading("open_before", text="Open Trước Kỳ")
        self.group_tree.heading("new", text="Ticket Mới")
        self.group_tree.heading("resolved", text="Ticket Đã Đóng")
        self.group_tree.heading("overdue_resp", text="Trễ Tiếp Nhận")
        self.group_tree.heading("overdue_res", text="Trễ Xử Lý")
        self.group_tree.heading("open_rem", text="Open Tồn")

        self.group_tree.column("name", width=160, anchor="w")
        self.group_tree.column("open_before", width=85, anchor="center")
        self.group_tree.column("new", width=80, anchor="center")
        self.group_tree.column("resolved", width=90, anchor="center")
        self.group_tree.column("overdue_resp", width=95, anchor="center")
        self.group_tree.column("overdue_res", width=85, anchor="center")
        self.group_tree.column("open_rem", width=80, anchor="center")

        self.group_tree.bind("<<TreeviewSelect>>", self.on_group_tree_select)

        g_scroll = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.group_tree.yview)
        self.group_tree.configure(yscrollcommand=g_scroll.set)
        self.group_tree.pack(side="left", fill="both", expand=True)
        g_scroll.pack(side="right", fill="y")

        # Chart Frame
        chart_frame = ttk.LabelFrame(paned, text="Biểu Đồ So Sánh Số Liệu SLA Nhóm", padding="5")
        paned.add(chart_frame, weight=2)

        self.group_canvas = tk.Canvas(chart_frame, bg="white", highlightthickness=0)
        self.group_canvas.pack(fill="both", expand=True)

    def init_staff_tab(self):
        # 1. Staff Filter Frame (Dropdown chọn nhóm Zalo)
        staff_filter_frame = ttk.Frame(self.staff_tab)
        staff_filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(staff_filter_frame, text="📍 Lọc Nhân Viên Theo Nhóm Zalo:", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 8))
        
        self.staff_group_combobox = ttk.Combobox(staff_filter_frame, state="readonly", width=40)
        self.staff_group_combobox.pack(side="left")
        self.staff_group_combobox.bind("<<ComboboxSelected>>", lambda e: self.load_data())

        # KPI Cards Top Frame
        self.staff_kpi_frame = ttk.Frame(self.staff_tab)
        self.staff_kpi_frame.pack(fill="x", pady=(0, 10))

        sub_frame = ttk.Frame(self.staff_kpi_frame)
        sub_frame.pack(fill="x")

        self.staff_kpi_labels = {}
        self.staff_kpi_labels["ack"] = self.create_kpi_card_widget(sub_frame, "Đã Tiếp Nhận", "0", "#2980B9")
        self.staff_kpi_labels["comp"] = self.create_kpi_card_widget(sub_frame, "Đã Hoàn Thành (Resolved)", "0", "#27AE60")
        self.staff_kpi_labels["overdue"] = self.create_kpi_card_widget(sub_frame, "Ticket Quá Hạn Xử Lý", "0", "#C0392B")
        self.staff_kpi_labels["open"] = self.create_kpi_card_widget(sub_frame, "Ticket Đang Open", "0", "#E67E22")

        paned = ttk.Panedwindow(self.staff_tab, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        # Table Frame
        tbl_frame = ttk.LabelFrame(paned, text="Chi Tiết Năng Suất Nhân Viên Hỗ Trợ", padding="5")
        paned.add(tbl_frame, weight=3)

        cols = ("staff_name", "acknowledged", "completed", "overdue_resolve", "open_rem")
        self.staff_tree = ttk.Treeview(tbl_frame, columns=cols, show="headings")
        self.staff_tree.heading("staff_name", text="Nhân Viên / KTV Hỗ Trợ")
        self.staff_tree.heading("acknowledged", text="Đã Tiếp Nhận")
        self.staff_tree.heading("completed", text="Đã Hoàn Thành (Resolved)")
        self.staff_tree.heading("overdue_resolve", text="Ticket Quá Hạn Xử Lý")
        self.staff_tree.heading("open_rem", text="Ticket Đang Open")

        self.staff_tree.column("staff_name", width=180, anchor="w")
        self.staff_tree.column("acknowledged", width=110, anchor="center")
        self.staff_tree.column("completed", width=140, anchor="center")
        self.staff_tree.column("overdue_resolve", width=130, anchor="center")
        self.staff_tree.column("open_rem", width=110, anchor="center")

        s_scroll = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.staff_tree.yview)
        self.staff_tree.configure(yscrollcommand=s_scroll.set)
        self.staff_tree.pack(side="left", fill="both", expand=True)
        s_scroll.pack(side="right", fill="y")

        # Chart Frame
        chart_frame = ttk.LabelFrame(paned, text="Biểu Đồ Năng Suất Nhân Viên", padding="5")
        paned.add(chart_frame, weight=2)

        self.staff_canvas = tk.Canvas(chart_frame, bg="white", highlightthickness=0)
        self.staff_canvas.pack(fill="both", expand=True)

    def create_kpi_card_widget(self, parent, title, initial_value, color):
        card = tk.Frame(parent, bg="white", bd=1, relief="solid", highlightbackground="#BDC3C7", highlightthickness=1, padx=10, pady=8)
        card.pack(side="left", fill="both", expand=True, padx=4)

        lbl_title = tk.Label(card, text=title, font=("Arial", 9, "bold"), fg="#7F8C8D", bg="white")
        lbl_title.pack(anchor="w")

        lbl_val = tk.Label(card, text=initial_value, font=("Arial", 16, "bold"), fg=color, bg="white")
        lbl_val.pack(anchor="w", pady=(2, 0))
        return lbl_val

    def populate_staff_group_combobox(self):
        tracked_groups = GroupDAO.get_tracked_groups()
        options = ["-- Tất cả các nhóm Zalo --"]
        self.group_id_map = {"-- Tất cả các nhóm Zalo --": None}
        for g in tracked_groups:
            label = f"{g['name']} (ID: {g['id']})"
            options.append(label)
            self.group_id_map[label] = g["id"]

        curr = self.staff_group_combobox.get()
        self.staff_group_combobox["values"] = options
        if not curr or curr not in options:
            self.staff_group_combobox.set(options[0])

    def load_data(self):
        from_ts, to_ts = self.parse_timestamps()
        if from_ts is None or to_ts is None:
            return

        self.populate_staff_group_combobox()
        selected_label = self.staff_group_combobox.get()
        selected_gid = self.group_id_map.get(selected_label)

        self.latest_group_metrics = TicketDAO.get_dashboard_group_metrics(from_ts, to_ts)
        staff_metrics = TicketDAO.get_dashboard_staff_metrics(from_ts, to_ts, group_id=selected_gid)

        self.render_group_metrics(self.latest_group_metrics)
        self.render_staff_metrics(staff_metrics)

    def render_group_metrics(self, group_metrics):
        # 1. Update Treeview
        for item in self.group_tree.get_children():
            self.group_tree.delete(item)

        self.group_row_map = {}
        first_item = None

        for g in group_metrics:
            item_id = self.group_tree.insert("", "end", values=(
                g["group_name"],
                g["open_before"],
                g["new_tickets"],
                g["resolved_tickets"],
                g["overdue_response"],
                g["overdue_resolve"],
                g["open_remaining"]
            ))
            self.group_row_map[item_id] = g
            if first_item is None:
                first_item = item_id

        # Mặc định chọn dòng đầu tiên nếu chưa chọn
        if first_item:
            self.group_tree.selection_set(first_item)
            self.update_group_kpi_cards(self.group_row_map[first_item])
        else:
            self.update_group_kpi_cards(None)

        # 2. Render Canvas Chart
        self.render_group_chart(group_metrics)

    def on_group_tree_select(self, event):
        selected_items = self.group_tree.selection()
        if selected_items and selected_items[0] in self.group_row_map:
            self.update_group_kpi_cards(self.group_row_map[selected_items[0]])

    def update_group_kpi_cards(self, g_data):
        if not g_data:
            self.group_hdr_lbl.configure(text="📍 Chỉ Số Đang Chọn: Chưa có dữ liệu nhóm")
            for k in self.group_kpi_labels:
                self.group_kpi_labels[k].configure(text="0")
            return

        self.group_hdr_lbl.configure(text=f"📍 Chỉ Số Đang Chọn: {g_data['group_name']}")
        self.group_kpi_labels["open_before"].configure(text=str(g_data["open_before"]))
        self.group_kpi_labels["new_tickets"].configure(text=str(g_data["new_tickets"]))
        self.group_kpi_labels["resolved_tickets"].configure(text=str(g_data["resolved_tickets"]))
        self.group_kpi_labels["overdue_response"].configure(text=str(g_data["overdue_response"]))
        self.group_kpi_labels["overdue_resolve"].configure(text=str(g_data["overdue_resolve"]))
        self.group_kpi_labels["open_remaining"].configure(text=str(g_data["open_remaining"]))

    def render_staff_metrics(self, staff_metrics):
        # 1. Update Treeview
        for item in self.staff_tree.get_children():
            self.staff_tree.delete(item)

        sum_ack = sum(s["acknowledged"] for s in staff_metrics)
        sum_comp = sum(s["completed"] for s in staff_metrics)
        sum_ov = sum(s["overdue_resolve"] for s in staff_metrics)
        sum_open = sum(s["open_remaining"] for s in staff_metrics)

        for s in staff_metrics:
            self.staff_tree.insert("", "end", values=(
                s["staff_name"],
                s["acknowledged"],
                s["completed"],
                s["overdue_resolve"],
                s["open_remaining"]
            ))

        # 2. Update KPI Cards without destroying widgets
        self.staff_kpi_labels["ack"].configure(text=str(sum_ack))
        self.staff_kpi_labels["comp"].configure(text=str(sum_comp))
        self.staff_kpi_labels["overdue"].configure(text=str(sum_ov))
        self.staff_kpi_labels["open"].configure(text=str(sum_open))

        # 3. Render Canvas Chart
        self.render_staff_chart(staff_metrics)

    def create_kpi_card(self, parent, title, value, color):
        card = tk.Frame(parent, bg="white", bd=1, relief="solid", highlightbackground="#BDC3C7", highlightthickness=1, padx=10, pady=8)
        card.pack(side="left", fill="both", expand=True, padx=4)

        lbl_title = tk.Label(card, text=title, font=("Arial", 9, "bold"), fg="#7F8C8D", bg="white")
        lbl_title.pack(anchor="w")

        lbl_val = tk.Label(card, text=value, font=("Arial", 16, "bold"), fg=color, bg="white")
        lbl_val.pack(anchor="w", pady=(2, 0))

    def render_group_chart(self, group_metrics):
        self.group_canvas.delete("all")
        if not group_metrics:
            return

        w = self.group_canvas.winfo_width() or 400
        h = self.group_canvas.winfo_height() or 400

        max_val = max([g["new_tickets"] for g in group_metrics] + [g["open_remaining"] for g in group_metrics] + [1])
        
        # Chú thích màu
        self.group_canvas.create_rectangle(20, 15, 35, 25, fill="#27AE60", outline="")
        self.group_canvas.create_text(40, 20, text="Ticket Mới", anchor="w", font=("Arial", 9))
        self.group_canvas.create_rectangle(140, 15, 155, 25, fill="#8E44AD", outline="")
        self.group_canvas.create_text(160, 20, text="Open Tồn", anchor="w", font=("Arial", 9))

        chart_top = 45
        chart_bottom = h - 60
        chart_height = max(100, chart_bottom - chart_top)

        bar_width = 18
        gap = 35
        x_start = 40

        for idx, g in enumerate(group_metrics[:8]): # Hiển thị tối đa 8 nhóm trên biểu đồ
            x = x_start + idx * (bar_width * 2 + gap)

            val_new = g["new_tickets"]
            val_rem = g["open_remaining"]

            h_new = int((val_new / max_val) * chart_height)
            h_rem = int((val_rem / max_val) * chart_height)

            # Cột Ticket Mới (Xanh)
            self.group_canvas.create_rectangle(x, chart_bottom - h_new, x + bar_width, chart_bottom, fill="#27AE60", outline="")
            if val_new > 0:
                self.group_canvas.create_text(x + bar_width/2, chart_bottom - h_new - 8, text=str(val_new), font=("Arial", 8, "bold"))

            # Cột Open Tồn (Tím)
            self.group_canvas.create_rectangle(x + bar_width + 4, chart_bottom - h_rem, x + bar_width * 2 + 4, chart_bottom, fill="#8E44AD", outline="")
            if val_rem > 0:
                self.group_canvas.create_text(x + bar_width + 4 + bar_width/2, chart_bottom - h_rem - 8, text=str(val_rem), font=("Arial", 8, "bold"))

            # Nhãn tên nhóm ngắn
            gname_short = g["group_name"][:8] + ".." if len(g["group_name"]) > 8 else g["group_name"]
            self.group_canvas.create_text(x + bar_width, chart_bottom + 15, text=gname_short, font=("Arial", 8), anchor="n")

        # Đường trục x
        self.group_canvas.create_line(20, chart_bottom, w - 20, chart_bottom, fill="#BDC3C7", width=1)

    def render_staff_chart(self, staff_metrics):
        self.staff_canvas.delete("all")
        if not staff_metrics:
            return

        w = self.staff_canvas.winfo_width() or 400
        h = self.staff_canvas.winfo_height() or 400

        max_val = max([s["completed"] for s in staff_metrics] + [s["acknowledged"] for s in staff_metrics] + [1])

        # Chú thích màu
        self.staff_canvas.create_rectangle(20, 15, 35, 25, fill="#2980B9", outline="")
        self.staff_canvas.create_text(40, 20, text="Đã Tiếp Nhận", anchor="w", font=("Arial", 9))
        self.staff_canvas.create_rectangle(150, 15, 165, 25, fill="#27AE60", outline="")
        self.staff_canvas.create_text(170, 20, text="Đã Hoàn Thành", anchor="w", font=("Arial", 9))

        chart_top = 45
        chart_bottom = h - 60
        chart_height = max(100, chart_bottom - chart_top)

        bar_width = 18
        gap = 35
        x_start = 40

        for idx, s in enumerate(staff_metrics[:8]): # Hiển thị tối đa 8 nhân viên
            x = x_start + idx * (bar_width * 2 + gap)

            val_ack = s["acknowledged"]
            val_comp = s["completed"]

            h_ack = int((val_ack / max_val) * chart_height)
            h_comp = int((val_comp / max_val) * chart_height)

            # Cột Đã tiếp nhận (Xanh dương)
            self.staff_canvas.create_rectangle(x, chart_bottom - h_ack, x + bar_width, chart_bottom, fill="#2980B9", outline="")
            if val_ack > 0:
                self.staff_canvas.create_text(x + bar_width/2, chart_bottom - h_ack - 8, text=str(val_ack), font=("Arial", 8, "bold"))

            # Cột Đã hoàn thành (Xanh lá)
            self.staff_canvas.create_rectangle(x + bar_width + 4, chart_bottom - h_comp, x + bar_width * 2 + 4, chart_bottom, fill="#27AE60", outline="")
            if val_comp > 0:
                self.staff_canvas.create_text(x + bar_width + 4 + bar_width/2, chart_bottom - h_comp - 8, text=str(val_comp), font=("Arial", 8, "bold"))

            # Nhãn tên nhân viên
            sname_short = s["staff_name"][:8] + ".." if len(s["staff_name"]) > 8 else s["staff_name"]
            self.staff_canvas.create_text(x + bar_width, chart_bottom + 15, text=sname_short, font=("Arial", 8), anchor="n")

        # Đường trục x
        self.staff_canvas.create_line(20, chart_bottom, w - 20, chart_bottom, fill="#BDC3C7", width=1)
