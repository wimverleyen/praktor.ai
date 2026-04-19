from __future__ import annotations

from dotenv import load_dotenv

import os
import uuid
import logging
from logging.handlers import RotatingFileHandler

load_dotenv()

# --- Model ---
MODEL = os.getenv('PRAKTOR_MODEL', 'qwen2.5')

# --- File paths ---
MD = os.getenv('MD')
PDF = os.getenv('PDF')
VECTOR_DB = os.getenv('VECTOR_DB')

# --- Queue ---
RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost/')
CONCURRENCY = int(os.getenv('PRAKTOR_CONCURRENCY', '4'))

# --- Judge evaluation ---
PRAKTOR_JUDGE_CONCURRENCY = int(os.getenv('PRAKTOR_JUDGE_CONCURRENCY', '3'))

# --- Cache ---
CACHE_DIR = os.getenv('CACHE_DIR', '/tmp/praktor_cache')
CACHE_TTL = int(os.getenv('CACHE_TTL', '3600'))

# --- LLM backend ---
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')

# --- Observability ---
# PRAKTOR_OTEL_ENABLED=1       — activate OTel export (default: off)
# PRAKTOR_OTLP_ENDPOINT        — OTLP gRPC collector (default: http://localhost:4317)
# PRAKTOR_OTEL_BACKEND=phoenix — bootstrap arize-phoenix-otel if installed
# OTEL_SDK_DISABLED=true       — disable all OTel (test runner safe)
PRAKTOR_OTEL_ENABLED   = os.getenv('PRAKTOR_OTEL_ENABLED', '').lower() in ('1', 'true', 'yes')
PRAKTOR_OTLP_ENDPOINT  = os.getenv('PRAKTOR_OTLP_ENDPOINT', os.getenv('OTLP_ENDPOINT', ''))
PRAKTOR_OTEL_BACKEND   = os.getenv('PRAKTOR_OTEL_BACKEND', '')
# Legacy alias — keep until all docs are updated
OTLP_ENDPOINT = PRAKTOR_OTLP_ENDPOINT

# --- Governance / RBAC ---
PRAKTOR_RBAC_SECRET = os.getenv('PRAKTOR_RBAC_SECRET')  # None = RBAC disabled globally
PRAKTOR_AUDIT_LOG = os.getenv('PRAKTOR_AUDIT_LOG', 'praktor_audit.jsonl')
PRAKTOR_AUDIT_MAX_BYTES = int(os.getenv('PRAKTOR_AUDIT_MAX_BYTES', str(100 * 1024 * 1024)))

# --- Logging ---
_LOG_FILE = os.getenv('PRAKTOR_LOG_FILE', 'praktor.ai.log')
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5


def create_log(request_id: str | None = None) -> logging.Logger:
    """
    Return a logger backed by a rotating file handler.
    Pass request_id to correlate a single request end-to-end.
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
