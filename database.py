import sqlite3
import shutil
import os
import time
import glob
import config

def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            is_tracked INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Dọn dẹp bản ghi rỗng/NULL nếu có từ trước
        conn.execute("DELETE FROM groups WHERE id IS NULL OR trim(id) = '';")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sla_settings (
            group_id TEXT PRIMARY KEY,
            max_response_time INTEGER NOT NULL,
            max_resolve_time INTEGER NOT NULL,
            FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            msg_id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            content TEXT,
            timestamp INTEGER NOT NULL,
            classification TEXT,
            confidence REAL,
            needs_review INTEGER DEFAULT 0,
            ticket_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            request_msg_id TEXT UNIQUE NOT NULL,
            requester_name TEXT NOT NULL,
            request_content TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            status TEXT DEFAULT 'PENDING',
            acknowledged_at INTEGER,
            resolved_at INTEGER,
            response_deadline INTEGER,
            resolve_deadline INTEGER,
            needs_review INTEGER DEFAULT 0,
            auto_resolved INTEGER DEFAULT 0,
            FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
        );
        """)
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN auto_resolved INTEGER DEFAULT 0;")
        except Exception:
            pass
        conn.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            response_msg_id TEXT UNIQUE NOT NULL,
            responder_name TEXT NOT NULL,
            response_content TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS group_support_staff (
            group_id TEXT NOT NULL,
            staff_name TEXT NOT NULL,
            PRIMARY KEY (group_id, staff_name),
            FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
        );
        """)
        conn.commit()

class GroupDAO:
    @staticmethod
    def get_group_support_staff(group_id):
        gid_str = str(group_id).strip() if group_id is not None else ""
        if not gid_str:
            return []
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT staff_name FROM group_support_staff WHERE group_id = ? ORDER BY staff_name ASC",
                (gid_str,)
            ).fetchall()
            return [row["staff_name"] for row in rows]

    @staticmethod
    def set_group_support_staff(group_id, staff_names):
        gid_str = str(group_id).strip() if group_id is not None else ""
        if not gid_str:
            return
        GroupDAO.add_group(gid_str, f"Nhóm {gid_str}", is_tracked=0)
        clean_names = sorted(list(set(str(name).strip() for name in staff_names if name and str(name).strip())))
        with get_connection() as conn:
            conn.execute("DELETE FROM group_support_staff WHERE group_id = ?", (gid_str,))
            for name in clean_names:
                conn.execute(
                    "INSERT OR REPLACE INTO group_support_staff (group_id, staff_name) VALUES (?, ?)",
                    (gid_str, name)
                )
            conn.commit()

    @staticmethod
    def is_support_staff(group_id, staff_name):
        gid_str = str(group_id).strip() if group_id is not None else ""
        sname = str(staff_name).strip() if staff_name is not None else ""
        if not gid_str or not sname:
            return True
        with get_connection() as conn:
            staff_list = [row["staff_name"] for row in conn.execute(
                "SELECT staff_name FROM group_support_staff WHERE group_id = ?", (gid_str,)
            ).fetchall()]

            # Nếu nhóm chưa từng được phân công nhân viên hỗ trợ ➔ Mặc định chấp nhận tất cả (tương thích ngược)
            if not staff_list:
                return True
            return sname in staff_list

    @staticmethod
    def add_group(group_id, name, is_tracked=0):
        if not group_id or not str(group_id).strip():
            group_id = "default_group"
        gid_str = str(group_id).strip()
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO groups (id, name, is_tracked) VALUES (?, ?, ?)",
                (gid_str, name, is_tracked)
            )
            conn.commit()

    @staticmethod
    def update_group_name(group_id, name):
        with get_connection() as conn:
            conn.execute(
                "UPDATE groups SET name = ? WHERE id = ?",
                (name, group_id)
            )
            conn.commit()

    @staticmethod
    def add_or_update_group(group_id, name, is_tracked=1):
        with get_connection() as conn:
            cursor = conn.execute("SELECT id FROM groups WHERE id = ?", (group_id,))
            if cursor.fetchone():
                conn.execute("UPDATE groups SET name = ?, is_tracked = ? WHERE id = ?", (name, is_tracked, group_id))
            else:
                conn.execute("INSERT INTO groups (id, name, is_tracked) VALUES (?, ?, ?)", (group_id, name, is_tracked))
            conn.commit()
            
    @staticmethod
    def set_tracking(group_id, is_tracked):
        with get_connection() as conn:
            conn.execute(
                "UPDATE groups SET is_tracked = ? WHERE id = ?",
                (is_tracked, group_id)
            )
            conn.commit()

    @staticmethod
    def get_tracked_groups():
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM groups WHERE is_tracked = 1")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_all_groups():
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM groups")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def set_sla_settings(group_id, max_response_time, max_resolve_time):
        gid_str = str(group_id).strip() if group_id is not None else ""
        if not gid_str:
            return
        GroupDAO.add_group(gid_str, f"Nhóm {gid_str}", is_tracked=0)
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sla_settings (group_id, max_response_time, max_resolve_time) VALUES (?, ?, ?)",
                (gid_str, int(max_response_time), int(max_resolve_time))
            )
            # Cập nhật lại thời hạn SLA cho các Ticket chưa đóng của nhóm
            conn.execute(
                """UPDATE tickets 
                   SET response_deadline = created_at + (? * 60 * 1000),
                       resolve_deadline = created_at + (? * 60 * 1000)
                   WHERE group_id = ? AND status IN ('PENDING', 'PROCESSING')""",
                (int(max_response_time), int(max_resolve_time), gid_str)
            )
            conn.commit()

    @staticmethod
    def get_sla_settings(group_id):
        gid_str = str(group_id).strip() if group_id is not None else ""
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sla_settings WHERE group_id = ?", (gid_str,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {
                "group_id": gid_str,
                "max_response_time": config.DEFAULT_MAX_RESPONSE_TIME,
                "max_resolve_time": config.DEFAULT_MAX_RESOLVE_TIME
            }

class MessageDAO:
    @staticmethod
    def save_message(msg_id, group_id, sender_id, sender_name, content, timestamp, classification=None, confidence=None, needs_review=0, ticket_id=None):
        # Ép kiểu an toàn cho tất cả các trường dữ liệu trước khi lưu SQLite
        msg_id = str(msg_id).strip() if msg_id is not None else ""
        if not group_id or not str(group_id).strip():
            group_id = "default_group"
        else:
            group_id = str(group_id).strip()
            
        sender_id = str(sender_id).strip() if sender_id is not None else ""
        sender_name = str(sender_name).strip() if sender_name is not None else ""
        
        # Đảm bảo group_id luôn tồn tại trong bảng groups để thỏa mãn ràng buộc khóa ngoại FOREIGN KEY
        GroupDAO.add_group(group_id, f"Nhóm {group_id}", is_tracked=0)

        # Xử lý biến content nếu bị truyền vào dưới dạng đối tượng lạ (ví dụ: MessageObject)
        if isinstance(content, str):
            pass
        elif isinstance(content, dict):
            content = content.get("content") or content.get("title") or str(content)
        elif hasattr(content, "content") and not callable(getattr(content, "content")):
            content = getattr(content, "content") or str(content)
        elif content is not None:
            content = str(content)
        else:
            content = ""

        # Phòng ngừa lỗi kiểu dữ liệu lạ cho timestamp
        try:
            if timestamp is None:
                timestamp = int(time.time() * 1000)
            elif not isinstance(timestamp, (int, float)):
                if isinstance(timestamp, str) and timestamp.isdigit():
                    timestamp = int(timestamp)
                else:
                    timestamp = int(time.time() * 1000)
            else:
                timestamp = int(timestamp)
        except Exception:
            timestamp = int(time.time() * 1000)

        with get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO messages 
                   (msg_id, group_id, sender_id, sender_name, content, timestamp, classification, confidence, needs_review, ticket_id) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, group_id, sender_id, sender_name, content, timestamp, classification, confidence, needs_review, ticket_id)
            )
            conn.commit()

    @staticmethod
    def get_last_timestamp(group_id):
        with get_connection() as conn:
            cursor = conn.execute("SELECT MAX(timestamp) as last_ts FROM messages WHERE group_id = ?", (group_id,))
            row = cursor.fetchone()
            return row["last_ts"] if row and row["last_ts"] is not None else 0

    @staticmethod
    def get_unclassified_messages(limit=100):
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM messages WHERE classification IS NULL ORDER BY timestamp ASC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_message_by_id(msg_id):
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM messages WHERE msg_id = ?", (msg_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_classification(msg_id, classification, confidence, needs_review=0, ticket_id=None):
        with get_connection() as conn:
            conn.execute(
                "UPDATE messages SET classification = ?, confidence = ?, needs_review = ?, ticket_id = ? WHERE msg_id = ?",
                (classification, confidence, needs_review, ticket_id, msg_id)
            )
            conn.commit()

    @staticmethod
    def get_sender_name_by_id(sender_id):
        if not sender_id:
            return None
        sid = str(sender_id).strip()
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT sender_name FROM messages 
                   WHERE sender_id = ? AND sender_name IS NOT NULL 
                     AND sender_name != '' AND sender_name != 'Người dùng Zalo' 
                   ORDER BY timestamp DESC LIMIT 1""",
                (sid,)
            )
            row = cursor.fetchone()
            return row["sender_name"] if row else None

class TicketDAO:
    @staticmethod
    def create_ticket(group_id, request_msg_id, requester_name, request_content, created_at, response_deadline, resolve_deadline, needs_review=0):
        if not group_id or not str(group_id).strip():
            group_id = "default_group"
        else:
            group_id = str(group_id).strip()
            
        GroupDAO.add_group(group_id, f"Nhóm {group_id}", is_tracked=0)
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR IGNORE INTO tickets 
                   (group_id, request_msg_id, requester_name, request_content, created_at, status, response_deadline, resolve_deadline, needs_review) 
                   VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)""",
                (group_id, request_msg_id, requester_name, request_content, created_at, response_deadline, resolve_deadline, needs_review)
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def add_response(ticket_id, response_msg_id, responder_name, response_content, created_at):
        with get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO responses 
                   (ticket_id, response_msg_id, responder_name, response_content, created_at) 
                   VALUES (?, ?, ?, ?, ?)""",
                (ticket_id, response_msg_id, responder_name, response_content, created_at)
            )
            conn.commit()

    @staticmethod
    def update_ticket_status(ticket_id, status, acknowledged_at=None, resolved_at=None, auto_resolved=0):
        with get_connection() as conn:
            if acknowledged_at and resolved_at:
                conn.execute(
                    "UPDATE tickets SET status = ?, acknowledged_at = ?, resolved_at = ?, auto_resolved = ? WHERE id = ?",
                    (status, acknowledged_at, resolved_at, auto_resolved, ticket_id)
                )
            elif acknowledged_at:
                conn.execute(
                    "UPDATE tickets SET status = ?, acknowledged_at = ? WHERE id = ?",
                    (status, acknowledged_at, ticket_id)
                )
            elif resolved_at:
                conn.execute(
                    "UPDATE tickets SET status = ?, resolved_at = ?, auto_resolved = ? WHERE id = ?",
                    (status, resolved_at, auto_resolved, ticket_id)
                )
            else:
                conn.execute(
                    "UPDATE tickets SET status = ?, auto_resolved = ? WHERE id = ?",
                    (status, auto_resolved, ticket_id)
                )
            conn.commit()

    @staticmethod
    def reopen_ticket(ticket_id):
        with get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM responses WHERE ticket_id = ?", (ticket_id,))
            row = cursor.fetchone()
            resp_cnt = row["cnt"] if row else 0
            
            new_status = "PROCESSING" if resp_cnt > 0 else "PENDING"
            conn.execute(
                "UPDATE tickets SET status = ?, resolved_at = NULL, auto_resolved = 0 WHERE id = ?",
                (new_status, ticket_id)
            )
            conn.commit()
            return new_status

    @staticmethod
    def get_unresolved_tickets(group_id):
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM tickets WHERE group_id = ? AND status IN ('PENDING', 'PROCESSING') ORDER BY created_at ASC",
                (group_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_group_ticket_counts(group_id):
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT 
                    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending_cnt,
                    SUM(CASE WHEN status = 'PROCESSING' THEN 1 ELSE 0 END) as processing_cnt
                   FROM tickets WHERE group_id = ?""",
                (group_id,)
            )
            row = cursor.fetchone()
            if row:
                pending = row["pending_cnt"] or 0
                processing = row["processing_cnt"] or 0
                return pending, processing
            return 0, 0

    @staticmethod
    def has_overdue_pending_tickets(group_id):
        gid_str = str(group_id).strip() if group_id is not None else ""
        if not gid_str:
            return False
        now_ms = int(time.time() * 1000)
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) as cnt FROM tickets 
                   WHERE group_id = ? AND status = 'PENDING' AND response_deadline < ?""",
                (gid_str, now_ms)
            )
            row = cursor.fetchone()
            return (row["cnt"] > 0) if row else False

    @staticmethod
    def get_group_sla_overdue_status(group_id):
        gid_str = str(group_id).strip() if group_id is not None else ""
        if not gid_str:
            return False, False
        now_ms = int(time.time() * 1000)
        with get_connection() as conn:
            cur1 = conn.execute(
                "SELECT COUNT(*) as cnt FROM tickets WHERE group_id = ? AND status = 'PENDING' AND response_deadline < ?",
                (gid_str, now_ms)
            )
            r1 = cur1.fetchone()
            has_response_overdue = (r1["cnt"] > 0) if r1 else False

            cur2 = conn.execute(
                "SELECT COUNT(*) as cnt FROM tickets WHERE group_id = ? AND status IN ('PENDING', 'PROCESSING') AND resolve_deadline < ?",
                (gid_str, now_ms)
            )
            r2 = cur2.fetchone()
            has_resolve_overdue = (r2["cnt"] > 0) if r2 else False

            return has_response_overdue, has_resolve_overdue

    @staticmethod
    def get_ticket_responses(ticket_id):
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM responses WHERE ticket_id = ? ORDER BY created_at ASC",
                (ticket_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_response_by_id(response_id):
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM responses WHERE id = ?", (response_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def delete_response_by_id(response_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM responses WHERE id = ?", (response_id,))
            conn.commit()

    @staticmethod
    def delete_ticket(ticket_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
            conn.execute("DELETE FROM responses WHERE ticket_id = ?", (ticket_id,))
            conn.commit()

    @staticmethod
    def relink_responses(source_ticket_id, target_ticket_id):
        with get_connection() as conn:
            conn.execute("UPDATE responses SET ticket_id = ? WHERE ticket_id = ?", (target_ticket_id, source_ticket_id))
            conn.execute("UPDATE messages SET ticket_id = ? WHERE ticket_id = ?", (target_ticket_id, source_ticket_id))
            conn.commit()

    @staticmethod
    def get_supported_tickets(group_id):
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT t.*, MAX(r.created_at) as latest_response_time 
                   FROM tickets t 
                   LEFT JOIN responses r ON t.id = r.ticket_id 
                   WHERE t.group_id = ? AND t.status IN ('PROCESSING', 'RESOLVED') 
                   GROUP BY t.id 
                   ORDER BY latest_response_time DESC, t.created_at DESC""",
                (group_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_ticket_by_id(ticket_id):
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def set_ticket_review(ticket_id, needs_review):
        with get_connection() as conn:
            conn.execute("UPDATE tickets SET needs_review = ? WHERE id = ?", (needs_review, ticket_id))
            conn.commit()

    @staticmethod
    def get_dashboard_group_metrics(from_ts, to_ts):
        """
        Lấy thống kê chỉ số SLA theo từng nhóm Zalo trong khoảng thời gian [from_ts, to_ts]
        """
        tracked_groups = GroupDAO.get_tracked_groups()
        results = []
        now_ms = int(time.time() * 1000)
        
        with get_connection() as conn:
            for group in tracked_groups:
                gid = group["id"]
                gname = group["name"]
                
                # 1. Số open ticket tồn tại trước từ ngày (created < from_ts và chưa đóng hoặc đóng sau from_ts)
                c1 = conn.execute(
                    """SELECT COUNT(*) as cnt FROM tickets 
                       WHERE group_id = ? AND created_at < ? 
                         AND (status IN ('PENDING', 'PROCESSING') OR resolved_at >= ?)""",
                    (gid, from_ts, from_ts)
                ).fetchone()["cnt"]
                
                # 2. Số ticket mới trong khoảng thời gian [from_ts, to_ts]
                c2 = conn.execute(
                    """SELECT COUNT(*) as cnt FROM tickets 
                       WHERE group_id = ? AND created_at >= ? AND created_at <= ?""",
                    (gid, from_ts, to_ts)
                ).fetchone()["cnt"]

                # 2b. Số ticket đã đóng (RESOLVED) trong khoảng thời gian [from_ts, to_ts]
                c2_res = conn.execute(
                    """SELECT COUNT(*) as cnt FROM tickets 
                       WHERE group_id = ? AND status = 'RESOLVED' 
                         AND resolved_at >= ? AND resolved_at <= ?""",
                    (gid, from_ts, to_ts)
                ).fetchone()["cnt"]
                
                # 3. Số ticket quá hạn SLA tiếp nhận (response_deadline) trong khoảng thời gian
                c3 = conn.execute(
                    """SELECT COUNT(*) as cnt FROM tickets 
                       WHERE group_id = ? AND created_at >= ? AND created_at <= ?
                         AND ((acknowledged_at IS NOT NULL AND acknowledged_at > response_deadline)
                              OR (acknowledged_at IS NULL AND response_deadline < ?))""",
                    (gid, from_ts, to_ts, min(to_ts, now_ms))
                ).fetchone()["cnt"]

                # 4. Số ticket quá hạn SLA xử lý (resolve_deadline) trong khoảng thời gian
                c4 = conn.execute(
                    """SELECT COUNT(*) as cnt FROM tickets 
                       WHERE group_id = ? AND created_at >= ? AND created_at <= ?
                         AND ((resolved_at IS NOT NULL AND resolved_at > resolve_deadline)
                              OR (status IN ('PENDING', 'PROCESSING') AND resolve_deadline < ?))""",
                    (gid, from_ts, to_ts, min(to_ts, now_ms))
                ).fetchone()["cnt"]

                # 5. Số open ticket còn tồn tại tới hiện tại (status PENDING/PROCESSING)
                c5 = conn.execute(
                    """SELECT COUNT(*) as cnt FROM tickets 
                       WHERE group_id = ? AND status IN ('PENDING', 'PROCESSING')""",
                    (gid,)
                ).fetchone()["cnt"]

                results.append({
                    "group_id": gid,
                    "group_name": gname,
                    "open_before": c1,
                    "new_tickets": c2,
                    "resolved_tickets": c2_res,
                    "overdue_response": c3,
                    "overdue_resolve": c4,
                    "open_remaining": c5
                })
        return results

    @staticmethod
    def get_dashboard_staff_metrics(from_ts, to_ts, group_id=None):
        """
        Lấy thống kê chỉ số hỗ trợ theo từng nhân viên / KTV trong khoảng thời gian [from_ts, to_ts].
        Nếu group_id được chỉ định, chỉ lọc số liệu trong nhóm Zalo đó.
        """
        results = []
        gid_str = str(group_id).strip() if group_id is not None and str(group_id).strip() != "" and str(group_id).upper() != "ALL" else None
        now_ms = int(time.time() * 1000)

        with get_connection() as conn:
            # Lấy danh sách nhân viên hỗ trợ từ bảng group_support_staff (nếu có cấu hình)
            if gid_str:
                assigned_rows = conn.execute(
                    "SELECT staff_name FROM group_support_staff WHERE group_id = ? ORDER BY staff_name ASC",
                    (gid_str,)
                ).fetchall()
                if assigned_rows:
                    staff_names = [r["staff_name"] for r in assigned_rows]
                else:
                    staff_rows = conn.execute(
                        """SELECT DISTINCT r.responder_name as staff_name 
                           FROM responses r 
                           JOIN tickets t ON r.ticket_id = t.id 
                           WHERE t.group_id = ? AND r.responder_name IS NOT NULL AND trim(r.responder_name) != ''""",
                        (gid_str,)
                    ).fetchall()
                    staff_names = sorted(list(set(row["staff_name"] for row in staff_rows)))
            else:
                assigned_rows = conn.execute(
                    """SELECT DISTINCT gss.staff_name 
                       FROM group_support_staff gss 
                       JOIN groups g ON gss.group_id = g.id 
                       WHERE g.is_tracked = 1 ORDER BY gss.staff_name ASC"""
                ).fetchall()
                if assigned_rows:
                    staff_names = [r["staff_name"] for r in assigned_rows]
                else:
                    staff_rows = conn.execute(
                        """SELECT DISTINCT responder_name as staff_name FROM responses WHERE responder_name IS NOT NULL AND trim(responder_name) != ''"""
                    ).fetchall()
                    staff_names = sorted(list(set(row["staff_name"] for row in staff_rows)))
            
            for sname in staff_names:
                if gid_str:
                    # 1. Số ticket đã tiếp nhận trong nhóm [from_ts, to_ts]
                    ack_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE t.group_id = ? AND r.responder_name = ? AND r.created_at >= ? AND r.created_at <= ?""",
                        (gid_str, sname, from_ts, to_ts)
                    ).fetchone()["cnt"]

                    # 2. Số ticket đã hoàn thành (RESOLVED) trong nhóm [from_ts, to_ts] do nhân viên này tham gia
                    resolved_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE t.group_id = ? AND r.responder_name = ? AND t.status = 'RESOLVED' 
                             AND t.resolved_at >= ? AND t.resolved_at <= ?""",
                        (gid_str, sname, from_ts, to_ts)
                    ).fetchone()["cnt"]

                    # 3. Số ticket quá hạn xử lý trong nhóm do nhân viên này tham gia
                    overdue_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE t.group_id = ? AND r.responder_name = ? AND t.created_at >= ? AND t.created_at <= ?
                             AND ((t.resolved_at IS NOT NULL AND t.resolved_at > t.resolve_deadline)
                                  OR (t.status IN ('PENDING', 'PROCESSING') AND t.resolve_deadline < ?))""",
                        (gid_str, sname, from_ts, to_ts, min(to_ts, now_ms))
                    ).fetchone()["cnt"]

                    # 4. Số ticket còn open trong nhóm (PENDING/PROCESSING) mà nhân viên này đang tham gia
                    open_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE t.group_id = ? AND r.responder_name = ? AND t.status IN ('PENDING', 'PROCESSING')""",
                        (gid_str, sname)
                    ).fetchone()["cnt"]
                else:
                    # 1. Số ticket đã tiếp nhận trong khoảng [from_ts, to_ts]
                    ack_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE r.responder_name = ? AND r.created_at >= ? AND r.created_at <= ?""",
                        (sname, from_ts, to_ts)
                    ).fetchone()["cnt"]

                    # 2. Số ticket đã hoàn thành (RESOLVED) trong khoảng [from_ts, to_ts] do nhân viên này tham gia
                    resolved_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE r.responder_name = ? AND t.status = 'RESOLVED' 
                             AND t.resolved_at >= ? AND t.resolved_at <= ?""",
                        (sname, from_ts, to_ts)
                    ).fetchone()["cnt"]

                    # 3. Số ticket quá hạn xử lý do nhân viên này tham gia
                    overdue_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE r.responder_name = ? AND t.created_at >= ? AND t.created_at <= ?
                             AND ((t.resolved_at IS NOT NULL AND t.resolved_at > t.resolve_deadline)
                                  OR (t.status IN ('PENDING', 'PROCESSING') AND t.resolve_deadline < ?))""",
                        (sname, from_ts, to_ts, min(to_ts, now_ms))
                    ).fetchone()["cnt"]

                    # 4. Số ticket còn open (PENDING/PROCESSING) mà nhân viên này đang tham gia
                    open_cnt = conn.execute(
                        """SELECT COUNT(DISTINCT t.id) as cnt 
                           FROM tickets t 
                           JOIN responses r ON t.id = r.ticket_id 
                           WHERE r.responder_name = ? AND t.status IN ('PENDING', 'PROCESSING')""",
                        (sname,)
                    ).fetchone()["cnt"]

                if ack_cnt > 0 or resolved_cnt > 0 or open_cnt > 0 or overdue_cnt > 0:
                    results.append({
                        "staff_name": sname,
                        "acknowledged": ack_cnt,
                        "completed": resolved_cnt,
                        "overdue_resolve": overdue_cnt,
                        "open_remaining": open_cnt
                    })
        return results

def run_vacuum():
    with get_connection() as conn:
        conn.execute("VACUUM")
        conn.commit()

def backup_db():
    if not os.path.exists(config.BACKUP_DIR):
        os.makedirs(config.BACKUP_DIR)
    
    timestamp = int(time.time())
    backup_file = os.path.join(config.BACKUP_DIR, f"zalo_tracker_backup_{timestamp}.db")
    
    if os.path.exists(config.DB_PATH):
        shutil.copy(config.DB_PATH, backup_file)
        
        backups = sorted(glob.glob(os.path.join(config.BACKUP_DIR, "zalo_tracker_backup_*.db")), key=os.path.getmtime)
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                try:
                    os.remove(old_backup)
                except Exception:
                    pass
