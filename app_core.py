import os
import time
import logging
import queue
import threading
import config
from database import initialize_database, GroupDAO, MessageDAO, TicketDAO, backup_db
from zalo_service import ZaloService
from ai_service import AIWorkerThread

setup_logging = None # Sẽ kế thừa từ bên ngoài hoặc gọi ở dưới
def init_logging():
    if not os.path.exists(config.LOG_DIR):
        os.makedirs(config.LOG_DIR)
        
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # App Logger
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()
    app_handler = logging.FileHandler(config.APP_LOG, encoding="utf-8")
    app_handler.setFormatter(formatter)
    app_logger.addHandler(app_handler)
    
    # AI Logger
    ai_logger = logging.getLogger("ai")
    ai_logger.setLevel(logging.INFO)
    if ai_logger.hasHandlers():
        ai_logger.handlers.clear()
    ai_handler = logging.FileHandler(config.AI_LOG, encoding="utf-8")
    ai_handler.setFormatter(formatter)
    ai_logger.addHandler(ai_handler)
    
    # Error Logger
    error_logger = logging.getLogger("error")
    error_logger.setLevel(logging.ERROR)
    if error_logger.hasHandlers():
        error_logger.handlers.clear()
    error_handler = logging.FileHandler(config.ERROR_LOG, encoding="utf-8")
    error_handler.setFormatter(formatter)
    error_logger.addHandler(error_handler)
    
    # Console output
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    app_logger.addHandler(console)
    ai_logger.addHandler(console)
    error_logger.addHandler(console)

init_logging()
logger = logging.getLogger("app")
ai_logger = logging.getLogger("ai")

class TicketManager:
    def __init__(self):
        pass

    def process_request(self, msg_data, confidence, needs_review):
        msg_id = msg_data["msg_id"]
        group_id = msg_data["group_id"]
        sender_name = msg_data["sender_name"]
        content = msg_data["content"]
        timestamp = msg_data["timestamp"]

        sla = GroupDAO.get_sla_settings(group_id)
        max_response = sla["max_response_time"]
        max_resolve = sla["max_resolve_time"]

        response_deadline = timestamp + (max_response * 60 * 1000)
        resolve_deadline = timestamp + (max_resolve * 60 * 1000)

        ticket_id = TicketDAO.create_ticket(
            group_id=group_id,
            request_msg_id=msg_id,
            requester_name=sender_name,
            request_content=content,
            created_at=timestamp,
            response_deadline=response_deadline,
            resolve_deadline=resolve_deadline,
            needs_review=needs_review
        )
        
        MessageDAO.update_classification(msg_id, "REQUEST", confidence, needs_review, ticket_id)
        logger.info(f"Đã tạo Ticket #{ticket_id} từ yêu cầu của {sender_name}.")
        return ticket_id

    def process_response(self, msg_data, target_ticket_id, confidence, needs_review):
        msg_id = msg_data["msg_id"]
        group_id = msg_data["group_id"]
        sender_name = msg_data["sender_name"]
        content = msg_data["content"]
        timestamp = msg_data["timestamp"]

        open_tickets = TicketDAO.get_unresolved_tickets(group_id)
        chosen_ticket_id = None
        heuristics_used = False

        if not open_tickets:
            logger.info(f"Nhận RESPONSE từ {sender_name} nhưng không có Ticket đang mở trong nhóm {group_id}.")
            MessageDAO.update_classification(msg_id, "RESPONSE", confidence, 1, None)
            return None

        elif len(open_tickets) == 1:
            chosen_ticket_id = open_tickets[0]["id"]
            logger.info(f"Tự động liên kết RESPONSE của {sender_name} vào Ticket duy nhất #{chosen_ticket_id}.")

        else:
            if target_ticket_id is not None:
                try:
                    ai_tid = int(target_ticket_id)
                    if any(t["id"] == ai_tid for t in open_tickets):
                        chosen_ticket_id = ai_tid
                        logger.info(f"Ghép RESPONSE vào Ticket #{chosen_ticket_id} theo đề xuất của AI.")
                except ValueError:
                    pass

            if chosen_ticket_id is None:
                content_lower = content.lower()
                for ticket in open_tickets:
                    req_name_lower = ticket["requester_name"].lower()
                    if req_name_lower in content_lower:
                        chosen_ticket_id = ticket["id"]
                        heuristics_used = True
                        logger.info(f"Heuristic: Ghép RESPONSE vào Ticket #{chosen_ticket_id} của {ticket['requester_name']} (Khớp tên).")
                        break

            if chosen_ticket_id is None:
                sorted_tickets = sorted(open_tickets, key=lambda t: t["created_at"], reverse=True)
                chosen_ticket_id = sorted_tickets[0]["id"]
                heuristics_used = True
                logger.info(f"Heuristic: Ghép RESPONSE vào Ticket mới nhất #{chosen_ticket_id} trong nhóm.")

        final_needs_review = needs_review
        if heuristics_used or final_needs_review:
            final_needs_review = 1
            if chosen_ticket_id:
                TicketDAO.set_ticket_review(chosen_ticket_id, 1)

        is_support_staff = GroupDAO.is_support_staff(group_id, sender_name)

        if chosen_ticket_id:
            ticket = TicketDAO.get_ticket_by_id(chosen_ticket_id)
            requester_clean = str(ticket["requester_name"]).strip().lower() if ticket else ""
            responder_clean = str(sender_name).strip().lower()

            # 1. Luôn lưu tin nhắn phản hồi vào lịch sử responses để hiển thị đầy đủ luồng trao đổi ở Cột 3
            TicketDAO.add_response(
                ticket_id=chosen_ticket_id,
                response_msg_id=msg_id,
                responder_name=sender_name,
                response_content=content,
                created_at=timestamp
            )

            # 2. Chỉ chuyển trạng thái PENDING -> PROCESSING (Tiếp nhận) nếu người gửi LÀ Nhân viên Hỗ trợ được phân công
            if responder_clean != requester_clean and is_support_staff:
                if ticket and ticket["status"] == "PENDING":
                    TicketDAO.update_ticket_status(chosen_ticket_id, "PROCESSING", acknowledged_at=timestamp)
                    logger.info(f"Ticket #{chosen_ticket_id} đã được tiếp nhận bởi KTV/Admin {sender_name}. Chuyển sang PROCESSING.")
            else:
                curr_status = ticket["status"] if ticket else "PENDING"
                logger.info(f"Ticket #{chosen_ticket_id}: Nhận thêm thông tin từ {sender_name}. Giữ nguyên trạng thái {curr_status}.")

            MessageDAO.update_classification(msg_id, "RESPONSE", confidence, final_needs_review, chosen_ticket_id)
            
        return chosen_ticket_id

    def process_resolve(self, msg_data, target_ticket_id, confidence, needs_review):
        msg_id = msg_data["msg_id"]
        group_id = msg_data["group_id"]
        sender_name = msg_data["sender_name"]
        content = msg_data["content"]
        timestamp = msg_data["timestamp"]

        open_tickets = TicketDAO.get_unresolved_tickets(group_id)
        chosen_ticket_id = None
        heuristics_used = False

        if not open_tickets:
            logger.info(f"Nhận RESOLVE từ {sender_name} nhưng không có Ticket đang mở trong nhóm {group_id}.")
            MessageDAO.update_classification(msg_id, "OTHER", confidence, 1, None)
            return None

        elif len(open_tickets) == 1:
            chosen_ticket_id = open_tickets[0]["id"]
            logger.info(f"Tự động liên kết RESOLVE của {sender_name} vào Ticket duy nhất #{chosen_ticket_id}.")

        else:
            if target_ticket_id is not None:
                try:
                    ai_tid = int(target_ticket_id)
                    if any(t["id"] == ai_tid for t in open_tickets):
                        chosen_ticket_id = ai_tid
                except ValueError:
                    pass

            if chosen_ticket_id is None:
                content_lower = content.lower()
                for ticket in open_tickets:
                    req_name_lower = ticket["requester_name"].lower()
                    if req_name_lower in content_lower:
                        chosen_ticket_id = ticket["id"]
                        heuristics_used = True
                        break

            if chosen_ticket_id is None:
                sorted_tickets = sorted(open_tickets, key=lambda t: t["created_at"], reverse=True)
                chosen_ticket_id = sorted_tickets[0]["id"]
                heuristics_used = True

        final_needs_review = needs_review
        if heuristics_used or final_needs_review:
            final_needs_review = 1
            if chosen_ticket_id:
                TicketDAO.set_ticket_review(chosen_ticket_id, 1)

        if chosen_ticket_id:
            TicketDAO.add_response(
                ticket_id=chosen_ticket_id,
                response_msg_id=msg_id,
                responder_name=sender_name,
                response_content=content,
                created_at=timestamp
            )

            # Đóng tự động Ticket này bởi AI (auto_resolved=1)
            TicketDAO.update_ticket_status(chosen_ticket_id, "RESOLVED", resolved_at=timestamp, auto_resolved=1)
            logger.info(f"AI: Tự động đóng Ticket #{chosen_ticket_id} (RESOLVED bởi AI) từ phản hồi của {sender_name}.")

            MessageDAO.update_classification(msg_id, "RESOLVE", confidence, final_needs_review, chosen_ticket_id)
            
        return chosen_ticket_id

    def resolve_ticket(self, ticket_id):
        current_time_ms = int(time.time() * 1000)
        TicketDAO.update_ticket_status(ticket_id, "RESOLVED", resolved_at=current_time_ms, auto_resolved=0)
        logger.info(f"Người dùng đóng Ticket #{ticket_id} (RESOLVED thủ công).")

    @staticmethod
    def get_remaining_sla(ticket):
        now_ms = int(time.time() * 1000)
        
        response_sla = None
        if ticket["status"] == "PENDING":
            response_sla = int((ticket["response_deadline"] - now_ms) / (60 * 1000))
            
        resolve_sla = None
        if ticket["status"] in ("PENDING", "PROCESSING"):
            resolve_sla = int((ticket["resolve_deadline"] - now_ms) / (60 * 1000))
            
        return response_sla, resolve_sla

class AppCore:
    def __init__(self, ui_callbacks=None):
        """
        ui_callbacks: dict chứa:
            - "update_ui": callback cập nhật giao diện
            - "sync_progress": callback tiến trình sync (current, total)
            - "status_message": callback hiện thông báo trạng thái (str)
        """
        logger.info("Khởi động nhân ứng dụng (AppCore)...")
        initialize_database()
        
        self.ui_callbacks = ui_callbacks or {}
        self.zalo_service = ZaloService()
        self.ticket_manager = TicketManager()
        self.ai_queue = queue.Queue(maxsize=config.AI_QUEUE_MAXSIZE)
        
        # Khởi chạy AI Worker Thread với callback
        self.ai_worker = AIWorkerThread(self.ai_queue, self.on_ai_classified)
        self.ai_worker.start()
        
        self.is_syncing = False

    def emit_ui_update(self):
        if "update_ui" in self.ui_callbacks:
            self.ui_callbacks["update_ui"]()

    def emit_sync_progress(self, current, total):
        if "sync_progress" in self.ui_callbacks:
            self.ui_callbacks["sync_progress"](current, total)

    def emit_status_message(self, message):
        if "status_message" in self.ui_callbacks:
            self.ui_callbacks["status_message"](message)

    def start_services(self):
        logged_in = self.zalo_service.auto_login()
        if logged_in:
            self.emit_status_message("Đã kết nối Zalo tự động thành công.")
            self.zalo_service.start_listening(self.on_message_received, self.on_connection_error)
            threading.Thread(target=self.start_startup_sync, daemon=True).start()
        else:
            self.emit_status_message("Chưa đăng nhập Zalo. Vui lòng cấu hình tài khoản.")

    @staticmethod
    def is_ai_eligible_message(content, metadata=None):
        """
        Kiểm tra xem tin nhắn có phải là tin nhắn văn bản thực sự để gửi AI phân loại hay không.
        Bỏ qua các tin nhắn dạng emotion, reaction, sticker, like, heart, marker, dict, link...
        """
        if not content:
            return False

        if isinstance(content, (dict, list)):
            return False

        if not isinstance(content, str):
            return False

        text = content.strip()
        if not text:
            return False

        # 1. Bỏ qua các định dạng tin nhắn hệ thống / media / emotion bọc trong ngoặc vuông [] hoặc {}
        if (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}")):
            return False

        # 2. Bỏ qua nếu metadata xác định thuộc loại sticker/emotion/reaction/like/heart/photo/file/link
        if metadata and isinstance(metadata, dict):
            msg_type = str(metadata.get("type", "")).lower()
            if msg_type in ("sticker", "reaction", "emotion", "like", "heart", "event", "undo", "photo", "file", "link"):
                return False

        # 3. Bỏ qua các biểu tượng emotion / emoji / reaction đơn lẻ
        EMOTION_KEYWORDS = {
            "👍", "❤️", "😍", "😊", "😂", "😭", "🙏", "👌", "🔥", "🎉", "👏", "🥰", "😮", "😢", "😠",
            "like", "heart", "reaction", "emotion", "sticker", "thả cảm xúc", "cảm xúc"
        }
        if text.lower() in EMOTION_KEYWORDS:
            return False

        return True

    def on_message_received(self, msg_data):
        group_id = str(msg_data.get("group_id", ""))
        msg_id = msg_data.get("msg_id", "")
        sender_id = msg_data.get("sender_id", "")
        sender_name = msg_data.get("sender_name", "Unknown")
        content = msg_data.get("content", "")
        timestamp = msg_data.get("timestamp", 0)

        # Lấy danh sách các nhóm đang được theo dõi
        tracked_groups = GroupDAO.get_tracked_groups()
        group_info = next((g for g in tracked_groups if str(g["id"]) == group_id), None)
        is_tracked = group_info is not None

        # 1. Gửi ngay sự kiện log live lên Bottom Panel UI cho TẤT CẢ tin nhắn nhận được từ Zalo
        if "on_live_message" in self.ui_callbacks:
            msg_copy = msg_data.copy()
            msg_copy["group_name"] = group_info["name"] if group_info else f"Hội thoại {group_id}"
            self.ui_callbacks["on_live_message"](msg_copy)
            logger.info(f"Live Message: Đã đẩy tin nhắn từ [{msg_copy['group_name']}] lên Bottom Panel.")

        # 2. Nếu nhóm không nằm trong danh sách theo dõi, bỏ qua không lưu DB
        if not is_tracked:
            logger.debug(f"Bỏ qua lưu DB tin nhắn {msg_id} vì hội thoại {group_id} không nằm trong danh sách theo dõi.")
            return

        # 3. Lưu tin nhắn thô của nhóm đang theo dõi vào SQLite
        MessageDAO.save_message(
            msg_id=msg_id,
            group_id=group_id,
            sender_id=sender_id,
            sender_name=sender_name,
            content=content,
            timestamp=timestamp
        )

        # 4. Chỉ phân loại AI đối với các tin nhắn dạng message văn bản thực sự
        if self.is_ai_eligible_message(content, msg_data.get("metadata")):
            if not self.ai_queue.full():
                self.enqueue_message(msg_data)
            else:
                logger.warning(f"Hàng đợi AI đầy. Tin nhắn {msg_id} tạm thời chỉ được lưu vào DB.")
        else:
            # Tự động gán nhãn OTHER trực tiếp cho tin nhắn emotion, reaction, sticker, like, heart...
            MessageDAO.update_classification(msg_id, "OTHER", 1.0, 0, None)
            logger.info(f"Đã bỏ qua AI phân loại cho tin nhắn dạng emotion/reaction/sticker (ID: {msg_id}). Tự động gán 'OTHER'.")

        self.emit_ui_update()

    def enqueue_message(self, msg_data):
        open_tickets = TicketDAO.get_unresolved_tickets(msg_data["group_id"])
        task = {
            "messages": [msg_data],
            "open_tickets": open_tickets
        }
        try:
            self.ai_queue.put(task, block=False)
        except queue.Full:
            logger.warning("Không thể đẩy tin nhắn vào AI Queue do hàng đợi đầy.")

    def refill_ai_queue(self):
        if self.ai_queue.qsize() >= 50:
            return
            
        unclassified = MessageDAO.get_unclassified_messages(limit=50)
        if not unclassified:
            return

        eligible_msgs = []
        for msg in unclassified:
            if not self.is_ai_eligible_message(msg.get("content")):
                # Tự động đánh dấu "OTHER" cho các tin nhắn không phải văn bản thực sự
                MessageDAO.update_classification(msg["msg_id"], "OTHER", 1.0, 0, None)
            else:
                eligible_msgs.append(msg)

        if not eligible_msgs:
            return

        grouped = {}
        for msg in eligible_msgs:
            gid = msg["group_id"]
            if gid not in grouped:
                grouped[gid] = []
            grouped[gid].append(msg)

        for gid, msgs in grouped.items():
            tracked_groups = GroupDAO.get_tracked_groups()
            if any(g["id"] == gid for g in tracked_groups):
                open_tickets = TicketDAO.get_unresolved_tickets(gid)
                task = {
                    "messages": msgs,
                    "open_tickets": open_tickets
                }
                try:
                    self.ai_queue.put(task, block=False)
                except queue.Full:
                    break

    def on_ai_classified(self, results):
        for res in results:
            msg_id = res["msg_id"]
            classification = res["classification"]
            target_ticket_id = res["target_ticket_id"]
            confidence = res["confidence"]
            
            msg_data = MessageDAO.get_message_by_id(msg_id)
            if not msg_data:
                continue

            needs_review = 1 if confidence < config.AI_CONFIDENCE_THRESHOLD or res.get("failed") else 0

            if res.get("failed"):
                MessageDAO.update_classification(msg_id, "OTHER", 0.0, 1, None)
            else:
                if classification == "REQUEST":
                    self.ticket_manager.process_request(msg_data, confidence, needs_review)
                elif classification == "RESPONSE":
                    self.ticket_manager.process_response(msg_data, target_ticket_id, confidence, needs_review)
                elif classification == "RESOLVE":
                    self.ticket_manager.process_resolve(msg_data, target_ticket_id, confidence, needs_review)
                else:
                    MessageDAO.update_classification(msg_id, "OTHER", confidence, needs_review, None)
                    
        self.refill_ai_queue()
        self.emit_ui_update()

    def start_startup_sync(self):
        if self.is_syncing:
            return
            
        self.is_syncing = True
        self.emit_status_message("Đang đồng bộ tin nhắn cũ khi khởi động...")
        logger.info("Bắt đầu đồng bộ tin nhắn cũ...")
        
        tracked_groups = GroupDAO.get_tracked_groups()
        total_groups = len(tracked_groups)
        
        for idx, group in enumerate(tracked_groups):
            group_id = group["id"]
            self.emit_sync_progress(idx, total_groups)
            self.emit_status_message(f"Đang đồng bộ nhóm: {group['name']}...")
            
            T_last = MessageDAO.get_last_timestamp(group_id)
            
            if T_last == 0:
                # Chạy lần đầu tiên cho nhóm này: Không đồng bộ các tin cũ
                # Lấy tin nhắn mới nhất hiện tại trên Zalo làm mốc
                messages = self.zalo_service.fetch_group_messages(group_id, count=1)
                if messages:
                    latest_msg = messages[0]
                    MessageDAO.save_message(
                        msg_id=latest_msg["msg_id"],
                        group_id=latest_msg["group_id"],
                        sender_id=latest_msg["sender_id"],
                        sender_name=latest_msg["sender_name"],
                        content=latest_msg["content"],
                        timestamp=latest_msg["timestamp"],
                        classification="OTHER",
                        confidence=1.0,
                        needs_review=0
                    )
                    logger.info(f"Nhóm {group['name']}: Khởi chạy lần đầu. Lưu tin nhắn mốc {latest_msg['msg_id']} tại {latest_msg['timestamp']}.")
                else:
                    # Nếu nhóm chưa có tin nhắn, lưu thời gian hiện tại làm mốc
                    now_ms = int(time.time() * 1000)
                    MessageDAO.save_message(
                        msg_id=f"init_marker_{group_id}_{now_ms}",
                        group_id=group_id,
                        sender_id="system",
                        sender_name="System",
                        content="[Khởi tạo mốc theo dõi]",
                        timestamp=now_ms,
                        classification="OTHER",
                        confidence=1.0,
                        needs_review=0
                    )
                    logger.info(f"Nhóm {group['name']}: Khởi chạy lần đầu (nhóm rỗng). Tạo mốc thời gian hiện tại: {now_ms}.")
                continue
                
            messages = self.zalo_service.fetch_group_messages(group_id, count=100)
            
            new_msgs_count = 0
            for msg in messages:
                if msg["timestamp"] > T_last:
                    MessageDAO.save_message(
                        msg_id=msg["msg_id"],
                        group_id=msg["group_id"],
                        sender_id=msg["sender_id"],
                        sender_name=msg["sender_name"],
                        content=msg["content"],
                        timestamp=msg["timestamp"]
                    )
                    new_msgs_count += 1
                    if "on_live_message" in self.ui_callbacks:
                        msg_copy = msg.copy()
                        msg_copy["group_name"] = group["name"]
                        self.ui_callbacks["on_live_message"](msg_copy)
            
            logger.info(f"Nhóm {group['name']}: Đã đồng bộ thêm {new_msgs_count} tin nhắn mới.")
            time.sleep(random.uniform(1.0, 2.5) if ZALO_AVAILABLE else 0.1)
            
        self.emit_sync_progress(total_groups, total_groups)
        self.emit_status_message("Đồng bộ hoàn tất.")
        logger.info("Đồng bộ tin nhắn cũ khi khởi động hoàn thành.")
        self.is_syncing = False
        
        self.refill_ai_queue()
        self.emit_ui_update()

    def on_connection_error(self, err_msg):
        logger.error(f"Mất kết nối Zalo: {err_msg}")
        self.emit_status_message(f"Mất kết nối Zalo: {err_msg}. Vui lòng đăng nhập lại.")

    def graceful_shutdown(self):
        logger.info("Bắt đầu quy trình tắt ứng dụng an toàn (Graceful Shutdown)...")
        self.emit_status_message("Đang tắt ứng dụng an toàn...")
        
        self.zalo_service.stop_listening()
        
        if self.ai_worker:
            self.ai_worker.stop()
            
        while not self.ai_queue.empty():
            try:
                self.ai_queue.get_nowait()
                self.ai_queue.task_done()
            except queue.Empty:
                break
                
        logger.info("Đang đóng SQLite kết nối...")
        try:
            backup_db()
            logger.info("Đã sao lưu database thành công trước khi thoát.")
        except Exception as e:
            logger.error(f"Lỗi khi sao lưu database lúc thoát: {e}")
            
        logger.info("Quy trình tắt ứng dụng an toàn hoàn tất.")

import random
from zalo_service import ZALO_AVAILABLE
