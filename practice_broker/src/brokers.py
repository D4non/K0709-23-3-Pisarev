from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

import aio_pika
import redis.asyncio as redis
from redis.exceptions import ResponseError

from .config import RabbitMQConfig, RedisConfig


class Publisher(Protocol):
    async def publish(self, body: bytes) -> None: ...

    async def close(self) -> None: ...


class Consumer(Protocol):
    async def run(self, on_message: Callable[[bytes], Awaitable[None]]) -> None: ...

    async def stop(self) -> None: ...


@dataclass
class RabbitPublisher:
    cfg: RabbitMQConfig
    _conn: aio_pika.RobustConnection | None = None
    _channel: aio_pika.RobustChannel | None = None

    async def _ensure(self) -> None:
        if self._conn is None:
            self._conn = await aio_pika.connect_robust(self.cfg.amqp_url)
        if self._channel is None:
            self._channel = await self._conn.channel(publisher_confirms=False)
            # auto_delete=False: иначе очередь может исчезать между прогонами/переподключениями,
            # и RabbitMQ начнёт "возвращать" сообщения (Basic.Return) или терять их.
            await self._channel.declare_queue(self.cfg.queue_name, durable=False, auto_delete=False)

    async def publish(self, body: bytes) -> None:
        await self._ensure()
        assert self._channel is not None
        msg = aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT)
        await self._channel.default_exchange.publish(msg, routing_key=self.cfg.queue_name)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        if self._conn is not None:
            await self._conn.close()


@dataclass
class RabbitConsumer:
    cfg: RabbitMQConfig
    prefetch: int = 100
    _conn: aio_pika.RobustConnection | None = None
    _channel: aio_pika.RobustChannel | None = None
    _task: asyncio.Task[None] | None = None
    _stopping: asyncio.Event = field(default_factory=asyncio.Event)

    async def run(self, on_message: Callable[[bytes], Awaitable[None]]) -> None:
        try:
            self._conn = await aio_pika.connect_robust(self.cfg.amqp_url)
            self._channel = await self._conn.channel()
            await self._channel.set_qos(prefetch_count=self.prefetch)
            queue = await self._channel.declare_queue(self.cfg.queue_name, durable=False, auto_delete=False)

            async with queue.iterator() as it:
                async for message in it:
                    async with message.process(requeue=True):
                        await on_message(message.body)
                    if self._stopping.is_set():
                        break
        except aio_pika.exceptions.AMQPError:
            # При штатной остановке мы закрываем channel/connection — aio-pika может выбросить AMQPError.
            # Это не должно считаться ошибкой теста.
            if not self._stopping.is_set():
                raise
        finally:
            try:
                if self._channel is not None:
                    await self._channel.close()
            finally:
                if self._conn is not None:
                    await self._conn.close()

    async def stop(self) -> None:
        self._stopping.set()
        # Закрываем соединение (run() перехватит "ожидаемую" AMQP-ошибку при закрытии).
        if self._channel is not None:
            try:
                await self._channel.close()
            except Exception:
                pass
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass


@dataclass
class RedisPublisher:
    cfg: RedisConfig
    _client: redis.Redis | None = None

    async def _ensure(self) -> None:
        if self._client is None:
            self._client = redis.from_url(self.cfg.url, decode_responses=False)

    async def publish(self, body: bytes) -> None:
        await self._ensure()
        assert self._client is not None
        await self._client.xadd(self.cfg.stream_name, {"data": body}, maxlen=None)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()


@dataclass
class RedisConsumer:
    cfg: RedisConfig
    consumer_name: str
    block_ms: int = 500
    count: int = 50
    _client: redis.Redis | None = None
    _stopping: asyncio.Event = field(default_factory=asyncio.Event)

    async def _ensure(self) -> None:
        if self._client is None:
            self._client = redis.from_url(self.cfg.url, decode_responses=False)
            try:
                await self._client.xgroup_create(
                    name=self.cfg.stream_name,
                    groupname=self.cfg.group_name,
                    id="0-0",
                    mkstream=True,
                )
            except ResponseError as e:
                # BUSYGROUP means "group already exists" (нормально для повторных прогонов).
                # Другие ошибки важно не глотать, иначе consumer может "умирать" молча.
                if "BUSYGROUP" not in str(e):
                    raise

    async def run(self, on_message: Callable[[bytes], Awaitable[None]]) -> None:
        await self._ensure()
        assert self._client is not None

        try:
            while not self._stopping.is_set():
                resp = await self._client.xreadgroup(
                    groupname=self.cfg.group_name,
                    consumername=self.consumer_name,
                    streams={self.cfg.stream_name: ">"},
                    count=self.count,
                    block=self.block_ms,
                )
                if not resp:
                    continue

                for _stream, entries in resp:
                    for entry_id, fields in entries:
                        body = fields.get(b"data", b"")
                        await on_message(body)
                        await self._client.xack(self.cfg.stream_name, self.cfg.group_name, entry_id)
        except Exception:
            # При штатной остановке aclose() прерывает блокирующий xreadgroup — это ожидаемо.
            if not self._stopping.is_set():
                raise

    async def stop(self) -> None:
        self._stopping.set()
        if self._client is not None:
            await self._client.aclose()


async def make_publisher(broker: str) -> Publisher:
    broker = broker.lower().strip()
    if broker == "rabbitmq":
        return RabbitPublisher(RabbitMQConfig())
    if broker == "redis":
        return RedisPublisher(RedisConfig())
    raise ValueError(f"Unknown broker: {broker}")


async def make_consumer(broker: str, consumer_name: str) -> Consumer:
    broker = broker.lower().strip()
    if broker == "rabbitmq":
        return RabbitConsumer(RabbitMQConfig())
    if broker == "redis":
        return RedisConsumer(RedisConfig(), consumer_name=consumer_name)
    raise ValueError(f"Unknown broker: {broker}")
