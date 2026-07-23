import json
import os
import random
import time
import logging
import threading
import config

logger = logging.getLogger("app")

# Đọc ghi file session
SESSION_FILE = "zalo_session.json"

def save_session(phone, password, cookies, imei, user_agent=None):
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "phone": phone,
                "password": password,
                "cookies": cookies,
                "imei": imei,
                "user_agent": user_agent
            }, f, ensure_ascii=False, indent=4)
        logger.info("Đã lưu phiên đăng nhập Zalo thành công.")
    except Exception as e:
        logger.error(f"Không thể lưu phiên đăng nhập Zalo: {e}")

def load_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Không thể tải phiên đăng nhập Zalo: {e}")
    return None

try:
    from zlapi import ZaloAPI
    ZALO_AVAILABLE = True
except ImportError:
    ZALO_AVAILABLE = False
    class ZaloAPI:
        pass

class ZaloBot(ZaloAPI if ZALO_AVAILABLE else object):
    def __init__(self, phone, password, imei=None, session_cookies=None, **kwargs):
        self.phone = phone
        self.password = password
        self.imei = imei or str(random.randint(10**14, 10**15 - 1))
        self.session_cookies = session_cookies
        self.message_callback = None
        self.error_callback = None
        self.known_live_groups = set()
        
        user_agent = kwargs.get("user_agent")
        if ZALO_AVAILABLE and user_agent:
            try:
                import zlapi._state
                import zlapi._util
                zlapi._state.headers["User-Agent"] = user_agent
                zlapi._util.HEADERS["User-Agent"] = user_agent
                
                if "Windows" in user_agent:
                    zlapi._state.headers["sec-ch-ua-platform"] = '"Windows"'
                    zlapi._util.HEADERS["sec-ch-ua-platform"] = '"Windows"'
                elif "Macintosh" in user_agent or "Mac OS" in user_agent:
                    zlapi._state.headers["sec-ch-ua-platform"] = '"macOS"'
                    zlapi._util.HEADERS["sec-ch-ua-platform"] = '"macOS"'
                elif "Linux" in user_agent:
                    zlapi._state.headers["sec-ch-ua-platform"] = '"Linux"'
                    zlapi._util.HEADERS["sec-ch-ua-platform"] = '"Linux"'
                logger.info(f"ZaloBot: Đã monkey-patch User-Agent thành công: {user_agent}")
            except Exception as patch_err:
                logger.error(f"ZaloBot: Lỗi khi monkey-patch User-Agent: {patch_err}")
        
        if ZALO_AVAILABLE:
            try:
                # Đổi tên session_cookies thành cookies cho tương thích với hàm init của ZaloAPI
                super().__init__(phone, password, imei=self.imei, cookies=session_cookies, **kwargs)
                logger.info("Khởi tạo ZaloBot thành công.")
            except Exception as e:
                logger.error(f"Khởi tạo ZaloBot thất bại: {e}")
                raise e

    def onMessage(self, mid, author_id, message, message_object, thread_id, thread_type, ts=None, metadata=None, msg=None, **kwargs):
        if thread_id:
            self.known_live_groups.add(str(thread_id))
            
        mid = str(mid) if mid is not None else ""
        thread_id = str(thread_id) if thread_id is not None else ""
        author_id = str(author_id) if author_id is not None else ""
        
        # Xử lý an toàn biến content nếu message truyền vào là đối tượng MessageObject hoặc dict
        content = message
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

        sender_name = "Người dùng Zalo"
        
        # Nếu ts không được truyền trực tiếp, trích xuất từ message_object
        if ts is None:
            if message_object:
                if isinstance(message_object, dict):
                    ts = message_object.get("timestamp") or message_object.get("ts")
                else:
                    ts = getattr(message_object, "timestamp", None) or getattr(message_object, "ts", None)
            if ts is None:
                ts = int(time.time() * 1000)
        else:
            try:
                ts = int(ts)
            except Exception:
                ts = int(time.time() * 1000)

        # Nếu metadata không được truyền trực tiếp, trích xuất từ message_object
        if metadata is None and message_object:
            if isinstance(message_object, dict):
                metadata = message_object.get("metadata")
            else:
                metadata = getattr(message_object, "metadata", None)

        if message_object:
            if isinstance(message_object, dict):
                sender_name = message_object.get("dName") or message_object.get("senderName") or message_object.get("authorName") or sender_name
            else:
                sender_name = getattr(message_object, "dName", None) or getattr(message_object, "senderName", None) or getattr(message_object, "authorName", None) or sender_name

        sender_name = str(sender_name) if sender_name is not None else "Người dùng Zalo"

        # Chuẩn hóa tin nhắn đặc biệt
        if not content:
            if metadata and isinstance(metadata, dict):
                msg_type = metadata.get("type", "")
                if msg_type == "sticker":
                    content = f"[Nhãn dán (Sticker ID: {metadata.get('id', 'N/A')})]"
                elif msg_type == "photo":
                    content = f"[Hình ảnh đính kèm: {metadata.get('url', 'N/A')}]"
                elif msg_type == "file":
                    content = f"[Tập tin đính kèm: {metadata.get('title', 'N/A')}]"
                else:
                    content = f"[Tin nhắn đa phương tiện: {msg_type}]"
            else:
                content = "[Tin nhắn trống]"

        if self.message_callback:
            self.message_callback(mid, thread_id, author_id, sender_name, content, ts)

    def onException(self, exception):
        logger.error(f"Zalo Client Exception: {exception}")
        if self.error_callback:
            self.error_callback(str(exception))

class ZaloListenerThread(threading.Thread):
    def __init__(self, client, message_received_cb, connection_lost_cb):
        super().__init__()
        self.client = client
        self.message_received_cb = message_received_cb
        self.connection_lost_cb = connection_lost_cb
        self.running = False
        self.daemon = True
        
        if self.client:
            self.client.message_callback = self.on_message_received
            self.client.error_callback = self.on_error

    def on_message_received(self, mid, thread_id, sender_id, sender_name, content, ts):
        if self.message_received_cb:
            self.message_received_cb({
                "msg_id": mid,
                "group_id": thread_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "content": content,
                "timestamp": ts
            })

    def on_error(self, err_msg):
        if self.connection_lost_cb:
            self.connection_lost_cb(err_msg)

    def run(self):
        self.running = True
        logger.info("ZaloListenerThread bắt đầu lắng nghe...")
        try:
            if ZALO_AVAILABLE and self.client:
                self.client.listen()
            else:
                while self.running:
                    time.sleep(10)
        except Exception as e:
            logger.error(f"Lỗi trong ZaloListenerThread: {e}")
            if self.connection_lost_cb:
                self.connection_lost_cb(str(e))
        finally:
            self.running = False

    def stop(self):
        self.running = False
        if ZALO_AVAILABLE and self.client:
            try:
                self.client.listening = False
            except Exception:
                pass
        self.join(timeout=2.0)

class QrLoginThread(threading.Thread):
    def __init__(self, progress_cb, success_cb, error_cb):
        super().__init__()
        self.progress_cb = progress_cb
        self.success_cb = success_cb
        self.error_cb = error_cb
        self.daemon = True

    def run(self):
        try:
            self.progress_cb("Đang khởi động trình duyệt Chrome...")
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            options = Options()
            options.add_argument("--window-size=550,650")
            options.add_argument("--disable-gpu")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            driver = webdriver.Chrome(options=options)
            driver.get("https://chat.zalo.me")
            
            self.progress_cb("Trình duyệt đã mở. Vui lòng quét mã QR trên Zalo Web.")
            
            cookies = {}
            z_uuid = None
            user_agent = None
            success = False
            
            # Chờ người dùng quét mã tối đa 120s
            for _ in range(120):
                time.sleep(1)
                try:
                    current_cookies = driver.get_cookies()
                    cookie_dict = {c["name"]: c["value"] for c in current_cookies}
                    if "zpsid" in cookie_dict and "zpw_sek" in cookie_dict:
                        cookies = cookie_dict
                        
                        # Trích xuất z_uuid từ localStorage để đồng bộ IMEI thiết bị
                        try:
                            z_uuid = driver.execute_script("return window.localStorage.getItem('z_uuid');")
                        except Exception:
                            z_uuid = None
                        
                        if not z_uuid:
                            z_uuid = cookie_dict.get("zbrowser_id")
                            
                        # Trích xuất User-Agent thực tế của trình duyệt Chrome để khớp header
                        try:
                            user_agent = driver.execute_script("return navigator.userAgent;")
                        except Exception:
                            user_agent = None
                            
                        success = True
                        break
                except Exception:
                    break
            
            try:
                driver.quit()
            except Exception:
                pass
                
            if success:
                self.success_cb(cookies, z_uuid, user_agent)
            else:
                self.error_cb("Đăng nhập QR thất bại hoặc trình duyệt bị đóng.")
                
        except ImportError:
            self.error_cb("Chưa cài đặt thư viện 'selenium'. Vui lòng chạy: pip install selenium")
        except Exception as e:
            self.error_cb(f"Lỗi khởi động trình duyệt: {e}\n(Vui lòng đảm bảo Google Chrome đã được cài đặt)")

class ZaloService:
    def __init__(self):
        self.client = None
        self.listener_thread = None

    def login(self, phone, password, cookies, imei=None, user_agent=None):
        try:
            self.client = ZaloBot(phone, password, imei=imei, session_cookies=cookies, user_agent=user_agent)
            if ZALO_AVAILABLE and self.client:
                try:
                    uid_to_fetch = str(self.client.uid).split("_")[0] if self.client.uid else None
                    if uid_to_fetch and uid_to_fetch != "0":
                        self.client.fetchUserInfo(uid_to_fetch)
                except Exception as info_err:
                    logger.debug(f"Bỏ qua lỗi fetchUserInfo ban đầu: {info_err}")
                    
            save_session(phone, password, cookies, self.client.imei, user_agent)
            return True
        except Exception as e:
            logger.error(f"Đăng nhập Zalo thất bại: {e}")
            self.client = None
            return False

    def auto_login(self):
        session = load_session()
        if session:
            logger.info("Phát hiện phiên Zalo cũ, đang tự động kết nối...")
            return self.login(
                session["phone"],
                session["password"],
                session["cookies"],
                session["imei"],
                user_agent=session.get("user_agent")
            )
        return False

    def start_listening(self, callback_func, error_func):
        if not self.client:
            logger.warning("Không thể khởi chạy Listener do chưa đăng nhập.")
            return False
            
        self.listener_thread = ZaloListenerThread(self.client, callback_func, error_func)
        self.listener_thread.start()
        return True

    def stop_listening(self):
        if self.listener_thread:
            logger.info("Đang dừng Zalo Listener Thread...")
            self.listener_thread.stop()
            self.listener_thread = None

    def start_qr_login(self, progress_cb, success_cb, error_cb):
        thread = QrLoginThread(progress_cb, success_cb, error_cb)
        thread.start()
        return thread

    def _extract_name_from_dict(self, d):
        if not d or not isinstance(d, (dict, object)):
            return None
        if isinstance(d, dict):
            return d.get("gName") or d.get("name") or d.get("groupName")
        return getattr(d, "gName", None) or getattr(d, "name", None) or getattr(d, "groupName", None)

    def fetch_user_info(self, user_id):
        if not self.client or not ZALO_AVAILABLE:
            return None
        try:
            uid_clean = str(user_id).split("_")[0] if user_id else None
            if uid_clean and uid_clean != "0":
                return self.client.fetchUserInfo(uid_clean)
        except Exception as e:
            logger.error(f"Lỗi khi fetch_user_info cho User {user_id}: {e}")
        return None

    def fetch_group_info(self, group_id):
        if not self.client or not ZALO_AVAILABLE:
            return None
        try:
            gid_str = str(group_id)
            gname = None
            
            # 1. Gọi API fetchGroupInfo từ zlapi
            try:
                info = self.client.fetchGroupInfo(gid_str)
                if info:
                    # Trích xuất trực tiếp
                    gname = self._extract_name_from_dict(info)
                    
                    # Trích xuất từ các cấp lồng nhau: gridInfoMap, gridMap, groups
                    if not gname:
                        grid_map = None
                        if isinstance(info, dict):
                            grid_map = info.get("gridInfoMap") or info.get("gridMap") or info.get("groups")
                        else:
                            grid_map = getattr(info, "gridInfoMap", None) or getattr(info, "gridMap", None) or getattr(info, "groups", None)
                            
                        if grid_map:
                            sub_obj = None
                            if isinstance(grid_map, dict):
                                sub_obj = grid_map.get(gid_str) or grid_map.get(int(gid_str) if gid_str.isdigit() else gid_str)
                                if not sub_obj and len(grid_map) > 0:
                                    sub_obj = list(grid_map.values())[0]
                            elif isinstance(grid_map, list) and len(grid_map) > 0:
                                sub_obj = grid_map[0]
                            if sub_obj:
                                gname = self._extract_name_from_dict(sub_obj)
            except Exception as req_err:
                logger.debug(f"fetchGroupInfo API call lỗi: {req_err}")

            # 2. Tìm trong danh sách nhóm lấy từ fetch_all_groups() làm dự phòng
            if not gname:
                all_groups = self.fetch_all_groups()
                match = next((g for g in all_groups if str(g["id"]) == gid_str), None)
                if match and match.get("name") and not str(match["name"]).startswith("Nhóm "):
                    gname = match["name"]

            if gname:
                logger.info(f"fetch_group_info: Đã trích xuất thành công tên nhóm ID {gid_str} là '{gname}'")
                return {"id": gid_str, "name": str(gname)}
            else:
                logger.warning(f"fetch_group_info: Không thể trích xuất tên nhóm cho ID {gid_str}")
        except Exception as e:
            logger.error(f"Lỗi khi fetch_group_info cho nhóm {group_id}: {e}")
        return None

    def fetch_group_messages(self, group_id, count=100):
        # Trả về danh sách rỗng do thư viện zlapi hiện tại không hỗ trợ API fetchThreadMessages để lấy tin nhắn cũ
        return []

    def fetch_all_groups(self):
        if not self.client or not ZALO_AVAILABLE:
            return [
                {"id": "g1", "name": "Nhóm Hỗ Trợ Khách Hàng A"},
                {"id": "g2", "name": "Nhóm Chat VIP Dự Án B"},
                {"id": "g3", "name": "Cộng Đồng Sử Dụng Sản Phẩm X"}
            ]
            
        result = []
        existing_ids = set()
        group_ids = []

        try:
            # 1. Lấy danh sách thô tất cả Group ID từ fetchAllGroups (/getlg/v4)
            groups = self.client.fetchAllGroups()
            if isinstance(groups, dict):
                if "gridVerMap" in groups and isinstance(groups["gridVerMap"], dict):
                    group_ids = [str(k) for k in groups["gridVerMap"].keys()]
                elif "groups" in groups:
                    gdata = groups["groups"]
                    if isinstance(gdata, dict):
                        group_ids = [str(k) for k in gdata.keys()]
                    elif isinstance(gdata, list):
                        group_ids = [str(item.get("grid") or item.get("id")) for item in gdata if isinstance(item, dict)]
            elif isinstance(groups, list):
                for item in groups:
                    gid = item.get("grid") or item.get("id") if isinstance(item, dict) else str(item)
                    if gid:
                        group_ids.append(str(gid))

            # 2. Hợp nhất thêm các Group ID từ WebSocket live messages
            if hasattr(self.client, "known_live_groups"):
                for live_gid in getattr(self.client, "known_live_groups", set()):
                    if live_gid and str(live_gid) not in group_ids:
                        group_ids.append(str(live_gid))

            # 3. Batch query fetchGroupInfo (/getmg-v2) để lấy tên thật (gName) của tất cả các nhóm
            name_map = {}
            if group_ids:
                chunk_size = 50
                for i in range(0, len(group_ids), chunk_size):
                    chunk = group_ids[i:i + chunk_size]
                    chunk_dict = {str(gid): 0 for gid in chunk}
                    try:
                        info_res = self.client.fetchGroupInfo(chunk_dict)
                        if info_res:
                            grid_info = None
                            if isinstance(info_res, dict):
                                grid_info = info_res.get("gridInfoMap") or info_res.get("gridMap") or info_res.get("groups") or info_res
                            else:
                                grid_info = getattr(info_res, "gridInfoMap", None) or getattr(info_res, "gridMap", None) or getattr(info_res, "groups", None) or info_res
                                
                            if isinstance(grid_info, dict):
                                for gid_k, gdata in grid_info.items():
                                    gname = self._extract_name_from_dict(gdata)
                                    if gname:
                                        name_map[str(gid_k)] = str(gname)
                    except Exception as batch_err:
                        logger.error(f"Lỗi khi batch fetchGroupInfo cho đợt {i}: {batch_err}")

            # 4. Tạo danh sách kết quả cuối cùng chứa đầy đủ Tên Nhóm thật
            for gid in group_ids:
                if gid in existing_ids:
                    continue
                existing_ids.add(gid)
                real_name = name_map.get(gid) or f"Nhóm {gid}"
                result.append({"id": gid, "name": real_name})

            logger.info(f"fetch_all_groups: Tải thành công {len(result)} nhóm (Đã lấy được {len(name_map)} tên thật từ Zalo).")
            return result
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách nhóm Zalo: {e}")
            return []
