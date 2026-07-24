import os
import unittest
import time
import shutil
import sqlite3

# Thiết lập biến môi trường giả lập để chạy test mà không cần file .env thực tế
os.environ["GEMINI_API_KEY"] = "mock_api_key_for_testing"

# Chạy test trong môi trường tạm thời
import config
config.DB_PATH = "test_zalo_cs_tracker.db"

import database
from database import GroupDAO, MessageDAO, TicketDAO, initialize_database
from app_core import TicketManager, AppCore

class TestZaloCsTracker(unittest.TestCase):
    def setUp(self):
        # Đảm bảo dọn dẹp DB cũ trước khi test
        if os.path.exists(config.DB_PATH):
            try:
                os.remove(config.DB_PATH)
            except Exception:
                pass
        initialize_database()
        with database.get_connection() as conn:
            conn.execute("DELETE FROM responses;")
            conn.execute("DELETE FROM tickets;")
            conn.execute("DELETE FROM messages;")
            conn.execute("DELETE FROM sla_settings;")
            conn.execute("DELETE FROM groups;")
            conn.commit()
        self.tm = TicketManager()

    def tearDown(self):
        # Dọn dẹp sau khi test
        if os.path.exists(config.DB_PATH):
            try:
                os.remove(config.DB_PATH)
            except Exception:
                pass

    def test_database_initialization(self):
        self.assertTrue(os.path.exists(config.DB_PATH))
        with database.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row["name"] for row in cursor.fetchall()]
            self.assertIn("groups", tables)
            self.assertIn("sla_settings", tables)
            self.assertIn("messages", tables)
            self.assertIn("tickets", tables)
            self.assertIn("responses", tables)

    def test_group_dao(self):
        GroupDAO.add_group("test_g1", "Nhóm test 1", 1)
        groups = GroupDAO.get_tracked_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["id"], "test_g1")
        self.assertEqual(groups[0]["name"], "Nhóm test 1")

        GroupDAO.set_sla_settings("test_g1", 10, 30)
        sla = GroupDAO.get_sla_settings("test_g1")
        self.assertEqual(sla["max_response_time"], 10)
        self.assertEqual(sla["max_resolve_time"], 30)

    def test_message_dao_duplicates(self):
        # Tạo nhóm trước để thỏa mãn khóa ngoại
        GroupDAO.add_group("g1", "Group 1", 1)
        
        MessageDAO.save_message("m1", "g1", "u1", "User 1", "Hello", 1000)
        MessageDAO.save_message("m1", "g1", "u1", "User 1", "Hello duplicate", 1000)
        
        with database.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM messages WHERE msg_id = 'm1'")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["content"], "Hello")

    def test_ticket_manager_request(self):
        GroupDAO.add_group("g1", "Group 1", 1)
        GroupDAO.set_sla_settings("g1", 15, 60)

        msg_data = {
            "msg_id": "m1",
            "group_id": "g1",
            "sender_id": "u1",
            "sender_name": "Khách hàng A",
            "content": "Tôi cần hỗ trợ lỗi đăng nhập database",
            "timestamp": int(time.time() * 1000)
        }

        MessageDAO.save_message(
            msg_data["msg_id"], msg_data["group_id"], msg_data["sender_id"],
            msg_data["sender_name"], msg_data["content"], msg_data["timestamp"]
        )

        ticket_id = self.tm.process_request(msg_data, 0.95, 0)
        self.assertIsNotNone(ticket_id)

        ticket = TicketDAO.get_ticket_by_id(ticket_id)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["requester_name"], "Khách hàng A")
        self.assertEqual(ticket["status"], "PENDING")
        self.assertEqual(ticket["response_deadline"], msg_data["timestamp"] + 15 * 60 * 1000)
        self.assertEqual(ticket["resolve_deadline"], msg_data["timestamp"] + 60 * 60 * 1000)

        msg_db = MessageDAO.get_message_by_id("m1")
        self.assertEqual(msg_db["classification"], "REQUEST")
        self.assertEqual(msg_db["ticket_id"], ticket_id)

    def test_ticket_manager_response_pairing(self):
        GroupDAO.add_group("g1", "Group 1", 1)
        GroupDAO.set_sla_settings("g1", 15, 60)

        now_ms = int(time.time() * 1000)

        req_msg = {
            "msg_id": "req_1",
            "group_id": "g1",
            "sender_id": "client_1",
            "sender_name": "Khách hàng A",
            "content": "Lỗi phần mềm",
            "timestamp": now_ms
        }
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        ticket_id = self.tm.process_request(req_msg, 0.90, 0)

        resp_msg = {
            "msg_id": "resp_1",
            "group_id": "g1",
            "sender_id": "staff_1",
            "sender_name": "KTV Hỗ Trợ",
            "content": "Tôi đang kiểm tra nhé bạn A",
            "timestamp": now_ms + 2 * 60 * 1000
        }
        MessageDAO.save_message(resp_msg["msg_id"], resp_msg["group_id"], resp_msg["sender_id"], resp_msg["sender_name"], resp_msg["content"], resp_msg["timestamp"])
        
        linked_tid = self.tm.process_response(resp_msg, target_ticket_id=None, confidence=0.85, needs_review=0)
        self.assertEqual(linked_tid, ticket_id)

        ticket = TicketDAO.get_ticket_by_id(ticket_id)
        self.assertEqual(ticket["status"], "PROCESSING")
        self.assertEqual(ticket["acknowledged_at"], resp_msg["timestamp"])

        responses = TicketDAO.get_ticket_responses(ticket_id)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["responder_name"], "KTV Hỗ Trợ")
        self.assertEqual(responses[0]["response_content"], "Tôi đang kiểm tra nhé bạn A")

    def test_customer_followup_message_does_not_change_pending_status(self):
        # Kiểm thử khách hàng gửi tin nhắn/ảnh bổ sung -> Ticket vẫn giữ nguyên trạng thái PENDING
        GroupDAO.add_group("g2", "Group 2", 1)
        now_ms = int(time.time() * 1000)

        req_msg = {
            "msg_id": "req_cust_1",
            "group_id": "g2",
            "sender_id": "cust_1",
            "sender_name": "Anh Nam (Khách)",
            "content": "Báo lỗi hệ thống",
            "timestamp": now_ms
        }
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        ticket_id = self.tm.process_request(req_msg, 0.95, 0)

        # Khách hàng gửi tiếp hình ảnh minh họa lỗi
        followup_msg = {
            "msg_id": "req_cust_2",
            "group_id": "g2",
            "sender_id": "cust_1",
            "sender_name": "Anh Nam (Khách)",
            "content": "[Hình ảnh đính kèm minh họa lỗi]",
            "timestamp": now_ms + 30 * 1000
        }
        MessageDAO.save_message(followup_msg["msg_id"], followup_msg["group_id"], followup_msg["sender_id"], followup_msg["sender_name"], followup_msg["content"], followup_msg["timestamp"])
        
        self.tm.process_response(followup_msg, target_ticket_id=ticket_id, confidence=0.90, needs_review=0)
        
        # Đảm bảo trạng thái vẫn là PENDING (Chờ xử lý), chưa chuyển sang PROCESSING
        ticket = TicketDAO.get_ticket_by_id(ticket_id)
        self.assertEqual(ticket["status"], "PENDING")

    def test_sla_remaining_calculation(self):
        now_ms = int(time.time() * 1000)
        ticket = {
            "status": "PENDING",
            "response_deadline": now_ms + 10 * 60 * 1000,
            "resolve_deadline": now_ms + 45 * 60 * 1000,
        }
        resp_sla, res_sla = TicketManager.get_remaining_sla(ticket)
        self.assertIn(resp_sla, (9, 10))
        self.assertIn(res_sla, (44, 45))

        ticket_overdue = {
            "status": "PENDING",
            "response_deadline": now_ms - 5 * 60 * 1000,
            "resolve_deadline": now_ms - 20 * 60 * 1000,
        }
        resp_sla, res_sla = TicketManager.get_remaining_sla(ticket_overdue)
        self.assertEqual(resp_sla, -5)
        self.assertEqual(res_sla, -20)

    def test_raw_test_data_payloads_parsing(self):
        # Kiểm thử phân tích dữ liệu thô đã thu thập từ Zalo
        test_data_dir = os.path.join(os.path.dirname(__file__), "test_data")
        live_file = os.path.join(test_data_dir, "raw_live_messages.json")
        groups_file = os.path.join(test_data_dir, "raw_groups_list.json")

        if os.path.exists(live_file):
            import json
            with open(live_file, "r", encoding="utf-8") as f:
                messages = json.load(f)
            self.assertGreater(len(messages), 0)
            
            # Đảm bảo dName (Tên hiển thị thật từ Zalo Web WebSocket) được trích xuất chính xác
            sample_msg = messages[0]
            msg_obj = sample_msg.get("message_object", {})
            dname = msg_obj.get("dName") or msg_obj.get("senderName") or msg_obj.get("authorName")
            self.assertTrue(dname is not None and len(dname) > 0)
            self.assertIn(dname, ["Thái Nguyễn", "Thu Ha"])

        if os.path.exists(groups_file):
            import json
            with open(groups_file, "r", encoding="utf-8") as f:
                groups_data = json.load(f)
            self.assertIn("gridVerMap", groups_data)
            grid_ver_map = groups_data["gridVerMap"]
            self.assertGreater(len(grid_ver_map), 100)
            # Kiểm tra trích xuất Group ID từ gridVerMap
            group_ids = list(grid_ver_map.keys())
            self.assertIn("4920757830183394806", group_ids)

    def test_fetch_all_groups_real_payload_parsing(self):
        # Kiểm thử tích hợp hàm fetch_all_groups với dữ liệu thô real từ Zalo API
        import json
        from zalo_service import ZaloService
        
        test_data_dir = os.path.join(os.path.dirname(__file__), "test_data")
        groups_list_file = os.path.join(test_data_dir, "raw_groups_list.json")
        groups_detail_file = os.path.join(test_data_dir, "raw_groups_detail.json")
        
        if os.path.exists(groups_list_file) and os.path.exists(groups_detail_file):
            with open(groups_list_file, "r", encoding="utf-8") as f:
                raw_groups_list = json.load(f)
            with open(groups_detail_file, "r", encoding="utf-8") as f:
                raw_groups_detail = json.load(f)
                
            class MockZaloClient:
                def fetchAllGroups(self):
                    return raw_groups_list
                    
                def fetchGroupInfo(self, chunk_dict):
                    # Kiểm tra chính xác tham số truyền vào phải là từ điển dict
                    if not isinstance(chunk_dict, dict):
                        raise ValueError("fetchGroupInfo parameter must be a dict!")
                    
                    # Trả về dữ liệu detail nếu có trong raw_groups_detail
                    combined = {"gridInfoMap": {}}
                    for gid in chunk_dict.keys():
                        if gid in raw_groups_detail:
                            detail = raw_groups_detail[gid]
                            if "gridInfoMap" in detail:
                                combined["gridInfoMap"].update(detail["gridInfoMap"])
                    return combined

            service = ZaloService()
            service.client = MockZaloClient()
            
            groups_result = service.fetch_all_groups()
            self.assertGreater(len(groups_result), 100)
            
            # Kiểm tra trích xuất chính xác tên thật của các nhóm từ dữ liệu real
            group_292 = next((g for g in groups_result if g["id"] == "2924193156720930600"), None)
            self.assertIsNotNone(group_292)
            self.assertEqual(group_292["name"], "Triển khai HKD cho Suntaxi")

            group_514 = next((g for g in groups_result if g["id"] == "5147254814944180946"), None)
            self.assertIsNotNone(group_514)
            self.assertEqual(group_514["name"], "40 năm LQĐ - Video Gala")

    def test_message_object_sanitization(self):
        # Kiểm thử xử lý an toàn khi content hoặc các trường khác bị truyền đối tượng lạ (MessageObject)
        class MockMessageObject:
            def __init__(self, text):
                self.content = text
            def __str__(self):
                return f"<MessageObject: {self.content}>"

        fake_msg_obj = MockMessageObject("Lỗi màn hình")
        
        # Test 1: Đảm bảo MessageDAO.save_message lưu thành công đối tượng MessageObject mà không báo lỗi SQLite
        MessageDAO.save_message(
            msg_id="m_obj_1",
            group_id="g_obj_1",
            sender_id="s_obj_1",
            sender_name="Khách A",
            content=fake_msg_obj,
            timestamp=fake_msg_obj
        )

        saved = MessageDAO.get_message_by_id("m_obj_1")
        self.assertIsNotNone(saved)
        self.assertIn("Lỗi màn hình", saved["content"])
        self.assertIsInstance(saved["timestamp"], int)

    def test_foreign_key_auto_group_creation(self):
        # Kiểm thử việc tự động tạo group_id trong bảng groups trước khi chèn tin nhắn/ticket hoàn toàn không vi phạm ràng buộc khóa ngoại
        new_untracked_gid = "untracked_group_9999"
        
        # Đảm bảo group chưa tồn tại
        all_groups_before = [g["id"] for g in GroupDAO.get_all_groups()]
        self.assertNotIn(new_untracked_gid, all_groups_before)

        # Lưu tin nhắn với group_id chưa từng tồn tại
        MessageDAO.save_message(
            msg_id="m_fk_test",
            group_id=new_untracked_gid,
            sender_id="s_fk_test",
            sender_name="Khách Mới",
            content="Hỗ trợ gấp",
            timestamp=int(time.time() * 1000)
        )

        # Kiểm tra tin nhắn và group_id đã được tự động khởi tạo thành công
        all_groups_after = [g["id"] for g in GroupDAO.get_all_groups()]
        self.assertIn(new_untracked_gid, all_groups_after)
        saved_msg = MessageDAO.get_message_by_id("m_fk_test")
        self.assertIsNotNone(saved_msg)

    def test_is_ai_eligible_message_filtering(self):
        # Kiểm thử bộ lọc loại bỏ các tin nhắn dạng emotion, reaction, sticker, like, heart... khỏi AI classification
        from app_core import AppCore
        
        # Tin nhắn văn bản thực sự -> ĐỦ ĐIỀU KIỆN AI (True)
        self.assertTrue(AppCore.is_ai_eligible_message("Báo giá cho mình với"))
        self.assertTrue(AppCore.is_ai_eligible_message("Lỗi phần mềm không kết nối được"))
        
        # Tin nhắn dạng emotion, sticker, icon, marker -> KHÔNG ĐỦ ĐIỀU KIỆN AI (False)
        self.assertFalse(AppCore.is_ai_eligible_message("[Nhãn dán (Sticker ID: 123)]"))
        self.assertFalse(AppCore.is_ai_eligible_message("[Thả cảm xúc: 👍]"))
        self.assertFalse(AppCore.is_ai_eligible_message("[Khởi tạo mốc theo dõi]"))
        self.assertFalse(AppCore.is_ai_eligible_message("👍"))
        self.assertFalse(AppCore.is_ai_eligible_message("❤️"))
        self.assertFalse(AppCore.is_ai_eligible_message("like"))
        self.assertFalse(AppCore.is_ai_eligible_message("heart"))
        self.assertFalse(AppCore.is_ai_eligible_message("", {"type": "sticker"}))
        self.assertFalse(AppCore.is_ai_eligible_message("photo", {"type": "photo"}))

    def test_filter_with_real_collected_live_messages(self):
        # Kiểm thử bộ lọc trực tiếp trên 28 gói tin nhắn thô thực tế từ Zalo WebSocket (raw_live_messages.json)
        import json
        from app_core import AppCore
        
        test_data_dir = os.path.join(os.path.dirname(__file__), "test_data")
        live_file = os.path.join(test_data_dir, "raw_live_messages.json")
        
        if os.path.exists(live_file):
            with open(live_file, "r", encoding="utf-8") as f:
                messages = json.load(f)
            
            eligible_count = 0
            filtered_count = 0
            for msg_item in messages:
                msg_obj = msg_item.get("message_object") or msg_item
                content = msg_obj.get("content") or msg_item.get("content")
                metadata = msg_obj.get("metadata") or msg_item.get("metadata")
                
                is_eligible = AppCore.is_ai_eligible_message(content, metadata)
                if is_eligible:
                    eligible_count += 1
                else:
                    filtered_count += 1

            # Đảm bảo phân loại đúng: có cả tin nhắn văn bản thực sự và tin nhắn reaction/link bị lọc bỏ
            self.assertGreater(eligible_count, 0)
            self.assertGreater(filtered_count, 0)

    def test_group_dao_set_and_get_sla_settings(self):
        # Kiểm thử việc lưu và tải lại thiết lập SLA cho nhóm Zalo
        test_gid = "sla_group_123"
        GroupDAO.add_group(test_gid, "Nhóm Test SLA", 1)
        
        # Cập nhật SLA mới: Tiếp nhận 10 phút, Xử lý 45 phút
        GroupDAO.set_sla_settings(test_gid, 10, 45)
        
        # Lấy SLA đã lưu
        sla = GroupDAO.get_sla_settings(test_gid)
        self.assertEqual(sla["max_response_time"], 10)
        self.assertEqual(sla["max_resolve_time"], 45)

    def test_resolve_ticket_updates_group_ticket_counts(self):
        # Kiểm thử việc đóng ticket (resolve) làm giảm số lượng ticket PROCESSING của nhóm
        GroupDAO.add_group("g_resolve_test", "Group Resolve Test", 1)
        now_ms = int(time.time() * 1000)

        # 1. Khách gửi yêu cầu -> PENDING
        req_msg = {"msg_id": "m_r1", "group_id": "g_resolve_test", "sender_id": "c1", "sender_name": "Khách B", "content": "Cần hỗ trợ", "timestamp": now_ms}
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        tid = self.tm.process_request(req_msg, 0.9, 0)
        
        pending_cnt, processing_cnt = TicketDAO.get_group_ticket_counts("g_resolve_test")
        self.assertEqual((pending_cnt, processing_cnt), (1, 0))

        # 2. KTV phản hồi -> PROCESSING
        resp_msg = {"msg_id": "m_r2", "group_id": "g_resolve_test", "sender_id": "ktv1", "sender_name": "KTV", "content": "Đang xử lý nhé", "timestamp": now_ms + 1000}
        MessageDAO.save_message(resp_msg["msg_id"], resp_msg["group_id"], resp_msg["sender_id"], resp_msg["sender_name"], resp_msg["content"], resp_msg["timestamp"])
        self.tm.process_response(resp_msg, target_ticket_id=tid, confidence=0.9, needs_review=0)
        
        pending_cnt, processing_cnt = TicketDAO.get_group_ticket_counts("g_resolve_test")
        self.assertEqual((pending_cnt, processing_cnt), (0, 1))

        # 3. Đóng ticket -> RESOLVED -> processing_cnt giảm về 0
        self.tm.resolve_ticket(tid)
        pending_cnt, processing_cnt = TicketDAO.get_group_ticket_counts("g_resolve_test")
        self.assertEqual((pending_cnt, processing_cnt), (0, 0))

    def test_has_overdue_pending_tickets(self):
        # Kiểm thử việc cảnh báo quá hạn tiếp nhận (PENDING + trễ SLA) và tự động khôi phục khi KTV phản hồi
        gid = "g_overdue_test"
        GroupDAO.add_group(gid, "Group Overdue Test", 1)
        now_ms = int(time.time() * 1000)

        # 1. Tạo ticket quá hạn tiếp nhận (created_at từ 2 tiếng trước, response SLA 15m)
        old_ts = now_ms - (120 * 60 * 1000)
        req_msg = {"msg_id": "m_overdue", "group_id": gid, "sender_id": "c2", "sender_name": "Khách C", "content": "Báo lỗi trễ", "timestamp": old_ts}
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        tid = self.tm.process_request(req_msg, 0.95, 0)

        # Ban đầu ticket PENDING trễ hạn -> has_overdue_pending_tickets = True
        self.assertTrue(TicketDAO.has_overdue_pending_tickets(gid))

        # 2. KTV phản hồi -> chuyển sang PROCESSING -> has_overdue_pending_tickets trở về False
        resp_msg = {"msg_id": "m_ack", "group_id": gid, "sender_id": "ktv2", "sender_name": "KTV B", "content": "Dạ em đã nhận tin", "timestamp": now_ms}
        MessageDAO.save_message(resp_msg["msg_id"], resp_msg["group_id"], resp_msg["sender_id"], resp_msg["sender_name"], resp_msg["content"], resp_msg["timestamp"])
        self.tm.process_response(resp_msg, target_ticket_id=tid, confidence=0.9, needs_review=0)

        # Sau khi tiếp nhận -> Trở về trạng thái bình thường (False)
        self.assertFalse(TicketDAO.has_overdue_pending_tickets(gid))

    def test_window_geometry_persistence(self):
        # Kiểm thử tính năng ghi và nạp kích thước cửa sổ ứng dụng (app_config.json)
        import json
        config_path = "app_config.json"
        test_geom = "1280x750+100+100"
        
        # Ghi dữ liệu kích thước giả lập
        data = {"window_geometry": test_geom}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            
        # Đọc dữ liệu kích thước bằng logic của MainWindow
        from ui.main_window import MainWindow
        mw = MainWindow.__new__(MainWindow)
        loaded_geom = mw.load_window_geometry()
        
        self.assertEqual(loaded_geom, test_geom)

    def test_ai_auto_resolve_and_reopen_ticket(self):
        # Kiểm thử AI tự động đóng ticket khi nhận tin nhắn cảm ơn/hoàn thành và nút mở lại ticket
        gid = "g_ai_resolve_test"
        GroupDAO.add_group(gid, "Group AI Resolve Test", 1)
        now_ms = int(time.time() * 1000)

        # 1. Tạo ticket
        req_msg = {"msg_id": "m_req_ai", "group_id": gid, "sender_id": "c_ai", "sender_name": "Khách D", "content": "Báo lỗi kết nối", "timestamp": now_ms}
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        tid = self.tm.process_request(req_msg, 0.95, 0)

        # 2. Khách gửi tin nhắn cảm ơn / báo xong -> AI nhận dạng RESOLVE -> Tự động đóng ticket (auto_resolved=1)
        res_msg = {"msg_id": "m_thanks", "group_id": gid, "sender_id": "c_ai", "sender_name": "Khách D", "content": "Dạ em đã kiểm tra lại, ok rồi cảm ơn anh", "timestamp": now_ms + 2000}
        MessageDAO.save_message(res_msg["msg_id"], res_msg["group_id"], res_msg["sender_id"], res_msg["sender_name"], res_msg["content"], res_msg["timestamp"])
        self.tm.process_resolve(res_msg, target_ticket_id=tid, confidence=0.92, needs_review=0)

        t_db = TicketDAO.get_ticket_by_id(tid)
        self.assertEqual(t_db["status"], "RESOLVED")
        self.assertEqual(t_db["auto_resolved"], 1)

        # 3. Người dùng phát hiện AI nhận dạng sai -> Bấm "🔓 Mở Lại Yêu Cầu" -> Khôi phục ticket
        new_status = TicketDAO.reopen_ticket(tid)
        t_reopened = TicketDAO.get_ticket_by_id(tid)
        self.assertEqual(t_reopened["auto_resolved"], 0)
        self.assertIn(t_reopened["status"], ("PENDING", "PROCESSING"))

    def test_dashboard_metrics_queries(self):
        # Kiểm thử truy vấn số liệu Dashboard cho nhóm và nhân viên
        gid = "g_dash_test"
        GroupDAO.add_group(gid, "Group Dashboard Test", 1)
        now_ms = int(time.time() * 1000)

        # Tạo ticket mới
        req_msg = {"msg_id": "m_dash_req", "group_id": gid, "sender_id": "c_dash", "sender_name": "Khách E", "content": "Báo lỗi máy in", "timestamp": now_ms}
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        tid = self.tm.process_request(req_msg, 0.95, 0)

        # Nhân viên phản hồi
        resp_msg = {"msg_id": "m_dash_resp", "group_id": gid, "sender_id": "ktv_dash", "sender_name": "KTV Hỗ Trợ A", "content": "Đang kiểm tra nhé", "timestamp": now_ms + 1000}
        MessageDAO.save_message(resp_msg["msg_id"], resp_msg["group_id"], resp_msg["sender_id"], resp_msg["sender_name"], resp_msg["content"], resp_msg["timestamp"])
        self.tm.process_response(resp_msg, target_ticket_id=tid, confidence=0.9, needs_review=0)

        # Đọc dữ liệu dashboard trong khoảng thời gian bao trùm
        from_ts = now_ms - 3600000
        to_ts = now_ms + 3600000

        g_metrics = TicketDAO.get_dashboard_group_metrics(from_ts, to_ts)
        self.assertTrue(len(g_metrics) > 0)
        dash_g = next((g for g in g_metrics if g["group_id"] == gid), None)
        self.assertIsNotNone(dash_g)
        self.assertEqual(dash_g["new_tickets"], 1)
        self.assertIn("resolved_tickets", dash_g)

        s_metrics = TicketDAO.get_dashboard_staff_metrics(from_ts, to_ts)
        self.assertTrue(len(s_metrics) > 0)
        dash_s = next((s for s in s_metrics if s["staff_name"] == "KTV Hỗ Trợ A"), None)
        self.assertIsNotNone(dash_s)
        self.assertEqual(dash_s["acknowledged"], 1)
        self.assertIn("overdue_resolve", dash_s)

        # Lọc theo group_id cụ thể
        s_metrics_grp = TicketDAO.get_dashboard_staff_metrics(from_ts, to_ts, group_id=gid)
        self.assertTrue(len(s_metrics_grp) > 0)
        dash_s_grp = next((s for s in s_metrics_grp if s["staff_name"] == "KTV Hỗ Trợ A"), None)
        self.assertIsNotNone(dash_s_grp)
        self.assertEqual(dash_s_grp["acknowledged"], 1)
        self.assertIn("overdue_resolve", dash_s_grp)

    def test_center_window_over_parent(self):
        # Kiểm thử logic canh giữa popup window trên cùng màn hình với window chính
        from ui.dialogs import center_window_over_parent
        class MockWindow:
            def __init__(self, w, h, rx, ry):
                self._w, self._h, self._rx, self._ry = w, h, rx, ry
                self.geom = ""
            def update_idletasks(self): pass
            def winfo_width(self): return self._w
            def winfo_height(self): return self._h
            def winfo_reqwidth(self): return self._w
            def winfo_reqheight(self): return self._h
            def winfo_rootx(self): return self._rx
            def winfo_rooty(self): return self._ry
            def winfo_exists(self): return True
            def geometry(self, g): self.geom = g

        # Giả lập window chính trên màn hình phụ (VD: rootx=1920, rooty=100, width=1280, height=720)
        main_win = MockWindow(1280, 720, 1920, 100)
        popup_win = MockWindow(400, 300, 0, 0)

        center_window_over_parent(popup_win, main_win)

        # cx = 1920 + (1280 - 400) // 2 = 1920 + 440 = 2360
        # cy = 100 + (720 - 300) // 2 = 100 + 210 = 310
        self.assertEqual(popup_win.geom, "400x300+2360+310")

    def test_group_support_staff_filtering(self):
        # 1. Kiểm thử GroupDAO support staff
        gid = "g_staff_test"
        GroupDAO.add_group(gid, "Group Staff Test", 1)
        
        # Ban đầu chưa phân công ➔ is_support_staff trả về True (tương thích ngược)
        self.assertTrue(GroupDAO.is_support_staff(gid, "KTV Bat Ky"))

        # Phân công danh sách Nhân viên Hỗ trợ
        GroupDAO.set_group_support_staff(gid, ["KTV Chinh A", "KTV Chinh B"])
        staff_list = GroupDAO.get_group_support_staff(gid)
        self.assertEqual(staff_list, ["KTV Chinh A", "KTV Chinh B"])

        self.assertTrue(GroupDAO.is_support_staff(gid, "KTV Chinh A"))
        self.assertFalse(GroupDAO.is_support_staff(gid, "Khách Hàng X"))

        # 2. Kiểm thử TicketManager.process_response khi khách/người không thuộc danh sách phản hồi
        now_ms = int(time.time() * 1000)
        req_msg = {"msg_id": "m_staff_req", "group_id": gid, "sender_id": "c_staff", "sender_name": "Khách Hàng X", "content": "Cần hỗ trợ gấp", "timestamp": now_ms}
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        tid = self.tm.process_request(req_msg, 0.95, 0)

        # Phản hồi từ Khách Hàng X (Không phải KTV) ➔ Giữ nguyên PENDING
        non_staff_resp = {"msg_id": "m_non_staff", "group_id": gid, "sender_id": "c_staff", "sender_name": "Khách Hàng X", "content": "Tin nhắn gửi thêm", "timestamp": now_ms + 1000}
        MessageDAO.save_message(non_staff_resp["msg_id"], non_staff_resp["group_id"], non_staff_resp["sender_id"], non_staff_resp["sender_name"], non_staff_resp["content"], non_staff_resp["timestamp"])
        self.tm.process_response(non_staff_resp, target_ticket_id=tid, confidence=0.9, needs_review=0)

        t_after_non_staff = TicketDAO.get_ticket_by_id(tid)
        self.assertEqual(t_after_non_staff["status"], "PENDING")

        # Phản hồi từ KTV Chinh A (Là KTV được phân công) ➔ Tiếp nhận, chuyển sang PROCESSING
        staff_resp = {"msg_id": "m_valid_staff", "group_id": gid, "sender_id": "ktv_a", "sender_name": "KTV Chinh A", "content": "Chào anh, tôi đang xử lý", "timestamp": now_ms + 2000}
        MessageDAO.save_message(staff_resp["msg_id"], staff_resp["group_id"], staff_resp["sender_id"], staff_resp["sender_name"], staff_resp["content"], staff_resp["timestamp"])
        self.tm.process_response(staff_resp, target_ticket_id=tid, confidence=0.9, needs_review=0)

        t_after_staff = TicketDAO.get_ticket_by_id(tid)
        self.assertEqual(t_after_staff["status"], "PROCESSING")
        self.assertIsNotNone(t_after_staff["acknowledged_at"])

    def test_image_message_filtering_and_ticket_creation(self):
        # 1. Kiểm thử lọc tin nhắn hình ảnh / media trong AppCore
        self.assertFalse(AppCore.is_ai_eligible_message("[Hình ảnh đính kèm: http://zalo.me/photo.jpg]"))
        self.assertFalse(AppCore.is_ai_eligible_message("Hình ảnh"))
        self.assertFalse(AppCore.is_ai_eligible_message("Đã gửi một hình ảnh"))
        self.assertFalse(AppCore.is_ai_eligible_message("[Tập tin đính kèm: error_log.txt]"))
        self.assertTrue(AppCore.is_ai_eligible_message("Hệ thống báo lỗi 500 không đăng nhập được"))

        # 2. Giả lập kịch bản: Khách gửi Tin nhắn 1 (Ảnh) rồi Tin nhắn 2 (Message chữ)
        gid = "g_img_test"
        GroupDAO.add_group(gid, "Group Image Test", 1)
        now_ms = int(time.time() * 1000)

        img_msg = {"msg_id": "msg_img_1", "group_id": gid, "sender_id": "c_img", "sender_name": "Khách Báo Lỗi", "content": "[Hình ảnh đính kèm: http://photo.png]", "timestamp": now_ms}
        text_msg = {"msg_id": "msg_text_2", "group_id": gid, "sender_id": "c_img", "sender_name": "Khách Báo Lỗi", "content": "Phần mềm bị treo khi bấm lưu hóa đơn", "timestamp": now_ms + 1000}

        # Tin nhắn 1 (Hình ảnh) ➔ is_ai_eligible_message trả về False ➔ Gán "OTHER"
        self.assertFalse(AppCore.is_ai_eligible_message(img_msg["content"]))

        # Tin nhắn 2 (Message chữ) ➔ is_ai_eligible_message trả về True ➔ Tạo Ticket REQUEST mới thành công
        self.assertTrue(AppCore.is_ai_eligible_message(text_msg["content"]))
        tid = self.tm.process_request(text_msg, 0.95, 0)
        self.assertIsNotNone(tid)

        t_created = TicketDAO.get_ticket_by_id(tid)
        self.assertEqual(t_created["requester_name"], "Khách Báo Lỗi")
        self.assertEqual(t_created["request_content"], "Phần mềm bị treo khi bấm lưu hóa đơn")
        self.assertEqual(t_created["status"], "PENDING")

    def test_split_ticket_smart_linking(self):
        # 1. Tạo nhóm và Ticket gốc với 2 tin nhắn phản hồi
        gid = "g_split_test"
        GroupDAO.add_group(gid, "Group Split Test", 1)
        GroupDAO.set_group_support_staff(gid, ["KTV Nam"])

        now_ms = int(time.time() * 1000)
        req_msg = {"msg_id": "m_split_orig", "group_id": gid, "sender_id": "c1", "sender_name": "Khách Alpha", "content": "Lỗi 1: Không in được phiếu xuất", "timestamp": now_ms}
        MessageDAO.save_message(req_msg["msg_id"], req_msg["group_id"], req_msg["sender_id"], req_msg["sender_name"], req_msg["content"], req_msg["timestamp"])
        orig_tid = self.tm.process_request(req_msg, 0.95, 0)

        # Phản hồi 1 từ Khách Alpha (Yêu cầu mới gửi nhầm dưới dạng phản hồi)
        resp1_msg = {"msg_id": "m_split_r1", "group_id": gid, "sender_id": "c1", "sender_name": "Khách Alpha", "content": "Lỗi 2: Không xuất được file Excel", "timestamp": now_ms + 1000}
        MessageDAO.save_message(resp1_msg["msg_id"], resp1_msg["group_id"], resp1_msg["sender_id"], resp1_msg["sender_name"], resp1_msg["content"], resp1_msg["timestamp"])
        self.tm.process_response(resp1_msg, target_ticket_id=orig_tid, confidence=0.9, needs_review=0)

        # Phản hồi 2 từ KTV Nam trả lời cho Lỗi 2
        resp2_msg = {"msg_id": "m_split_r2", "group_id": gid, "sender_id": "ktv1", "sender_name": "KTV Nam", "content": "Đã hướng dẫn xuất lại file Excel", "timestamp": now_ms + 2000}
        MessageDAO.save_message(resp2_msg["msg_id"], resp2_msg["group_id"], resp2_msg["sender_id"], resp2_msg["sender_name"], resp2_msg["content"], resp2_msg["timestamp"])
        self.tm.process_response(resp2_msg, target_ticket_id=orig_tid, confidence=0.9, needs_review=0)

        # Lấy danh sách response IDs của orig_tid
        responses = TicketDAO.get_ticket_responses(orig_tid)
        self.assertEqual(len(responses), 2)
        resp_ids = [r["id"] for r in responses]

        # 2. Thực hiện Tách Ticket từ 2 phản hồi được chọn
        new_tid = self.tm.split_ticket(resp_ids)
        self.assertIsNotNone(new_tid)
        self.assertNotEqual(orig_tid, new_tid)

        # Kiểm tra Ticket mới: Yêu cầu gốc là Lỗi 2
        new_ticket = TicketDAO.get_ticket_by_id(new_tid)
        self.assertEqual(new_ticket["requester_name"], "Khách Alpha")
        self.assertEqual(new_ticket["request_content"], "Lỗi 2: Không xuất được file Excel")
        
        # Vì có phản hồi 2 từ KTV Nam ➔ Ticket mới tự động chuyển sang PROCESSING
        self.assertEqual(new_ticket["status"], "PROCESSING")
        self.assertIsNotNone(new_ticket["acknowledged_at"])

        # Kiểm tra các phản hồi của Ticket mới có chứa Phản hồi 2 từ KTV Nam
        new_responses = TicketDAO.get_ticket_responses(new_tid)
        self.assertEqual(len(new_responses), 1)
        self.assertEqual(new_responses[0]["responder_name"], "KTV Nam")

        # Kiểm tra Ticket cũ không còn phản hồi nào
        old_responses = TicketDAO.get_ticket_responses(orig_tid)
        self.assertEqual(len(old_responses), 0)

if __name__ == "__main__":
    unittest.main()
