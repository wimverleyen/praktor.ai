from dotenv import load_dotenv

import os
import uuid
import logging
from logging.handlers import RotatingFileHandler

load_dotenv()

#MODEL = 'llama3.1'
MODEL = 'qwen2.5'

MD = os.getenv('MD')
PDF = os.getenv('PDF')
VECTOR_DB = os.getenv('VECTOR_DB')

_LOG_FILE = 'praktor.ai.log'
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_BACKUP_COUNT = 5


def create_log(request_id: str | None = None) -> logging.Logger:
    """
    Return a logger backed by a rotating file handler.

    Pass a request_id to tag every log line with a correlation ID so that
    a single request can be traced end-to-end across agent → queue → method.
    """
    name = f'praktor.{request_id}' if request_id else 'praktor'
    log = logging.getLogger(name)

    if not log.handlers:
        handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
        )
        fmt = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        handler.setFormatter(logging.Formatter(fmt))
        log.addHandler(handler)
        log.setLevel(logging.DEBUG)

    return log


def new_request_id() -> str:
    """Generate a short correlation ID for a single agent request."""
    return uuid.uuid4().hex[:8]
