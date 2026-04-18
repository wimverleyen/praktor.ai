"""
KafkaAuditSink — write audit entries as Avro messages to a Kafka topic.

Requires: pip install praktor[kafka]

Configuration via environment variables:
    PRAKTOR_AUDIT_KAFKA_TOPIC   — topic name (default: "praktor_audit")
    PRAKTOR_AUDIT_KAFKA_BROKERS — comma-separated broker list (default: "localhost:9092")

Retry behavior: 3 attempts with exponential backoff (1s, 2s, 4s).
On persistent failure: logs error, does NOT crash the agent.
The audit gap is visible in the application log.
"""
from __future__ import annotations

import json
import os

from settings import create_log

log = create_log()

_TOPIC = os.getenv("PRAKTOR_AUDIT_KAFKA_TOPIC", "praktor_audit")
_BROKERS = os.getenv("PRAKTOR_AUDIT_KAFKA_BROKERS", "localhost:9092")
_MAX_RETRIES = 3


class KafkaAuditSink:
    """
    Kafka audit sink. Sends one JSON message per AuditEntry.

    Lazy-initializes the aiokafka producer on first write.
    Cached at instance level (do not create per-write).
    """

    def __init__(
        self,
        topic: str = _TOPIC,
        brokers: str = _BROKERS,
    ) -> None:
        self._topic = topic
        self._brokers = brokers
        self._producer = None

    async def _get_producer(self):
        if self._producer is None:
            from aiokafka import AIOKafkaProducer
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._brokers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            log.info(f"KafkaAuditSink: connected to {self._brokers}, topic={self._topic}")
        return self._producer

    async def write(self, entry) -> None:
        """Write one audit entry to Kafka. Retries on transient failure."""
        import asyncio
        from dataclasses import asdict

        data = asdict(entry)
        last_exc = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                producer = await self._get_producer()
                await producer.send_and_wait(self._topic, value=data)
                log.debug(f"KafkaAuditSink: wrote entry {entry.entry_id}")
                return
            except Exception as e:
                last_exc = e
                wait = 2 ** (attempt - 1)
                log.warning(
                    f"KafkaAuditSink: attempt {attempt}/{_MAX_RETRIES} failed: {e}. "
                    f"Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)

        log.error(
            f"KafkaAuditSink: WRITE FAILED after {_MAX_RETRIES} attempts for "
            f"entry {entry.entry_id}: {last_exc}. Audit entry dropped."
        )

    async def close(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None
