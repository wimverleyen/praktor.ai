"""
Tests for enterprise audit sinks: KafkaAuditSink and MinIOAuditSink.

All tests mock external dependencies (aiokafka, minio). No live services needed.
"""
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

import sys
import os

from praktor.governance.audit import AuditEntry


# ---------------------------------------------------------------------------
# KafkaAuditSink
# ---------------------------------------------------------------------------

class TestKafkaAuditSink:
    """Tests for KafkaAuditSink with mocked aiokafka producer."""

    @pytest.fixture
    def mock_producer(self):
        producer = AsyncMock()
        producer.start = AsyncMock()
        producer.send_and_wait = AsyncMock()
        producer.stop = AsyncMock()
        return producer

    @pytest.fixture
    def entry(self):
        return AuditEntry(
            entry_id="test-kafka-001",
            agent_type="test_agent",
            session_id="sess-001",
            prompt_hash=AuditEntry.hash_text("hello"),
            response_hash=AuditEntry.hash_text("world"),
        )

    @pytest.mark.asyncio
    async def test_write_sends_to_kafka(self, mock_producer, entry):
        """Successful write sends serialized entry to the configured topic."""
        from praktor.governance.audit_kafka import KafkaAuditSink

        sink = KafkaAuditSink(topic="test-topic", brokers="localhost:9092")
        # Inject the mock producer directly
        sink._producer = mock_producer

        await sink.write(entry)

        mock_producer.send_and_wait.assert_called_once()
        call_args = mock_producer.send_and_wait.call_args
        assert call_args[0][0] == "test-topic"  # topic
        assert call_args[1]["value"]["entry_id"] == "test-kafka-001"

    @pytest.mark.asyncio
    async def test_write_retries_on_failure(self, mock_producer, entry):
        """Transient failures trigger retries with backoff."""
        from praktor.governance.audit_kafka import KafkaAuditSink

        sink = KafkaAuditSink(topic="test-topic", brokers="localhost:9092")
        sink._producer = mock_producer

        # Fail twice, succeed on third attempt
        mock_producer.send_and_wait.side_effect = [
            ConnectionError("broker down"),
            ConnectionError("broker down"),
            None,  # success
        ]

        await sink.write(entry)
        assert mock_producer.send_and_wait.call_count == 3

    @pytest.mark.asyncio
    async def test_write_logs_error_after_max_retries(self, mock_producer, entry):
        """After max retries, logs error but does not crash."""
        from praktor.governance.audit_kafka import KafkaAuditSink

        sink = KafkaAuditSink(topic="test-topic", brokers="localhost:9092")
        sink._producer = mock_producer

        # Fail on all attempts
        mock_producer.send_and_wait.side_effect = ConnectionError("permanent failure")

        # Should not raise — just log and drop
        await sink.write(entry)
        assert mock_producer.send_and_wait.call_count == 3

    @pytest.mark.asyncio
    async def test_close_stops_producer(self, mock_producer):
        """close() stops the producer cleanly."""
        from praktor.governance.audit_kafka import KafkaAuditSink

        sink = KafkaAuditSink()
        sink._producer = mock_producer

        await sink.close()
        mock_producer.stop.assert_called_once()
        assert sink._producer is None


# ---------------------------------------------------------------------------
# MinIOAuditSink
# ---------------------------------------------------------------------------

class TestMinIOAuditSink:
    """Tests for MinIOAuditSink with mocked minio client."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.bucket_exists.return_value = True
        client.put_object.return_value = None
        return client

    @pytest.fixture
    def entry(self):
        return AuditEntry(
            entry_id="test-minio-001",
            agent_type="healthcare_agent",
            session_id="sess-002",
            prompt_hash=AuditEntry.hash_text("patient data"),
            response_hash=AuditEntry.hash_text("redacted response"),
        )

    @pytest.mark.asyncio
    async def test_write_puts_object_to_minio(self, mock_client, entry):
        """Successful write stores JSON object with correct key schema."""
        from praktor.governance.audit_minio import MinIOAuditSink

        sink = MinIOAuditSink(bucket="test-bucket")
        sink._client = mock_client
        sink._bucket_verified = True  # skip bucket check

        await sink.write(entry)

        mock_client.put_object.assert_called_once()
        call_args = mock_client.put_object.call_args
        assert call_args[0][0] == "test-bucket"
        object_name = call_args[0][1]
        # Key schema: {agent_type}/{YYYY-MM-DD}/{entry_id}.json
        assert object_name.startswith("healthcare_agent/")
        assert object_name.endswith("/test-minio-001.json")

    @pytest.mark.asyncio
    async def test_auto_creates_bucket(self, mock_client, entry):
        """Auto-creates bucket if it does not exist."""
        from praktor.governance.audit_minio import MinIOAuditSink

        mock_client.bucket_exists.return_value = False

        sink = MinIOAuditSink(bucket="new-bucket")
        sink._client = mock_client

        await sink.write(entry)

        mock_client.bucket_exists.assert_called_with("new-bucket")
        mock_client.make_bucket.assert_called_once_with("new-bucket")

    @pytest.mark.asyncio
    async def test_write_failure_does_not_crash(self, mock_client, entry):
        """Write failure logs error but does not raise."""
        from praktor.governance.audit_minio import MinIOAuditSink

        mock_client.put_object.side_effect = Exception("disk full")

        sink = MinIOAuditSink(bucket="test-bucket")
        sink._client = mock_client
        sink._bucket_verified = True

        # Should not raise
        await sink.write(entry)

    @pytest.mark.asyncio
    async def test_bucket_check_cached_after_first_write(self, mock_client, entry):
        """Bucket existence check only runs once, then cached."""
        from praktor.governance.audit_minio import MinIOAuditSink

        sink = MinIOAuditSink(bucket="test-bucket")
        sink._client = mock_client

        await sink.write(entry)
        await sink.write(entry)

        # bucket_exists called once (cached after first check)
        assert mock_client.bucket_exists.call_count == 1
