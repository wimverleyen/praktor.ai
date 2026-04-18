"""
RabbitMQ transport adapter using aio-pika.

Wraps the existing aio-pika consumer/producer pattern into the Transport protocol.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import aio_pika
from aio_pika import IncomingMessage

from transport.transport import Transport, TransportMessage, TransportError
from settings import create_log

log = create_log()


class RabbitMQTransport:
    """
    RabbitMQ transport via aio-pika.

    Supports prefetch-based concurrency (set concurrency= at construction).
    ack/nack are forwarded to aio-pika's message acknowledgement.
    """

    def __init__(self, url: str, concurrency: int = 4) -> None:
        self._url = url
        self._concurrency = concurrency
        self._connection = None
        self._pending: dict[str, IncomingMessage] = {}

    async def publish(self, message: bytes, routing_key: str) -> None:
        try:
            conn = await aio_pika.connect_robust(self._url)
            async with conn:
                channel = await conn.channel()
                await channel.declare_queue(routing_key, durable=False)
                await channel.default_exchange.publish(
                    aio_pika.Message(body=message),
                    routing_key=routing_key,
                )
        except Exception as e:
            raise TransportError(f"RabbitMQ publish failed: {e}") from e

    async def consume(self, routing_key: str) -> AsyncGenerator[TransportMessage, None]:
        conn = await aio_pika.connect_robust(self._url)
        self._connection = conn
        async with conn:
            channel = await conn.channel()
            await channel.set_qos(prefetch_count=self._concurrency)
            queue = await channel.declare_queue(routing_key, durable=False)
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    msg_id = uuid.uuid4().hex
                    self._pending[msg_id] = message
                    yield TransportMessage(message_id=msg_id, body=message.body)

    async def ack(self, message_id: str) -> None:
        msg = self._pending.pop(message_id, None)
        if msg:
            await msg.ack()

    async def nack(self, message_id: str) -> None:
        msg = self._pending.pop(message_id, None)
        if msg:
            await msg.nack(requeue=False)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
