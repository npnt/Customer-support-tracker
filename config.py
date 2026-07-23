import os
from dotenv import load_dotenv

# Load các biến môi trường từ file .env
load_dotenv()

# Đường dẫn cơ sở dữ liệu và thư mục backup
DB_PATH = "zalo_cs_tracker.db"
BACKUP_DIR = "backups"

# Cấu hình AI Gemini - Lấy thực sự từ .env và bắt buộc phải tồn tại
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY or GEMINI_API_KEY.strip() in ("", "YOUR_GEMINI_API_KEY_HERE", "your_actual_gemini_api_key_here"):
    raise ValueError(
        "\n========================================================================\n"
        "LỖI CẤU HÌNH: Không tìm thấy 'GEMINI_API_KEY' hợp lệ trong file .env!\n"
        "Vui lòng thực hiện:\n"
        "1. Đổi tên file '.env.example' thành '.env'.\n"
        "2. Điền khóa Gemini API thực của bạn vào dòng: GEMINI_API_KEY=key_cua_ban\n"
        "========================================================================"
    )

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
AI_CONFIDENCE_THRESHOLD = 0.70  # Ngưỡng tin cậy của AI (70%)

# Cấu hình SLA mặc định (phút)
DEFAULT_MAX_RESPONSE_TIME = 15
DEFAULT_MAX_RESOLVE_TIME = 60

# Cấu hình Hàng đợi & Tránh tràn bộ nhớ
AI_QUEUE_MAXSIZE = 200  # Kích thước hàng đợi tối đa trên RAM

# Cấu hình AI Retry & Timeout
AI_MAX_RETRY = 3
AI_RETRY_DELAY = 2  # giây
AI_TIMEOUT = 10     # giây

# Cấu hình file Log
LOG_DIR = "logs"
APP_LOG = os.path.join(LOG_DIR, "app.log")
AI_LOG = os.path.join(LOG_DIR, "ai.log")
ERROR_LOG = os.path.join(LOG_DIR, "error.log")
