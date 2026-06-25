import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_FILE = Path(__file__).resolve().parent / "app.log"
LOG_MAX_MESSAGE_LENGTH = 200
ERROR_CODES = {
    'VALIDATION_ERROR': 'VALIDATION_ERROR',
    'DISPATCH_SERVICE_FAILURE': 'DISPATCH_SERVICE_FAILURE',
    'LINE_REGISTER_FAILURE': 'LINE_REGISTER_FAILURE',
    'AI_CONNECTIVITY_WARNING': 'AI_CONNECTIVITY_WARNING',
    'UNKNOWN_ERROR': 'UNKNOWN_ERROR',
}

formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")


def truncate_message(message: str, max_chars: int = LOG_MAX_MESSAGE_LENGTH) -> str:
    if message is None:
        return ''
    text = str(message)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + '...'


def build_error_payload(code: str, message: str) -> dict:
    return {
        'code': code,
        'message': truncate_message(message)
    }


def setup_logger() -> logging.Logger:
    logger = logging.getLogger('disaster_dispatcher')
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()
