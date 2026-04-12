"""
Async RabbitMQ consumer using aio-pika.

Key improvements over the legacy receive.py:
- Non-blocking: processes CONCURRENCY messages simultaneously
- Streaming: forwards token chunks to stdout as they arrive
- Error isolation: a failing message is nack'd without affecting others
- Dynamic routing: no hardcoded dispatch — all routing lives in the Router
"""

import asyncio
import sys
from typing import AsyncGenerator

import aio_pika
from aio_pika import IncomingMessage

from core.router import Router
from settings import RABBITMQ_URL, CONCURRENCY, create_log

log = create_log()


async def _handle_message(message: IncomingMessage, router: Router) -> None:
    """Process a single queue message. Ack on success, nack on failure."""
    async with message.process(requeue_on_error=False, ignore_processed=True):
        try:
            chunks: list[str] = []
            async for chunk in router.dispatch(message.body):
                chunks.append(chunk)
                sys.stdout.write(chunk)
                sys.stdout.flush()

            if chunks:
                sys.stdout.write("\n")
                sys.stdout.flush()

            log.info(
                f"Message processed: {len(''.join(chunks))} chars"
            )

        except ValueError as e:
            # Schema / routing errors — don't retry
            log.error(f"Message rejected (bad payload): {e}")
            raise

        except Exception as e:
            # LLM errors — already retried by AsyncLLMAdapter; nack here
            log.error(f"Message failed: {e}", exc_info=True)
            raise


async def run_consumer(router: Router) -> None:
    """
    Start the aio-pika consumer loop.

    Processes up to CONCURRENCY messages concurrently.
    Each message is an independent asyncio.Task — a slow LLM call
    on one message does not block others.
    """
    log.info(f"Connecting to RabbitMQ at {RABBITMQ_URL}")
    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=CONCURRENCY)
        queue = await channel.declare_queue("agentic", durable=False)

        log.info(
            f"Consumer ready [agentic] concurrency={CONCURRENCY} "
            f"agents={router.registered()}"
        )
        print(
            f"Ready to receive [agentic] — agents: {router.registered()} "
            f"concurrency={CONCURRENCY}"
        )

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                asyncio.create_task(_handle_message(message, router))
