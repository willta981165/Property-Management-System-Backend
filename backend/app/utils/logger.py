# Facts (GateGuard):
# 1. Imported by: app/__init__.py, app/routes/auth.py, admin.py,
#    admin_facility.py, admin_booking.py, resident_booking.py
# 2. No existing logger module found (confirmed: zero logging imports in codebase)
# 3. Writes to logs/logging.txt — format: YYYY-MM-DD HH:MM:SS - civic_app - LEVEL - message
#    Rotates at midnight to logs/loggingMMDD.txt (e.g. logging0719.txt). No production data.
# 4. User: "建立log機制...在本地產一個資料夾放logging.txt...每天晚上12點把當天資料撥離成logging0719.txt"
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# logs/ 放在 backend/ 根目錄（Docker 內為 /app/logs/）
LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
)
LOG_FILE = os.path.join(LOG_DIR, 'logging.txt')


def _namer(default_name: str) -> str:
    """
    將預設的 logging.txt.2026-07-19 改名為 logging0719.txt
    於每天 00:00 rotate 時觸發
    """
    base_dir = os.path.dirname(default_name)
    date_suffix = default_name.rsplit('.', 1)[-1]
    try:
        mmdd = datetime.strptime(date_suffix, '%Y-%m-%d').strftime('%m%d')
    except ValueError:
        mmdd = date_suffix
    return os.path.join(base_dir, f'logging{mmdd}.txt')


def _build_logger() -> logging.Logger:
    logger = logging.getLogger('civic_app')
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    handler = TimedRotatingFileHandler(
        filename=LOG_FILE,
        when='midnight',
        backupCount=90,
        encoding='utf-8',
    )
    handler.namer = _namer
    handler.setFormatter(logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))
    logger.addHandler(handler)
    return logger


app_logger = _build_logger()
