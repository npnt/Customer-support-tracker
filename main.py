import sys
import logging
from ui.main_window import MainWindow

logger = logging.getLogger("app")

def main():
    logger.info("Khởi động ứng dụng Zalo Customer Support Tracker (Tkinter Edition)...")
    
    # Khởi tạo cửa sổ chính và chạy vòng lặp sự kiện của Tkinter
    app = MainWindow()
    app.mainloop()

if __name__ == "__main__":
    main()
