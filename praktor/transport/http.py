"""
HTTP transport adapter.

publish(): POST JSON to an endpoint.
consume(): Long-poll GET endpoint that returns Server-Sent Events (SSE).

Configuration via env vars:
    PRAKTOR_HTTP_ENDPOINT  base URL, e.g. http://localhost:8080
    PRAKTOR_HTTP_API_KEY   bearer token (optional)
"""
from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from settings import create_log
from transport.transport import Transport, TransportMessage, TransportError

log = create_log()


class HTTPTransport:
    """
    HTTP-based transport. Useful for deployments that already have
    an HTTP API gateway and don't want to introduce RabbitMQ.

    publish: POST /publish/{routing_key}
    consume: GET  /consume/{routing_key}  (SSE stream)
    ack:     POST /ack/{message_id}
    nack:    POST /nack/{message_id}

    Note: requires aiohttp (pip install aiohttp). Raises ImportError if absent.
    """

    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        try:
            import aiohttp  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "HTTPTransport requires aiohttp: pip install aiohttp"
            ) from e
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._session = None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def _get_session(self):
        import aiohttp
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers())
        return self._session

    async def publish(self, message: bytes, routing_key: str) -> None:
        import aiohttp
        session = await self._get_session()
        url = f"{self._endpoint}/publish/{routing_key}"
        try:
            async with session.post(url, data=message) as resp:
                if resp.status >= 400:
                    raise TransportError(f"HTTP publish failed: {resp.status}")
        except aiohttp.ClientError as e:
            raise TransportError(f"HTTP publish error: {e}") from e

    async def consume(self, routing_key: str) -> AsyncGenerator[TransportMessage, None]:
        import aiohttp
        session = await self._get_session()
        url = f"{self._endpoint}/consume/{routing_key}"
        try:
            async with session.get(url) as resp:
                async for line in resp.content:
                    line = line.decode().strip()
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        try:
                            payload = json.loads(raw)
                            yield TransportMessage(
                                message_id=payload.get("message_id", uuid.uuid4().hex),
                                body=raw.encode(),
                            )
                        except json.JSONDecodeError:
                            log.warning(f"HTTPTransport: invalid SSE payload: {raw[:100]}")
        except aiohttp.ClientError as e:
            raise TransportError(f"HTTP consume error: {e}") from e

    async def ack(self, message_id: str) -> None:
        import aiohttp
        session = await self._get_session()
        url = f"{self._endpoint}/ack/{message_id}"
        try:
            async with session.post(url) as resp:
                if resp.status >= 400:
                    log.warning(f"HTTPTransport ack failed: {resp.status}")
        except aiohttp.ClientError as e:
            log.warning(f"HTTPTransport ack error (non-fatal): {e}")

    async def nack(self, message_id: str) -> None:
        import aiohttp
        session = await self._get_session()
        url = f"{self._endpoint}/nack/{message_id}"
        try:
            async with session.post(url) as resp:
                if resp.status >= 400:
                    log.warning(f"HTTPTransport nack failed: {resp.status}")
        except aiohttp.ClientError as e:
            log.warning(f"HTTPTransport nack error (non-fatal): {e}")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
