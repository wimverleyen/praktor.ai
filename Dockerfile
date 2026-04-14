# ============================================================================
# praktor.ai — Local-first agentic framework with governance
#
# Multi-stage build: slim runtime image, uv for fast dependency management.
#
# Build:
#   docker build -t praktor .
#   docker build -t praktor --build-arg EXTRAS="kafka,minio" .
#
# Run (connects to host Ollama):
#   docker run --rm -it --network host praktor receive
#   docker run --rm -it --network host praktor publish --agent thank_you \
#     --data '{"adjective":"warm","position":"CTO","content":"Great chat"}'
#
# Run with docker-compose (recommended):
#   docker compose up
# ============================================================================

# ---------- Stage 1: build dependencies ----------
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Build arg: comma-separated extras (e.g. "kafka,minio,presidio")
ARG EXTRAS=""

WORKDIR /app

# Copy dependency metadata first (cache-friendly layer)
COPY pyproject.toml .
COPY README.md .
COPY praktor/ praktor/

# Install project with uv into a virtual environment
RUN uv venv /app/.venv \
    && if [ -n "$EXTRAS" ]; then \
         uv pip install --python /app/.venv/bin/python -e ".[$EXTRAS]"; \
       else \
         uv pip install --python /app/.venv/bin/python -e .; \
       fi

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

# Labels
LABEL org.opencontainers.image.title="praktor.ai" \
      org.opencontainers.image.description="Local-first agentic framework with governance" \
      org.opencontainers.image.version="0.3.0" \
      org.opencontainers.image.source="https://github.com/wimverleyen/praktor.ai"

# Non-root user for security
RUN groupadd --gid 1000 praktor \
    && useradd --uid 1000 --gid praktor --create-home praktor

WORKDIR /app

# Copy the venv and source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/praktor /app/praktor
COPY --from=builder /app/pyproject.toml /app/

# Copy .env.example as reference
COPY .env.example .env.example

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/praktor" \
    PYTHONUNBUFFERED=1 \
    # Default config — override at runtime
    PRAKTOR_MODEL="qwen2.5" \
    PRAKTOR_CONCURRENCY="4" \
    CACHE_DIR="/tmp/praktor_cache" \
    CACHE_TTL="3600"

# Audit log volume (persist across restarts)
VOLUME ["/app/audit"]
ENV PRAKTOR_AUDIT_LOG="/app/audit/praktor_audit.jsonl"

# Switch to non-root
USER praktor

# Health check: import praktor without error
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import praktor" || exit 1

# Default: start the async consumer
ENTRYPOINT ["python", "-m", "praktor"]
CMD ["receive"]
