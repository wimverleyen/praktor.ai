from __future__ import annotations
"""
Async RabbitMQ producer.

Usage:
    from praktor.transport.producer import publish

    await publish({"agent_type": "thank_you", "adjective": "professional", ...})
"""

import aio_pika
from json import dumps

from praktor.settings import RABBITMQ_URL, new_request_id, create_log

log = create_log()

_QUEUE = "agentic"


async def publish(data: dict, session_id: str | None = None) -> str:
    """
    Publish a single message to the agentic queue.

    Injects agent_type (required) and session_id (auto-generated if absent).
    Returns the session_id for correlation.
    """
    if "agent_type" not in data:
        raise ValueError("data must include 'agent_type'")

    sid = session_id or data.get("session_id") or new_request_id()
    data = {**data, "session_id": sid}

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(_QUEUE, durable=False)
        await channel.default_exchange.publish(
            aio_pika.Message(body=dumps(data).encode()),
            routing_key=_QUEUE,
        )
        log.debug(f"Published agent_type='{data['agent_type']}' session={sid}")

    return sid


async def publish_many(messages: list[dict]) -> list[str]:
    """Publish multiple messages over a single connection."""
    if not messages:
        return []

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    session_ids: list[str] = []

    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(_QUEUE, durable=False)

        for data in messages:
            if "agent_type" not in data:
                raise ValueError(f"Message missing agent_type: {data}")
            sid = data.get("session_id") or new_request_id()
            payload = {**data, "session_id": sid}
            await channel.default_exchange.publish(
                aio_pika.Message(body=dumps(payload).encode()),
                routing_key=_QUEUE,
            )
            session_ids.append(sid)
            log.debug(f"Published agent_type='{data['agent_type']}' session={sid}")

    return session_ids
