"""
MinIOAuditSink — write audit entries as JSON objects to MinIO/S3.

Requires: pip install praktor[minio]

Configuration via environment variables:
    PRAKTOR_AUDIT_MINIO_ENDPOINT — MinIO endpoint (default: "localhost:9000")
    PRAKTOR_AUDIT_MINIO_BUCKET   — bucket name (default: "praktor-audit")
    PRAKTOR_AUDIT_MINIO_ACCESS_KEY — access key
    PRAKTOR_AUDIT_MINIO_SECRET_KEY — secret key
    PRAKTOR_AUDIT_MINIO_SECURE    — use HTTPS (default: "false")

Object key schema: {bucket}/{agent_type}/{YYYY-MM-DD}/{entry_id}.json
Auto-creates the bucket on first write if it does not exist.
"""
from __future__ import annotations

import json
import os
import time

from praktor.settings import create_log

log = create_log()

_ENDPOINT = os.getenv("PRAKTOR_AUDIT_MINIO_ENDPOINT", "localhost:9000")
_BUCKET = os.getenv("PRAKTOR_AUDIT_MINIO_BUCKET", "praktor-audit")
_ACCESS_KEY = os.getenv("PRAKTOR_AUDIT_MINIO_ACCESS_KEY", "")
_SECRET_KEY = os.getenv("PRAKTOR_AUDIT_MINIO_SECRET_KEY", "")
_SECURE = os.getenv("PRAKTOR_AUDIT_MINIO_SECURE", "false").lower() == "true"


class MinIOAuditSink:
    """
    MinIO/S3 audit sink. Writes one JSON object per AuditEntry.

    Lazy-initializes the Minio client on first write.
    Auto-creates the bucket if it does not exist.
    """

    def __init__(
        self,
        endpoint: str = _ENDPOINT,
        bucket: str = _BUCKET,
        access_key: str = _ACCESS_KEY,
        secret_key: str = _SECRET_KEY,
        secure: bool = _SECURE,
    ) -> None:
        self._endpoint = endpoint
        self._bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._secure = secure
        self._client = None
        self._bucket_verified = False

    def _get_client(self):
        if self._client is None:
            from minio import Minio
            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
            log.info(f"MinIOAuditSink: connected to {self._endpoint}")
        return self._client

    def _ensure_bucket(self, client) -> None:
        """Auto-create the bucket if it does not exist."""
        if self._bucket_verified:
            return
        if not client.bucket_exists(self._bucket):
            client.make_bucket(self._bucket)
            log.info(f"MinIOAuditSink: created bucket '{self._bucket}'")
        self._bucket_verified = True

    async def write(self, entry) -> None:
        """Write one audit entry as a JSON object to MinIO."""
        import asyncio
        import io
        from dataclasses import asdict

        try:
            client = self._get_client()
            await asyncio.to_thread(self._ensure_bucket, client)

            data = json.dumps(asdict(entry), sort_keys=True).encode("utf-8")
            date_prefix = time.strftime("%Y-%m-%d", time.gmtime())
            object_name = f"{entry.agent_type}/{date_prefix}/{entry.entry_id}.json"

            await asyncio.to_thread(
                client.put_object,
                self._bucket,
                object_name,
                io.BytesIO(data),
                len(data),
                content_type="application/json",
            )
            log.debug(f"MinIOAuditSink: wrote {self._bucket}/{object_name}")

        except Exception as e:
            log.error(
                f"MinIOAuditSink: WRITE FAILED for entry {entry.entry_id}: {e}. "
                "Audit entry dropped.",
                exc_info=True,
            )
