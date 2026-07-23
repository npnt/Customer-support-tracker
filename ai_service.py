import json
import time
import logging
import queue
import threading
import config

logger = logging.getLogger("ai")
err_logger = logging.getLogger("error")

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

class AIService:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        configured_model = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
        self.model_candidates = [
            configured_model,
            "gemini-1.5-flash-latest",
            "gemini-1.5-pro",
            "gemini-1.5-pro-latest",
            "gemini-2.0-flash-exp",
            "gemini-pro"
        ]
        # Xóa các phần tử trùng lặp mà vẫn giữ đúng thứ tự
        self.model_candidates = list(dict.fromkeys(self.model_candidates))
        self.current_model_index = 0
        self.model = None
        self.configured = False

        if GENAI_AVAILABLE and self.api_key and self.api_key not in ("YOUR_GEMINI_API_KEY_HERE", "your_actual_gemini_api_key_here"):
            try:
                genai.configure(api_key=self.api_key)
                self._init_current_model()
            except Exception as e:
                self.configured = False
                logger.error(f"Lỗi cấu hình Gemini API: {e}")
        else:
            self.configured = False
            logger.warning("Gemini API key chưa được thiết lập hoặc thiếu thư viện. Sử dụng bộ phân loại giả lập.")

    def _init_current_model(self):
        model_name = self.model_candidates[self.current_model_index]
        try:
            self.model = genai.GenerativeModel(model_name)
            self.model_name = model_name
            self.configured = True
            logger.info(f"Cấu hình Gemini API với model '{model_name}' thành công.")
        except Exception as e:
            logger.error(f"Khởi tạo model '{model_name}' thất bại: {e}")
            self.configured = False

    def classify_messages(self, messages, open_tickets):
        if not self.configured:
            time.sleep(0.5)
            return self._mock_classification(messages, open_tickets)

        prompt = self._build_prompt(messages, open_tickets)
        
        for attempt in range(len(self.model_candidates)):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                result_text = response.text.strip()
                logger.info(f"Yêu cầu AI thành công với model '{self.model_name}'. Phản hồi: {result_text}")
                return json.loads(result_text)
            except Exception as e:
                err_str = str(e)
                logger.error(f"Lỗi khi gửi yêu cầu tới Gemini API (model '{self.model_name}'): {err_str}")
                
                # Nếu gặp lỗi 404 Model not found, chuyển sang model dự phòng kế tiếp
                if "404" in err_str or "not found" in err_str.lower() or "not supported" in err_str.lower():
                    if self.current_model_index + 1 < len(self.model_candidates):
                        self.current_model_index += 1
                        next_model = self.model_candidates[self.current_model_index]
                        logger.warning(f"Model '{self.model_name}' bị lỗi 404. Đang tự động chuyển sang model dự phòng: '{next_model}'")
                        self._init_current_model()
                        if self.configured:
                            continue

                # Dự phòng cuối cùng: Dùng mock classification để tránh dừng chương trình
                break

        logger.warning("Tất cả các model Gemini API đều không khả dụng. Tự động chuyển sang fallback _mock_classification.")
        return self._mock_classification(messages, open_tickets)

    def _build_prompt(self, messages, open_tickets):
        messages_str = json.dumps(messages, ensure_ascii=False, indent=2)
        tickets_str = json.dumps(open_tickets, ensure_ascii=False, indent=2)
        
        prompt = f"""
Bạn là một trợ lý AI chăm sóc khách hàng hỗ trợ phân loại tin nhắn trong nhóm chat Zalo.
Dưới đây là danh sách các Ticket đang mở và danh sách tin nhắn mới cần phân loại.

### DANH SÁCH TICKET ĐANG MỞ (Open Tickets):
{tickets_str}

### DANH SÁCH TIN NHẮN MỚI CẦN PHÂN LOẠI:
{messages_str}

### NHIỆM VỤ:
1. Phân loại từng tin nhắn mới thành một trong bốn loại:
   - "REQUEST": Tin nhắn yêu cầu hỗ trợ mới từ khách hàng (hỏi giá, báo lỗi, hỏi đáp kỹ thuật...).
   - "RESPONSE": Tin nhắn phản hồi thông tin hoặc hỗ trợ xử lý của kỹ thuật viên/admin, hoặc tin nhắn làm rõ thêm của khách hàng cho ticket cũ.
   - "RESOLVE": Tin nhắn báo đã xử lý xong, thông báo khắc phục xong lỗi, hoặc tin nhắn cảm ơn/xác nhận đã hoàn thành từ khách hàng (ví dụ: "cảm ơn", "xử lý xong rồi", "đã ok", "đã sửa xong", "dạ cảm ơn anh", "ok rồi nhé"...).
   - "OTHER": Tin chào hỏi, xã giao, tin nhắn rác không thuộc diện cần xử lý.
2. Đối với tin "RESPONSE" hoặc "RESOLVE", hãy tìm kiếm xem nó liên quan/phản hồi tới Ticket nào trong "DANH SÁCH TICKET ĐANG MỞ". Trả về ID của Ticket đó vào trường `target_ticket_id`. Nếu không liên quan hoặc không tìm thấy, đặt là null.
3. Cung cấp chỉ số độ tin cậy `confidence` (từ 0.0 đến 1.0) cho phân loại này.

### ĐỊNH DẠNG TRẢ VỀ (JSON Array duy nhất, không có markdown block):
[
  {{
    "msg_id": "ID_tin_nhắn",
    "classification": "REQUEST" | "RESPONSE" | "RESOLVE" | "OTHER",
    "target_ticket_id": null | ID_của_ticket,
    "confidence": số_thực_từ_0_0_đến_1_0
  }}
]
"""
        return prompt

    def _mock_classification(self, messages, open_tickets):
        results = []
        for msg in messages:
            content = msg["content"].lower()
            sender = msg["sender_name"].lower()
            
            if any(k in content for k in ["cảm ơn", "cám ơn", "xử lý xong", "đã xong", "đã sửa", "đã được rồi", "được rồi", "ok rồi", "hoàn thành"]):
                classification = "RESOLVE"
                target_ticket_id = open_tickets[-1]["id"] if open_tickets else None
                confidence = 0.92
            elif any(k in content for k in ["lỗi", "giúp", "không chạy", "hỗ trợ", "báo giá", "không được", "sao thế"]):
                classification = "REQUEST"
                target_ticket_id = None
                confidence = 0.95
            elif any(k in content for k in ["ok", "kiểm tra", "đã reset"]):
                classification = "RESPONSE"
                target_ticket_id = open_tickets[-1]["id"] if open_tickets else None
                confidence = 0.88
            else:
                classification = "OTHER"
                target_ticket_id = None
                confidence = 0.98
                
            results.append({
                "msg_id": msg["msg_id"],
                "classification": classification,
                "target_ticket_id": target_ticket_id,
                "confidence": confidence
            })
        return results

class AIWorkerThread(threading.Thread):
    def __init__(self, ai_queue, callback_func):
        super().__init__()
        self.queue = ai_queue
        self.callback_func = callback_func
        self.ai_service = AIService()
        self.running = False
        self.daemon = True

    def run(self):
        self.running = True
        logger.info("AIWorkerThread đã khởi chạy.")
        
        while self.running:
            try:
                task = self.queue.get(timeout=1.0)
            except queue.Empty:
                continue

            messages = task.get("messages", [])
            open_tickets = task.get("open_tickets", [])
            
            if not messages:
                self.queue.task_done()
                continue
                
            logger.info(f"Đang xử lý phân loại AI cho lô {len(messages)} tin nhắn...")
            
            retries = 0
            success = False
            classified_results = []
            
            while retries < config.AI_MAX_RETRY and self.running:
                try:
                    classified_results = self.ai_service.classify_messages(messages, open_tickets)
                    success = True
                    break
                except Exception as e:
                    retries += 1
                    logger.warning(f"Lỗi AI phân tích (Lần {retries}/{config.AI_MAX_RETRY}): {e}")
                    if retries < config.AI_MAX_RETRY:
                        time.sleep(config.AI_RETRY_DELAY * (2 ** (retries - 1)))
            
            if success:
                logger.info("Phân loại AI hoàn tất.")
                if self.callback_func:
                    self.callback_func(classified_results)
            else:
                err_msg = f"Phân loại AI thất bại sau {config.AI_MAX_RETRY} lần thử cho {len(messages)} tin nhắn."
                logger.error(err_msg)
                err_logger.error(err_msg)
                
                failed_results = []
                for msg in messages:
                    failed_results.append({
                        "msg_id": msg["msg_id"],
                        "classification": "OTHER",
                        "target_ticket_id": None,
                        "confidence": 0.0,
                        "failed": True
                    })
                if self.callback_func:
                    self.callback_func(failed_results)
                
            self.queue.task_done()
            
        logger.info("AIWorkerThread đã dừng.")

    def stop(self):
        self.running = False
        self.join(timeout=2.0)
