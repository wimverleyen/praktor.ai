"""
Test suite configuration.

Sets OTEL_SDK_DISABLED=true before any test module imports opentelemetry.
Without this, the ConsoleSpanExporter (initialized at module load in
observability.py) holds a reference to stdout that gets closed after the
first test, causing "I/O operation on closed file" errors in subsequent
tests when BatchSpanProcessor tries to flush.
"""
import os

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
