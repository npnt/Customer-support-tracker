#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ứng dụng thu thập dữ liệu thô từ Zalo (Zalo Raw Test Data Collector)
Sử dụng phiên Zalo hiện tại để trích xuất dữ liệu phản hồi thực tế (API & WebSocket)
Phục vụ công tác xây dựng Unit Test, Mock Data và Kiểm thử QA.
"""

import os
import sys
import json
import time
import argparse
import datetime
import logging

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ZaloDataCollector")

# Đường dẫn thư mục lưu trữ dữ liệu test
TEST_DATA_DIR = os.path.join("tests", "test_data")

def make_serializable(obj):
    """
    Chuyển đổi các đối tượng phức tạp từ zlapi (Munch, MessageObject, EventObject, v.v.)
    thành kiểu dữ liệu chuẩn của Python có thể serialize ra tệp JSON.
    """
    if obj is None:
        return None
    if isinstance(obj, (int, float, bool, str)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [make_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): make_serializable(v) for k, v in obj.items()}
    if hasattr(obj, "toDict") and callable(getattr(obj, "toDict")):
        try:
            return make_serializable(obj.toDict())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return make_serializable(vars(obj))
        except Exception:
            pass
    return str(obj)

def save_json_file(filename, data):
    """
    Lưu dữ liệu vào tệp JSON trong thư mục tests/test_data/
    """
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    filepath = os.path.join(TEST_DATA_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu tệp dữ liệu thô: {filepath}")
    return filepath

def collect_zalo_data(listen_duration=30):
    from zalo_service import ZaloBot, load_session, ZALO_AVAILABLE
    
    if not ZALO_AVAILABLE:
        logger.error("Thư viện 'zlapi' chưa được cài đặt. Không thể kết nối Zalo.")
        return

    session = load_session()
    if not session:
        logger.error("Không tìm thấy tệp session 'zalo_session.json'. Vui lòng chạy ứng dụng main.py và đăng nhập Zalo trước!")
        return

    logger.info("==================================================")
    logger.info("   ZALO RAW TEST DATA COLLECTOR (FOR UNITTEST & QA)")
    logger.info("==================================================")
    logger.info(f"Phát hiện phiên Zalo cho SĐT: {session.get('phone', 'N/A')}")
    
    phone = session.get("phone")
    password = session.get("password")
    cookies = session.get("cookies")
    imei = session.get("imei")
    user_agent = session.get("user_agent")

    logger.info("Đang khởi tạo ZaloBot client...")
    try:
        bot = ZaloBot(phone, password, imei=imei, session_cookies=cookies, user_agent=user_agent)
    except Exception as e:
        logger.error(f"Khởi tạo ZaloBot thất bại: {e}")
        return

    collected_manifest = {
        "collected_at": datetime.datetime.now().isoformat(),
        "phone": phone,
        "files": []
    }

    # ---------------------------------------------------------
    # 1. Thu thập danh sách tất cả các nhóm (All Groups Payload)
    # ---------------------------------------------------------
    logger.info("\n[1/4] Đang thu thập danh sách nhóm thô (All Groups)...")
    group_ids = []
    try:
        all_groups_raw = bot.fetchAllGroups()
        serializable_groups = make_serializable(all_groups_raw)
        fpath = save_json_file("raw_groups_list.json", serializable_groups)
        collected_manifest["files"].append({"type": "groups_list", "file": fpath})

        # Trích xuất đúng các Group ID thực tế từ gridVerMap
        if isinstance(all_groups_raw, dict):
            if "gridVerMap" in all_groups_raw and isinstance(all_groups_raw["gridVerMap"], dict):
                group_ids = [str(k) for k in all_groups_raw["gridVerMap"].keys()]
            elif "groups" in all_groups_raw:
                gdata = all_groups_raw["groups"]
                if isinstance(gdata, dict):
                    group_ids = [str(k) for k in gdata.keys()]
                elif isinstance(gdata, list):
                    group_ids = [str(item.get("grid") or item.get("id")) for item in gdata if isinstance(item, dict)]
        logger.info(f" -> Phát hiện tổng cộng {len(group_ids)} Group ID thực tế từ Zalo.")
    except Exception as e:
        logger.error(f"Lỗi khi thu thập groups list: {e}")

    # ---------------------------------------------------------
    # 2. Thu thập chi tiết thông tin từng nhóm (Group Info Payload)
    # ---------------------------------------------------------
    logger.info("\n[2/4] Đang thu thập chi tiết nhóm (Group Details)...")
    group_details = {}
    valid_user_ids = []
    for gid in group_ids[:5]: # Thu thập tối đa 5 nhóm mẫu
        try:
            logger.info(f" -> Lấy thông tin chi tiết nhóm ID: {gid}")
            ginfo = bot.fetchGroupInfo(str(gid))
            group_details[str(gid)] = make_serializable(ginfo)

            # Thu thập thử một số User ID từ thành viên nhóm để làm mẫu cho fetchUserInfo
            if ginfo and isinstance(ginfo, dict):
                mems = ginfo.get("memApprove") or ginfo.get("members") or []
                if isinstance(mems, list):
                    for m in mems:
                        uid = m.get("id") or m.get("userId") or m if isinstance(m, (str, int)) else None
                        if uid and str(uid) not in valid_user_ids:
                            valid_user_ids.append(str(uid))
        except Exception as e:
            logger.error(f" -> Lỗi khi lấy thông tin nhóm {gid}: {e}")
            
    if group_details:
        fpath = save_json_file("raw_groups_detail.json", group_details)
        collected_manifest["files"].append({"type": "groups_detail", "file": fpath})

    # ---------------------------------------------------------
    # 3. Thu thập thông tin Tài khoản người dùng (User Profile)
    # ---------------------------------------------------------
    logger.info("\n[3/4] Đang thu thập thông tin tài khoản (Profile User)...")
    try:
        target_uid = bot.uid if bot.uid and str(bot.uid) != "0" else (valid_user_ids[0] if valid_user_ids else "1909893267130386493")
        target_uid = str(target_uid).split("_")[0]
        logger.info(f" -> Lấy thông tin User Profile cho UID: {target_uid}")
        user_info = bot.fetchUserInfo(target_uid)
        serializable_user_info = make_serializable(user_info)
        fpath = save_json_file("raw_user_info.json", serializable_user_info)
        collected_manifest["files"].append({"type": "user_info", "file": fpath})
    except Exception as e:
        logger.error(f"Lỗi khi thu thập user info: {e}")

    # ---------------------------------------------------------
    # 4. Thu thập tin nhắn Live WebSocket (Live Message Payloads)
    # ---------------------------------------------------------
    logger.info(f"\n[4/4] Bắt đầu lắng nghe tin nhắn Live trong {listen_duration} giây...")
    logger.info("   (Vui lòng gửi tin nhắn thử nghiệm vào Zalo để ghi nhận dữ liệu live thô)")

    captured_messages = []

    # Ghi đè handler onMessage để thu thập dữ liệu thô
    def custom_on_message(mid, author_id, message, message_object, thread_id, thread_type, ts=None, metadata=None, msg=None, **kwargs):
        payload_sample = {
            "index": len(captured_messages) + 1,
            "recorded_at": datetime.datetime.now().isoformat(),
            "mid": mid,
            "author_id": author_id,
            "message_content": message,
            "thread_id": thread_id,
            "thread_type": str(thread_type),
            "ts": ts,
            "metadata": make_serializable(metadata),
            "message_object": make_serializable(message_object),
            "extra_kwargs": make_serializable(kwargs)
        }
        captured_messages.append(payload_sample)
        logger.info(f"   [+] Bắt 1 tin nhắn WebSocket: Thread={thread_id} | Người gửi={author_id} | Content='{message}'")

    bot.onMessage = custom_on_message

    import threading
    listen_thread = threading.Thread(target=bot.listen, daemon=True)
    listen_thread.start()

    # Chờ thu thập trong khoảng thời gian quy định
    start_t = time.time()
    try:
        while time.time() - start_t < listen_duration:
            time.sleep(1)
            remaining = int(listen_duration - (time.time() - start_t))
            if remaining % 10 == 0 and remaining > 0:
                logger.info(f"   ...Còn lại {remaining}s lắng nghe tin nhắn...")
    except KeyboardInterrupt:
        logger.info("Người dùng tạm dừng quá trình lắng nghe sớm.")

    bot.listening = False
    
    # Lưu danh sách tin nhắn live
    fpath = save_json_file("raw_live_messages.json", captured_messages)
    collected_manifest["files"].append({
        "type": "live_messages", 
        "count": len(captured_messages), 
        "file": fpath
    })

    # Save manifest
    save_json_file("manifest.json", collected_manifest)

    logger.info("\n==================================================")
    logger.info("   HOÀN THÀNH THU THẬP DỮ LIỆU TEST")
    logger.info("==================================================")
    logger.info(f"Tất cả tệp dữ liệu mẫu đã được lưu vào thư mục: {os.path.abspath(TEST_DATA_DIR)}")
    logger.info(f"- Số tin nhắn Live bắt được: {len(captured_messages)}")
    logger.info(f"- Tệp tổng hợp manifest: {os.path.abspath(os.path.join(TEST_DATA_DIR, 'manifest.json'))}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zalo Raw Test Data Collector")
    parser.add_argument("--listen-time", type=int, default=30, help="Thời gian (giây) lắng nghe tin nhắn live (Mặc định: 30s)")
    args = parser.parse_args()

    collect_zalo_data(listen_duration=args.listen_time)
