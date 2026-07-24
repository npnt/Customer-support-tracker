import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import time
import logging
import queue
import threading

from database import GroupDAO, TicketDAO, MessageDAO, run_vacuum
from app_core import AppCore, TicketManager
from ui.dialogs import LoginDialog, SlaSettingsDialog, GroupSelectDialog
from ui.dashboard import DashboardWindow

logger = logging.getLogger("app")

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Đảm bảo chiều rộng của khung cuộn bằng canvas
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def on_canvas_configure(self, event):
        # Đặt chiều rộng của khung cuộn bằng chiều rộng canvas để co giãn tốt
        self.canvas.itemconfig(self.canvas_window, width=event.width)

class TicketCard(tk.Frame):
    def __init__(self, parent, ticket, on_click_cb, *args, **kwargs):
        super().__init__(parent, bd=1, relief="solid", bg="white", padx=5, pady=5, *args, **kwargs)
        self.ticket = ticket
        self.on_click_cb = on_click_cb
        
        self.configure(highlightbackground="#BDC3C7", highlightcolor="#3498DB", highlightthickness=1)
        self.init_ui()
        
        # Bắt sự kiện click trên toàn bộ card và các widget con
        self.bind("<Button-1>", self.on_click)
        self.bind_all_children(self)

    def bind_all_children(self, parent_widget):
        for child in parent_widget.winfo_children():
            child.bind("<Button-1>", self.on_click)
            self.bind_all_children(child)

    def init_ui(self):
        # Header: Tên khách hàng & Nhãn Cần duyệt
        header_frame = tk.Frame(self, bg="white")
        header_frame.pack(fill="x", anchor="w")
        
        name_label = tk.Label(header_frame, text=f"👤 {self.ticket['requester_name']}", font=("Arial", 10, "bold"), bg="white", fg="#2C3E50")
        name_label.pack(side="left")
        
        if self.ticket.get("needs_review") == 1:
            badge = tk.Label(header_frame, text="⚠️ Cần duyệt", font=("Arial", 8, "bold"), bg="#FFF3CD", fg="#856404", bd=1, relief="solid", padx=2)
            badge.pack(side="left", padx=5)
            
        # Nội dung yêu cầu (Snippet)
        snippet = self.ticket["request_content"]
        if len(snippet) > 60:
            snippet = snippet[:60] + "..."
        self.snippet_label = tk.Label(self, text=snippet, font=("Arial", 9), fg="#555555", bg="white", justify="left", anchor="w", wraplength=380)
        self.snippet_label.pack(fill="x", pady=2)
        
        # Khung chứa nhãn SLA
        sla_frame = tk.Frame(self, bg="white")
        sla_frame.pack(fill="x", anchor="w", pady=2)
        
        self.response_label = tk.Label(sla_frame, font=("Courier", 9), padx=4, pady=1)
        self.resolve_label = tk.Label(sla_frame, font=("Courier", 9), padx=4, pady=1)
        
        self.update_timers()

    def update_timers(self):
        ticket = TicketDAO.get_ticket_by_id(self.ticket["id"])
        if not ticket:
            return
        self.ticket = ticket
        
        resp_mins, res_mins = TicketManager.get_remaining_sla(self.ticket)
        
        # Tiếp nhận SLA
        if self.ticket["status"] == "PENDING":
            if resp_mins is not None:
                if resp_mins < 0:
                    self.response_label.configure(text=f"⏱️ Tiếp nhận: Trễ {-resp_mins}p", bg="#F8D7DA", fg="#721C24")
                elif resp_mins <= 5:
                    self.response_label.configure(text=f"⏱️ Tiếp nhận: {resp_mins}p", bg="#FFF3CD", fg="#856404")
                else:
                    self.response_label.configure(text=f"⏱️ Tiếp nhận: {resp_mins}p", bg="#D1ECF1", fg="#0C5460")
                self.response_label.pack(side="left", padx=(0, 10))
        else:
            self.response_label.configure(text="⏱️ Tiếp nhận: OK", bg="#D4EDDA", fg="#155724")
            self.response_label.pack(side="left", padx=(0, 10))
            
        # Xử lý SLA
        if res_mins is not None:
            if res_mins < 0:
                self.resolve_label.configure(text=f"🛠️ Xử lý: Trễ {-res_mins}p", bg="#F8D7DA", fg="#721C24")
            elif res_mins <= 15:
                self.resolve_label.configure(text=f"🛠️ Xử lý: {res_mins}p", bg="#FFF3CD", fg="#856404")
            else:
                self.resolve_label.configure(text=f"🛠️ Xử lý: {res_mins}p", bg="#D1ECF1", fg="#0C5460")
            self.resolve_label.pack(side="left")
        else:
            self.resolve_label.pack_forget()

    def on_click(self, event):
        self.on_click_cb(self)
        
    def select(self):
        # Đổi màu nền sang xanh nhạt khi được chọn
        self.configure(bg="#EBF5FB", highlightbackground="#3498DB", highlightthickness=2)
        self.update_widget_colors(self, "#EBF5FB")

    def deselect(self):
        self.configure(bg="white", highlightbackground="#BDC3C7", highlightthickness=1)
        self.update_widget_colors(self, "white")

    def update_widget_colors(self, parent_widget, bg_color):
        for child in parent_widget.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(bg=bg_color)
                self.update_widget_colors(child, bg_color)
            else:
                # Giữ nguyên màu nền các nhãn trạng thái đặc biệt
                if child.cget("bg") not in ("#FFF3CD", "#F8D7DA", "#D1ECF1", "#D4EDDA"):
                    child.configure(bg=bg_color)

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zalo Customer Support Tracker - AI Support Monitor")
        
        # Tải kích thước cửa sổ đã lưu từ trước (hoặc mặc định 1100x700)
        saved_geometry = self.load_window_geometry()
        self.geometry(saved_geometry)
        
        # Khởi tạo Queue nhận sự kiện UI thread-safe
        self.ui_queue = queue.Queue()
        
        # Đăng ký callback cho Core
        ui_callbacks = {
            "update_ui": lambda: self.ui_queue.put({"type": "UPDATE_UI"}),
            "sync_progress": lambda c, t: self.ui_queue.put({"type": "SYNC_PROGRESS", "data": (c, t)}),
            "status_message": lambda m: self.ui_queue.put({"type": "STATUS_MESSAGE", "data": m}),
            "on_live_message": lambda msg: self.ui_queue.put({"type": "LIVE_MESSAGE", "data": msg})
        }
        
        self.core = AppCore(ui_callbacks)
        self.selected_group_id = None
        self.selected_ticket_id = None
        self.ticket_cards = []
        
        self.init_ui()
        self.init_menu()
        
        # Bắt đầu nhận diện dịch vụ
        self.core.start_services()
        
        # Bắt đầu vòng lặp polling sự kiện UI từ luồng phụ
        self.poll_ui_queue()
        
        # Cập nhật SLA định kỳ mỗi 1 giây
        self.update_sla_loop()
        
        # Cập nhật trạng thái hiển thị kết nối ban đầu
        self.update_connection_ui()
        
        # Bắt sự kiện đóng cửa sổ
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def init_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Vệt Paned Window theo chiều dọc để chứa 3 cột và Panel tin nhắn live dưới cùng
        v_pane = ttk.Panedwindow(self, orient=tk.VERTICAL)
        v_pane.pack(fill="both", expand=True, padx=5, pady=5)

        # Layout chính dạng Paned Window (chiều ngang) chứa 3 cột
        main_pane = ttk.Panedwindow(v_pane, orient=tk.HORIZONTAL)
        v_pane.add(main_pane, weight=4)

        # ==========================================
        # CỘT 1 (BÊN TRÁI): NHÓM CHAT & THIẾT LẬP
        # ==========================================
        left_frame = ttk.LabelFrame(main_pane, text="Nhóm Zalo Theo Dõi", padding="10")
        
        self.add_group_btn = ttk.Button(left_frame, text="➕ Thêm Nhóm Theo Dõi", command=self.on_add_group_clicked)
        self.add_group_btn.pack(fill="x", pady=(0, 5))
        
        self.update_group_btn = ttk.Button(left_frame, text="🔄 Cập Nhật Tên Nhóm", command=self.on_update_group_names_clicked)
        self.update_group_btn.pack(fill="x", pady=(0, 10))
        
        # Sử dụng Listbox cho nhóm với exportselection=False để giữ nguyên vệt chọn khi mở cửa sổ phụ
        self.group_listbox = tk.Listbox(left_frame, font=("Arial", 10), height=15, exportselection=False)
        self.group_listbox.pack(fill="both", expand=True, pady=(0, 10))
        self.group_listbox.bind("<<ListboxSelect>>", self.on_group_selected)
        
        group_btn_frame = ttk.Frame(left_frame)
        group_btn_frame.pack(fill="x", pady=(0, 15))

        self.sla_settings_btn = ttk.Button(group_btn_frame, text="⚙️ Thiết lập SLA", command=self.on_sla_clicked, state="disabled")
        self.sla_settings_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.manage_staff_btn = ttk.Button(group_btn_frame, text="👥 QL Nhân Viên", command=self.on_manage_staff_clicked, state="normal")
        self.manage_staff_btn.pack(side="left", fill="x", expand=True)

        # Khung Đăng nhập / Kết nối
        conn_frame = ttk.LabelFrame(left_frame, text="Zalo Connection", padding="8")
        conn_frame.pack(fill="x", side="bottom")
        
        self.conn_status_label = tk.Label(conn_frame, text="Trạng thái: Chưa kết nối", font=("Arial", 9, "bold"), fg="#7F8C8D")
        self.conn_status_label.pack(anchor="w", pady=(0, 5))
        
        self.login_btn = ttk.Button(conn_frame, text="🔑 Đăng nhập Zalo Web", command=self.on_login_clicked)
        self.login_btn.pack(fill="x")
        
        main_pane.add(left_frame, weight=1)

        # ==========================================
        # CỘT 2 (Ở GIỮA): DANH SÁCH YÊU CẦU HỖ TRỢ
        # ==========================================
        middle_frame = ttk.LabelFrame(main_pane, text="Yêu Cầu Chưa Phản Hồi (Chờ Tiếp Nhận)", padding="10")
        
        # Scrollable Frame để hiển thị danh sách các Card
        self.scroll_tickets_frame = ScrollableFrame(middle_frame)
        self.scroll_tickets_frame.pack(fill="both", expand=True)
        
        main_pane.add(middle_frame, weight=2)

        # ==========================================
        # CỘT 3 (BÊN PHẢI): YÊU CẦU ĐÃ & ĐANG ĐƯỢC HỖ TRỢ
        # ==========================================
        right_frame = ttk.LabelFrame(main_pane, text="Yêu Cầu Đã & Đang Được Hỗ Trợ", padding="10")
        
        # Header ticket thông tin
        header_frame = ttk.Frame(right_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        self.ticket_info_label = tk.Label(header_frame, text="Vui lòng chọn một yêu cầu để xem chi tiết.", font=("Arial", 10, "bold"), fg="#2C3E50", justify="left", anchor="w", wraplength=320)
        self.ticket_info_label.pack(fill="x", anchor="w")

        self.ticket_sla_label = tk.Label(header_frame, text="", font=("Arial", 9, "bold"), justify="left", anchor="w", wraplength=320)
        self.ticket_sla_label.pack(fill="x", anchor="w", pady=(2, 0))
        
        # Cây phản hồi sử dụng ttk.Treeview với chiều cao dòng thoáng hơn (rowheight=32)
        style.configure("ResponseTree.Treeview", rowheight=32, font=("Arial", 10))
        self.response_tree = ttk.Treeview(right_frame, show="tree", style="ResponseTree.Treeview")
        self.response_tree.pack(fill="both", expand=True, pady=(0, 10))
        self.response_tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Cấu hình màu nền và chữ cho các trạng thái trên cây
        self.response_tree.tag_configure("needs_review", background="#FFF3CD")
        self.response_tree.tag_configure("RESOLVED", foreground="#7F8C8D")
        self.response_tree.tag_configure("PROCESSING", foreground="#2C3E50", font=("Arial", 10, "bold"))

        # Nút Hành động
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill="x", side="bottom")
        
        self.resolve_btn = ttk.Button(btn_frame, text="✅ Đóng Yêu Cầu", command=self.on_resolve_clicked, state="disabled")
        self.resolve_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))

        self.reopen_btn = ttk.Button(btn_frame, text="🔓 Mở Lại Yêu Cầu", command=self.on_reopen_clicked, state="disabled")
        self.reopen_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        self.split_ticket_btn = ttk.Button(btn_frame, text="✂️ Tách Ticket", command=self.on_split_ticket_clicked, state="disabled")
        self.split_ticket_btn.pack(side="left", fill="x", expand=True)
        
        main_pane.add(right_frame, weight=2)

        # ==========================================
        # PANEL DƯỚI CÙNG: NHẬT KÝ TIN NHẮN LIVE TRỰC TIẾP
        # ==========================================
        bottom_panel = ttk.LabelFrame(v_pane, text="📺 Nhật Ký Tin Nhắn Zalo Trực Tiếp (Live Zalo Messages)", padding="5")
        
        self.live_tree = ttk.Treeview(bottom_panel, columns=("time", "group", "sender", "content"), show="headings", height=4)
        self.live_tree.heading("time", text="Thời Gian")
        self.live_tree.heading("group", text="Nhóm Zalo")
        self.live_tree.heading("sender", text="Người Gửi")
        self.live_tree.heading("content", text="Nội Dung Tin Nhắn")
        
        self.live_tree.column("time", width=80, minwidth=80, stretch=False, anchor="center")
        self.live_tree.column("group", width=150, minwidth=100, stretch=False, anchor="w")
        self.live_tree.column("sender", width=120, minwidth=100, stretch=False, anchor="w")
        self.live_tree.column("content", width=500, minwidth=300, stretch=True, anchor="w")
        
        live_scroll = ttk.Scrollbar(bottom_panel, orient="vertical", command=self.live_tree.yview)
        self.live_tree.configure(yscrollcommand=live_scroll.set)
        
        self.live_tree.pack(side="left", fill="both", expand=True)
        live_scroll.pack(side="right", fill="y")
        
        v_pane.add(bottom_panel, weight=1)

        # ==========================================
        # STATUS BAR & PROGRESS BAR
        # ==========================================
        self.status_bar_frame = ttk.Frame(self, relief="sunken", padding="2")
        self.status_bar_frame.pack(fill="x", side="bottom")
        
        self.status_label = ttk.Label(self.status_bar_frame, text="Sẵn sàng")
        self.status_label.pack(side="left", padx=5)
        
        self.progress_bar = ttk.Progressbar(self.status_bar_frame, orient="horizontal", length=150, mode="determinate")
        self.progress_bar.pack(side="right", padx=5)
        self.progress_bar.pack_forget() # Ẩn đi khi không chạy sync

    def init_menu(self):
        menubar = tk.Menu(self)
        
        # Menu Hệ thống
        system_menu = tk.Menu(menubar, tearoff=0)
        system_menu.add_command(label="Thoát", command=self.on_close)
        menubar.add_cascade(label="Hệ thống", menu=system_menu)
        
        # Menu Cấu hình
        config_menu = tk.Menu(menubar, tearoff=0)
        config_menu.add_command(label="👥 Quản lý Nhân Viên Hỗ Trợ", command=self.on_manage_staff_clicked)
        config_menu.add_command(label="⚙️ Thiết lập SLA Nhóm Zalo", command=self.on_sla_clicked)
        menubar.add_cascade(label="Cấu hình", menu=config_menu)

        # Menu Báo cáo & Thống kê
        report_menu = tk.Menu(menubar, tearoff=0)
        report_menu.add_command(label="📊 Dashboard Báo Cáo SLA & Đánh Giá Hỗ Trợ", command=self.on_open_dashboard)
        menubar.add_cascade(label="Báo cáo & Thống kê", menu=report_menu)

        # Menu Bảo trì
        maintenance_menu = tk.Menu(menubar, tearoff=0)
        maintenance_menu.add_command(label="Tối ưu hóa Database (VACUUM)", command=self.on_vacuum_clicked)
        maintenance_menu.add_command(label="Sao lưu Database thủ công", command=self.on_backup_clicked)
        menubar.add_cascade(label="Bảo trì", menu=maintenance_menu)
        
        self.config(menu=menubar)

    def on_open_dashboard(self):
        DashboardWindow(self)

    # ==========================================
    # CÁC HÀM XỬ LÝ SỰ KIỆN GIAO DIỆN
    # ==========================================
    def poll_ui_queue(self):
        """
        Đọc các sự kiện nhận được từ luồng phụ trong hàng đợi ui_queue
        để chạy cập nhật giao diện trên luồng chính của Tkinter.
        """
        while True:
            try:
                event = self.ui_queue.get_nowait()
            except queue.Empty:
                break
                
            event_type = event.get("type")
            data = event.get("data")
            
            if event_type == "UPDATE_UI":
                self.refresh_ui()
            elif event_type == "SYNC_PROGRESS":
                current, total = data
                self.update_sync_progress(current, total)
            elif event_type == "STATUS_MESSAGE":
                self.show_status_message(data)
            elif event_type == "LIVE_MESSAGE":
                self.add_live_message_to_tree(data)
                
        self.after(100, self.poll_ui_queue)

    def refresh_ui(self):
        # 1. Cập nhật danh sách nhóm
        # Lưu lại nhóm cũ đang chọn
        selected_indices = self.group_listbox.curselection()
        old_selected_id = self.selected_group_id
        
        self.group_listbox.delete(0, tk.END)
        tracked_groups = GroupDAO.get_tracked_groups()
        
        for idx, group in enumerate(tracked_groups):
            sla = GroupDAO.get_sla_settings(group["id"])
            pending_cnt, processing_cnt = TicketDAO.get_group_ticket_counts(group["id"])
            has_overdue = TicketDAO.has_overdue_pending_tickets(group["id"])
            
            if has_overdue:
                item_text = f"⚠️ [{pending_cnt}/{processing_cnt}] {group['name']} ({sla['max_response_time']}m/{sla['max_resolve_time']}m)"
            else:
                item_text = f"[{pending_cnt}/{processing_cnt}] {group['name']} ({sla['max_response_time']}m/{sla['max_resolve_time']}m)"
                
            self.group_listbox.insert(tk.END, item_text)
            
            if has_overdue:
                self.group_listbox.itemconfigure(idx, fg="#C0392B", bg="#FDEDEC", selectforeground="#C0392B")
            else:
                self.group_listbox.itemconfigure(idx, fg="#2C3E50", bg="white", selectforeground="#FFFFFF")
            
            if str(group["id"]) == str(old_selected_id):
                self.group_listbox.selection_set(idx)
                
        if tracked_groups:
            self.manage_staff_btn.configure(state="normal")
            if self.group_listbox.curselection():
                self.sla_settings_btn.configure(state="normal")
            else:
                self.sla_settings_btn.configure(state="disabled")
        else:
            self.manage_staff_btn.configure(state="disabled")
            self.sla_settings_btn.configure(state="disabled")

        # 2. Cập nhật danh sách ticket chưa phản hồi
        self.refresh_ticket_list()
        
        # 3. Cập nhật cây các ticket đã & đang được hỗ trợ
        self.refresh_supported_tickets_tree()

    def refresh_ticket_list(self):
        if not self.selected_group_id:
            # Clear ticket cards
            for card in self.ticket_cards:
                card.destroy()
            self.ticket_cards.clear()
            return
            
        # Lấy danh sách ticket chưa phản hồi (status = 'PENDING')
        tickets = [t for t in TicketDAO.get_unresolved_tickets(self.selected_group_id) if t["status"] == "PENDING"]
        
        def get_response_sla(t):
            resp_mins, _ = TicketManager.get_remaining_sla(t)
            return resp_mins if resp_mins is not None else 99999
            
        tickets_sorted = sorted(tickets, key=get_response_sla)
        
        # Xóa các card cũ trong scroll frame
        for card in self.ticket_cards:
            card.destroy()
        self.ticket_cards.clear()
        
        # Tạo các card mới
        for ticket in tickets_sorted:
            card = TicketCard(
                parent=self.scroll_tickets_frame.scrollable_frame,
                ticket=ticket,
                on_click_cb=self.on_ticket_card_clicked
            )
            card.pack(fill="x", pady=5, padx=5)
            self.ticket_cards.append(card)
            
            # Chọn lại card nếu trùng ID đang chọn
            if ticket["id"] == self.selected_ticket_id:
                card.select()

    def refresh_supported_tickets_tree(self):
        # Lưu các node đang mở để giữ nguyên trạng thái đóng/mở sau khi nạp lại
        expanded_tickets = set()
        for item in self.response_tree.get_children():
            if self.response_tree.item(item, "open"):
                expanded_tickets.add(item)
                
        # Xóa cây cũ
        for item in self.response_tree.get_children():
            self.response_tree.delete(item)
            
        if not self.selected_group_id:
            return
            
        # Lấy danh sách ticket đã và đang hỗ trợ
        tickets = TicketDAO.get_supported_tickets(self.selected_group_id)
        
        for ticket in tickets:
            ticket_id = ticket["id"]
            node_id = f"ticket_{ticket_id}"
            
            if ticket["status"] == "RESOLVED":
                if ticket.get("auto_resolved") == 1:
                    status_symbol = "🤖" # Icon phân biệt Ticket do AI tự động đóng!
                else:
                    status_symbol = "✅" # Icon cho Ticket do người dùng tự bấm đóng!
            else:
                status_symbol = "⚙️"
            created_time = time.strftime('%H:%M %d/%m', time.localtime(ticket["created_at"]/1000))
            
            # Tính toán và hiển thị SLA giải quyết cho ticket đang hỗ trợ (status == PROCESSING)
            sla_text = ""
            if ticket["status"] == "PROCESSING":
                _, res_mins = TicketManager.get_remaining_sla(ticket)
                if res_mins is not None:
                    if res_mins < 0:
                        sla_text = f" [🛠️ Trễ {-res_mins}m]"
                    else:
                        sla_text = f" [🛠️ Còn {res_mins}m]"
            
            root_text = f"{status_symbol} {ticket['requester_name']}: {ticket['request_content'][:40]}... ({created_time}){sla_text}"
            
            tags = (ticket["status"],)
            if ticket.get("needs_review") == 1:
                tags = tags + ("needs_review",)
                
            should_open = node_id in expanded_tickets
            
            root_node = self.response_tree.insert(
                "", 
                "end", 
                iid=node_id, 
                text=root_text, 
                open=should_open,
                tags=tags
            )
            
            # Thêm các tin nhắn phản hồi dưới dạng nút con
            responses = TicketDAO.get_ticket_responses(ticket_id)
            for resp in responses:
                resp_time = time.strftime('%H:%M:%S %d/%m', time.localtime(resp["created_at"]/1000))
                child_text = f"💬 {resp['responder_name']}: {resp['response_content']} ({resp_time})"
                
                child_tags = ()
                msg_db = MessageDAO.get_message_by_id(resp["response_msg_id"])
                if msg_db and msg_db.get("needs_review") == 1:
                    child_tags = ("needs_review",)
                    
                self.response_tree.insert(
                    root_node, 
                    "end", 
                    iid=f"resp_{resp['id']}", 
                    text=child_text, 
                    tags=child_tags
                )

    def on_group_selected(self, event):
        selection = self.group_listbox.curselection()
        if not selection:
            self.selected_group_id = None
            self.sla_settings_btn.configure(state="disabled")
            self.manage_staff_btn.configure(state="disabled")
            return
            
        idx = selection[0]
        tracked_groups = GroupDAO.get_tracked_groups()
        if idx < len(tracked_groups):
            self.selected_group_id = tracked_groups[idx]["id"]
            self.sla_settings_btn.configure(state="normal")
            self.manage_staff_btn.configure(state="normal")
            self.refresh_ticket_list()
            self.refresh_supported_tickets_tree()

    def on_manage_staff_clicked(self):
        tracked_groups = GroupDAO.get_tracked_groups()
        if not tracked_groups:
            messagebox.showwarning("Cảnh báo", "Vui lòng thêm ít nhất một nhóm Zalo vào danh sách theo dõi trước khi quản lý nhân viên.")
            return

        if not self.selected_group_id:
            # Tự động chọn nhóm đầu tiên nếu người dùng chưa click chọn nhóm
            self.selected_group_id = tracked_groups[0]["id"]
            self.group_listbox.selection_clear(0, tk.END)
            self.group_listbox.selection_set(0)

        selected_group = next((g for g in tracked_groups if str(g["id"]) == str(self.selected_group_id)), tracked_groups[0])
        group_name = selected_group["name"] if selected_group else f"Nhóm {self.selected_group_id}"

        from ui.dialogs import StaffManagementDialog
        dialog = StaffManagementDialog(self.selected_group_id, group_name, self.core.zalo_service, parent=self)
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()
        self.wait_window(dialog)

        self.refresh_ticket_list()
        self.refresh_supported_tickets_tree()

    def update_ticket_header_info(self, ticket=None):
        if ticket is None:
            if not self.selected_ticket_id:
                self.ticket_info_label.configure(text="Vui lòng chọn một yêu cầu để xem chi tiết.")
                self.ticket_sla_label.configure(text="")
                return
            ticket = TicketDAO.get_ticket_by_id(self.selected_ticket_id)
            if not ticket:
                self.ticket_info_label.configure(text="Vui lòng chọn một yêu cầu để xem chi tiết.")
                self.ticket_sla_label.configure(text="")
                return

        requester = ticket.get("requester_name", "N/A")
        content = ticket.get("request_content", "")
        status = ticket.get("status", "PENDING")

        info_text = f"Khách hàng: {requester}\nYêu cầu: {content}"

        if status == "RESOLVED":
            if ticket.get("auto_resolved") == 1:
                sla_text = "Trạng thái: 🤖 Đã tự động hoàn thành bởi AI"
            else:
                sla_text = "Trạng thái: ✅ Đã hoàn thành (Resolved)"
            sla_color = "#7F8C8D"
        else:
            _, res_mins = TicketManager.get_remaining_sla(ticket)
            if res_mins is not None:
                # Tính ngưỡng 10% của thời gian SLA xử lý tối đa của nhóm
                group_sla = GroupDAO.get_sla_settings(ticket["group_id"])
                max_res = group_sla.get("max_resolve_time", 60)
                threshold_10pct = max_res * 0.10

                if res_mins < 0:
                    sla_text = f"SLA xử lý: ⚠️ Quá hạn {-res_mins} phút!"
                    sla_color = "#C0392B"  # Màu đỏ khi quá hạn
                elif res_mins <= threshold_10pct:
                    sla_text = f"SLA xử lý: ⚠️ Sắp hết hạn! Còn {res_mins} phút (< 10% SLA)"
                    sla_color = "#D35400"  # Màu vàng/cam khi còn dưới 10% SLA
                else:
                    sla_text = f"SLA xử lý: ⏳ Còn {res_mins} phút"
                    sla_color = "#27AE60"  # Màu xanh lá khi bình thường
            else:
                sla_text = ""
                sla_color = "#2C3E50"

        if self.ticket_info_label.cget("text") != info_text:
            self.ticket_info_label.configure(text=info_text)

        if self.ticket_sla_label.cget("text") != sla_text or self.ticket_sla_label.cget("fg") != sla_color:
            self.ticket_sla_label.configure(text=sla_text, fg=sla_color)

    def on_ticket_card_clicked(self, clicked_card):
        # Deselect tất cả card khác
        for card in self.ticket_cards:
            card.deselect()
            
        clicked_card.select()
        self.selected_ticket_id = clicked_card.ticket["id"]
        
        ticket = clicked_card.ticket
        self.update_ticket_header_info(ticket)
        if ticket["status"] == "RESOLVED":
            self.resolve_btn.configure(state="disabled")
            self.reopen_btn.configure(state="normal")
        else:
            self.resolve_btn.configure(state="normal")
            self.reopen_btn.configure(state="disabled")
        self.split_ticket_btn.configure(state="disabled")

    def on_tree_select(self, event):
        selected_items = self.response_tree.selection()
        if not selected_items:
            self.selected_ticket_id = None
            self.resolve_btn.configure(state="disabled")
            self.reopen_btn.configure(state="disabled")
            self.split_ticket_btn.configure(state="disabled")
            self.update_ticket_header_info(None)
            return
            
        item_id = selected_items[0]
        if item_id.startswith("ticket_"):
            ticket_id = int(item_id.split("_")[1])
        elif item_id.startswith("resp_"):
            parent_id = self.response_tree.parent(item_id)
            if parent_id and parent_id.startswith("ticket_"):
                ticket_id = int(parent_id.split("_")[1])
            else:
                ticket_id = None
        else:
            ticket_id = None
            
        self.selected_ticket_id = ticket_id
        has_resp_selection = any(item_id.startswith("resp_") for item_id in selected_items)

        if ticket_id:
            ticket = TicketDAO.get_ticket_by_id(ticket_id)
            if ticket:
                self.update_ticket_header_info(ticket)
                
                # Bật/tắt các nút chức năng tùy trạng thái của ticket
                if ticket["status"] == "RESOLVED":
                    self.resolve_btn.configure(state="disabled")
                    self.reopen_btn.configure(state="normal")
                else:
                    self.resolve_btn.configure(state="normal")
                    self.reopen_btn.configure(state="disabled")

        if has_resp_selection:
            self.split_ticket_btn.configure(state="normal")
        else:
            self.split_ticket_btn.configure(state="disabled")

    def on_resolve_clicked(self):
        if not self.selected_ticket_id:
            return
            
        ticket = TicketDAO.get_ticket_by_id(self.selected_ticket_id)
        if not ticket:
            return
            
        if messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn đóng Ticket #{ticket['id']} của {ticket['requester_name']}?"):
            self.core.ticket_manager.resolve_ticket(self.selected_ticket_id)
            self.refresh_ui()
            self.show_status_message(f"Đã đóng Ticket #{ticket['id']}.")

    def on_reopen_clicked(self):
        if not self.selected_ticket_id:
            return
            
        ticket = TicketDAO.get_ticket_by_id(self.selected_ticket_id)
        if not ticket:
            return
            
        if messagebox.askyesno("Xác nhận Mở Lại", f"Bạn có chắc muốn mở lại Ticket #{ticket['id']} của {ticket['requester_name']}?"):
            new_status = TicketDAO.reopen_ticket(self.selected_ticket_id)
            self.refresh_ui()
            self.show_status_message(f"Đã mở lại Ticket #{ticket['id']} (Trạng thái mới: {new_status}).")

    def on_split_ticket_clicked(self):
        selected_items = self.response_tree.selection()
        response_ids = []
        for item_id in selected_items:
            if item_id.startswith("resp_"):
                try:
                    response_ids.append(int(item_id.split("_")[1]))
                except ValueError:
                    pass

        if not response_ids:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất một tin nhắn phản hồi dưới cây Cột 3 để tách.")
            return

        if messagebox.askyesno("Xác nhận Tách Ticket", f"Bạn có chắc muốn tách {len(response_ids)} tin nhắn đã chọn thành một Ticket mới độc lập?"):
            new_ticket_id = self.core.ticket_manager.split_ticket(response_ids)
            if new_ticket_id:
                self.refresh_ui()
                self.show_status_message(f"Đã tách thành công {len(response_ids)} tin nhắn thành Ticket mới #{new_ticket_id}.")
                messagebox.showinfo("Thành công", f"Đã tách {len(response_ids)} tin nhắn thành Ticket mới #{new_ticket_id}!")

    def on_add_group_clicked(self):
        self.show_status_message("Đang tải danh sách nhóm từ Zalo...")
        zalo_groups = self.core.zalo_service.fetch_all_groups()
        
        tracked_groups = GroupDAO.get_all_groups()
        tracked_ids = [g["id"] for g in tracked_groups if g["is_tracked"] == 1]
        
        dialog = GroupSelectDialog(zalo_groups, tracked_ids, self.core.zalo_service, self)
        self.wait_window(dialog)
        
        selected_groups = dialog.get_selected_groups()
        if selected_groups is not None:
            selected_ids = [g["id"] for g in selected_groups]
            
            # Bỏ theo dõi các nhóm không nằm trong danh sách chọn
            for g in tracked_groups:
                if g["id"] not in selected_ids:
                    GroupDAO.set_tracking(g["id"], 0)
                    
            # Cập nhật/thêm các nhóm được chọn kèm tên chính xác
            for item in selected_groups:
                gid = item["id"]
                name = item["name"]
                GroupDAO.add_or_update_group(gid, name, 1)
                
            self.refresh_ui()
            self.show_status_message("Cập nhật danh sách nhóm theo dõi thành công.")
            
            # Khởi chạy đồng bộ tin nhắn cũ
            threading.Thread(target=self.core.start_startup_sync, daemon=True).start()

    def on_update_group_names_clicked(self):
        if not self.core.zalo_service.client:
            messagebox.showwarning("Cảnh báo", "Vui lòng kết nối Zalo trước khi cập nhật tên nhóm.")
            return
            
        tracked_groups = GroupDAO.get_tracked_groups()
        if not tracked_groups:
            messagebox.showinfo("Thông báo", "Chưa có nhóm nào trong danh sách theo dõi.")
            return
            
        self.show_status_message("Đang truy vấn Zalo để cập nhật lại tên các nhóm...")
        updated_count = 0
        
        for group in tracked_groups:
            gid = str(group["id"])
            info = self.core.zalo_service.fetch_group_info(gid)
            if info and info.get("name"):
                new_name = info["name"]
                if new_name != group["name"]:
                    GroupDAO.add_or_update_group(gid, new_name, is_tracked=1)
                    updated_count += 1
                    
        self.refresh_ui()
        self.show_status_message("Cập nhật tên các nhóm từ Zalo hoàn tất.")
        if updated_count > 0:
            messagebox.showinfo("Thành công", f"Đã cập nhật tên mới từ Zalo cho {updated_count} nhóm theo dõi!")
        else:
            messagebox.showinfo("Thông báo", "Tất cả nhóm theo dõi đều đã có tên chính xác từ Zalo!")

    def on_sla_clicked(self):
        target_group_id = self.selected_group_id
        if not target_group_id:
            return
            
        sla = GroupDAO.get_sla_settings(target_group_id)
        
        tracked_groups = GroupDAO.get_tracked_groups()
        group_name = next((g["name"] for g in tracked_groups if str(g["id"]) == str(target_group_id)), f"Nhóm {target_group_id}")
        
        dialog = SlaSettingsDialog(group_name, sla, self)
        self.wait_window(dialog)
        
        data = dialog.get_data()
        if data:
            GroupDAO.set_sla_settings(target_group_id, data["max_response_time"], data["max_resolve_time"])
            self.selected_group_id = target_group_id
            self.refresh_ui()
            self.show_status_message(f"Đã cập nhật SLA cho nhóm {group_name}.")

    def on_login_clicked(self):
        dialog = LoginDialog(self.core.zalo_service, self)
        self.wait_window(dialog)
        
        data = dialog.get_data()
        if data:
            self.show_status_message("Đang kiểm tra đăng nhập Zalo...")
            success = self.core.zalo_service.login(
                data["phone"],
                data["password"],
                data["cookies"],
                data["imei"],
                user_agent=data.get("user_agent")
            )
            if success:
                messagebox.showinfo("Thành công", "Đăng nhập Zalo thành công!")
                self.conn_status_label.configure(text="Trạng thái: Đã kết nối Zalo", fg="#2ECC71")
                
                # Bắt đầu lắng nghe và đồng bộ
                self.core.zalo_service.start_listening(self.core.on_message_received, self.core.on_connection_error)
                threading.Thread(target=self.core.start_startup_sync, daemon=True).start()
            else:
                messagebox.showerror("Thất bại", "Đăng nhập Zalo thất bại. Vui lòng kiểm tra lại thông tin và Cookies.")

    def on_resolve_clicked(self):
        if not self.selected_ticket_id:
            return
            
        ticket = TicketDAO.get_ticket_by_id(self.selected_ticket_id)
        if not ticket:
            return
            
        reply = messagebox.askyesno(
            "Xác nhận", 
            f"Bạn có chắc muốn đóng yêu cầu hỗ trợ của {ticket['requester_name']}?"
        )
        
        if reply:
            self.core.ticket_manager.resolve_ticket(self.selected_ticket_id)
            self.refresh_ticket_list()
            self.refresh_supported_tickets_tree()
            
            # Reset detail
            self.selected_ticket_id = None
            self.ticket_info_label.configure(text="Vui lòng chọn một yêu cầu để xem chi tiết.")
            self.resolve_btn.configure(state="disabled")
            self.split_ticket_btn.configure(state="disabled")

    def on_vacuum_clicked(self):
        try:
            run_vacuum()
            messagebox.showinfo("Thành công", "Đã tối ưu hóa và giải phóng dung lượng Database (VACUUM).")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể tối ưu hóa Database: {e}")

    def on_backup_clicked(self):
        try:
            from database import backup_db
            backup_db()
            messagebox.showinfo("Thành công", "Đã tạo bản sao lưu Database thành công trong backups/.")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể sao lưu Database: {e}")

    # ==========================================
    # CÁC HÀM CẬP NHẬT GIAO DIỆN TỪ CALLBACK
    # ==========================================
    def update_sync_progress(self, current, total):
        if current < total:
            self.progress_bar.configure(maximum=total, value=current)
            self.progress_bar.pack(side="right", padx=5)
        else:
            self.progress_bar.pack_forget()

    def show_status_message(self, message):
        self.status_label.configure(text=message)
        self.update_connection_ui()

    def update_connection_ui(self):
        if self.core.zalo_service.client:
            self.conn_status_label.configure(text="Trạng thái: Đã kết nối Zalo", fg="#2ECC71")
            self.login_btn.configure(text="🚪 Đăng xuất Zalo", command=self.on_logout_clicked)
        else:
            self.conn_status_label.configure(text="Trạng thái: Chưa kết nối Zalo", fg="#7F8C8D")
            self.login_btn.configure(text="🔑 Đăng nhập Zalo Web", command=self.on_login_clicked)

    def on_logout_clicked(self):
        reply = messagebox.askyesno(
            "Xác nhận đăng xuất",
            "Bạn có chắc chắn muốn đăng xuất khỏi Zalo? Tiến trình theo dõi tin nhắn sẽ tạm dừng."
        )
        if reply:
            self.show_status_message("Đang đăng xuất...")
            
            # Dừng lắng nghe tin nhắn trực tiếp
            self.core.zalo_service.stop_listening()
            
            # Xóa client và tệp session lưu trữ phiên làm việc
            self.core.zalo_service.client = None
            session_file = "zalo_session.json"
            try:
                import os
                if os.path.exists(session_file):
                    os.remove(session_file)
                logger.info("Đã xóa file phiên đăng nhập zalo_session.json.")
            except Exception as e:
                logger.error(f"Lỗi khi xóa file session: {e}")
                
            self.update_connection_ui()
            self.show_status_message("Đã đăng xuất tài khoản Zalo.")
            messagebox.showinfo("Thông báo", "Đã đăng xuất tài khoản Zalo thành công!")

    def add_live_message_to_tree(self, msg):
        import datetime
        from database import GroupDAO
        try:
            ts_ms = msg.get("timestamp")
            try:
                if ts_ms is not None:
                    ts_val = float(ts_ms)
                else:
                    ts_val = time.time() * 1000.0
            except Exception:
                ts_val = time.time() * 1000.0
                
            time_str = datetime.datetime.fromtimestamp(ts_val / 1000.0).strftime('%H:%M:%S')
            
            group_name = msg.get("group_name")
            if not group_name:
                g_id = msg.get("group_id")
                g_info = GroupDAO.get_group_by_id(g_id)
                group_name = g_info["name"] if g_info else f"Hội thoại {g_id}"
                
            sender = str(msg.get("sender_name") or "Người dùng")
            content = str(msg.get("content") or "")
            
            # Đưa lên dòng đầu tiên để tin mới nhất luôn ở trên
            self.live_tree.insert("", 0, values=(time_str, group_name, sender, content))
            
            # Giới hạn tối đa hiển thị 100 tin nhắn
            items = self.live_tree.get_children()
            if len(items) > 100:
                self.live_tree.delete(items[-1])
        except Exception as e:
            logger.error(f"Lỗi khi thêm tin nhắn live vào Treeview: {e}")

    def update_group_listbox_styles(self):
        tracked_groups = GroupDAO.get_tracked_groups()
        for idx, group in enumerate(tracked_groups):
            gid = group["id"]
            sla = GroupDAO.get_sla_settings(gid)
            pending_cnt, processing_cnt = TicketDAO.get_group_ticket_counts(gid)
            has_overdue = TicketDAO.has_overdue_pending_tickets(gid)

            if has_overdue:
                item_text = f"⚠️ [{pending_cnt}/{processing_cnt}] {group['name']} ({sla['max_response_time']}m/{sla['max_resolve_time']}m)"
            else:
                item_text = f"[{pending_cnt}/{processing_cnt}] {group['name']} ({sla['max_response_time']}m/{sla['max_resolve_time']}m)"

            if idx < self.group_listbox.size():
                current_text = self.group_listbox.get(idx)
                if current_text != item_text:
                    is_selected = str(gid) == str(self.selected_group_id)
                    self.group_listbox.delete(idx)
                    self.group_listbox.insert(idx, item_text)
                    if is_selected:
                        self.group_listbox.selection_set(idx)

                if has_overdue:
                    self.group_listbox.itemconfigure(idx, fg="#C0392B", bg="#FDEDEC", selectforeground="#C0392B")
                else:
                    self.group_listbox.itemconfigure(idx, fg="#2C3E50", bg="white", selectforeground="#FFFFFF")

    def update_sla_loop(self):
        """
        Duyệt qua các card và cập nhật bộ đếm ngược SLA mỗi 1 giây
        """
        for card in self.ticket_cards:
            card.update_timers()
        self.update_group_listbox_styles()
        self.update_ticket_header_info()
        self.after(1000, self.update_sla_loop)

    def load_window_geometry(self):
        config_path = "app_config.json"
        if os.path.exists(config_path):
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    geom = data.get("window_geometry")
                    if geom and isinstance(geom, str):
                        return geom
            except Exception as e:
                logger.error(f"Lỗi khi đọc kích thước cửa sổ từ {config_path}: {e}")
        return "1100x700"

    def save_window_geometry(self):
        config_path = "app_config.json"
        try:
            import json
            current_geom = self.geometry()
            data = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data["window_geometry"] = current_geom
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Đã lưu kích thước cửa sổ ứng dụng ({current_geom}) vào {config_path}.")
        except Exception as e:
            logger.error(f"Lỗi khi lưu kích thước cửa sổ: {e}")

    def on_close(self):
        reply = messagebox.askyesno(
            "Thoát ứng dụng", 
            "Bạn có chắc muốn thoát chương trình? Mọi cài đặt kết nối và hàng đợi sẽ được tắt an toàn."
        )
        if reply:
            self.save_window_geometry()
            self.core.graceful_shutdown()
            self.destroy()
