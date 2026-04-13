"""
Transport protocol and built-in adapters.

Transport abstracts the message queue so praktor works with RabbitMQ,
HTTP, Kafka, or no transport at all (DirectTransport for dev/tests).

All adapters implement the Transport protocol. The consumer and producer
use Transport — they never import aio-pika directly.

Data flow:
    Producer ──publish()──► Queue/Channel ──consume()──► Consumer
                                                              │
                                                         ack()/nack()
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import AsyncGenerator, Protocol, runtime_checkable


@dataclass
class TransportMessage:
    """
    A message received from the transport layer.

    message_id: opaque string for ack/nack correlation
    body:       raw JSON bytes — passed to Router.dispatch(body)
    """
    message_id: str
    body: bytes


@runtime_checkable
class Transport(Protocol):
    async def publish(self, message: bytes, routing_key: str) -> None:
        """Publish a message. Raises TransportError on failure."""
        ...

    async def consume(self, routing_key: str) -> AsyncGenerator[TransportMessage, None]:
        """Yield TransportMessage objects. Caller acks/nacks via message_id."""
        ...

    async def ack(self, message_id: str) -> None:
        """Acknowledge successful processing."""
        ...

    async def nack(self, message_id: str) -> None:
        """Nack a message (requeue / dead-letter depending on queue config)."""
        ...

    async def close(self) -> None:
        """Clean shutdown. Drain in-flight messages before returning."""
        ...


class TransportError(Exception):
    """Raised when a transport operation fails."""


class DirectTransport:
    """
    In-process transport — no external dependencies.

    publish() places messages in an asyncio.Queue.
    consume() yields them. ack/nack are no-ops.

    Use for:
    - Local development (no Docker required)
    - Unit tests (no mocking needed)
    - Embedded deployments

    NOT suitable for multi-process deployments — messages are in-memory only.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[TransportMessage]] = {}

    def _get_queue(self, routing_key: str) -> asyncio.Queue[TransportMessage]:
        if routing_key not in self._queues:
            self._queues[routing_key] = asyncio.Queue()
        return self._queues[routing_key]

    async def publish(self, message: bytes, routing_key: str) -> None:
        msg = TransportMessage(message_id=uuid.uuid4().hex, body=message)
        await self._get_queue(routing_key).put(msg)

    async def consume(self, routing_key: str) -> AsyncGenerator[TransportMessage, None]:
        queue = self._get_queue(routing_key)
        while True:
            msg = await queue.get()
            yield msg

    async def ack(self, message_id: str) -> None:
        pass  # No-op for in-process transport

    async def nack(self, message_id: str) -> None:
        pass  # No-op — message already consumed from queue

    async def close(self) -> None:
        self._queues.clear()
