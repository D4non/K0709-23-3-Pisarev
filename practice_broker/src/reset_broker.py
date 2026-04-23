from __future__ import annotations

import asyncio
import time

from .config import RabbitMQConfig, RedisConfig


async def reset_broker(broker: str) -> None:
    """
    Сбрасывает состояние брокера перед прогоном.

    Почему это важно:
    - RabbitMQ: если прогон упал, в очереди могут остаться сообщения от предыдущего запуска.
    - Redis Stream накапливает записи, даже если consumer всё прочитал.
      Без очистки следующие прогоны будут нечестными и Redis может упасть по памяти,
      после чего consumer получит ошибки вида "Connection closed by server".
    """

    b = broker.lower().strip()
    if b == "redis":
        await _reset_redis(RedisConfig())
        return
    if b == "rabbitmq":
        await _reset_rabbitmq(RabbitMQConfig())
        return
    raise ValueError(f"Unknown broker: {broker}")


async def _reset_redis(cfg: RedisConfig) -> None:
    import redis.asyncio as redis

    client = redis.from_url(cfg.url, decode_responses=False)
    try:
        await _wait_redis_ready(client, timeout_sec=30)
        # Полностью удаляем stream (вместе с consumer group), чтобы каждый прогон был "с нуля".
        await client.delete(cfg.stream_name)
    finally:
        await client.aclose()


async def _reset_rabbitmq(cfg: RabbitMQConfig) -> None:
    try:
        import aio_pika
    except Exception:
        # Если зависимости не стоят, просто пропускаем reset.
        return

    await _wait_rabbitmq_ready(cfg, timeout_sec=30)

    conn = await aio_pika.connect_robust(cfg.amqp_url, timeout=10)
    ch = await conn.channel()
    # Важно: если очередь уже была создана с другими параметрами (например auto_delete=true),
    # declare_queue с "новыми" параметрами упадёт с PRECONDITION_FAILED.
    # Поэтому: удаляем очередь и создаём заново с текущими параметрами стенда.
    try:
        await ch.queue_delete(cfg.queue_name, if_unused=False, if_empty=False)
    except Exception:
        pass

    q = await ch.declare_queue(cfg.queue_name, durable=False, auto_delete=False)
    await q.purge()
    await ch.close()
    await conn.close()


async def _wait_rabbitmq_ready(cfg: RabbitMQConfig, timeout_sec: int) -> None:
    import aio_pika

    start = time.monotonic()
    delay = 0.5
    last_exc: Exception | None = None
    while True:
        try:
            conn = await aio_pika.connect_robust(cfg.amqp_url, timeout=5)
            await conn.close()
            return
        except Exception as e:
            last_exc = e
            if time.monotonic() - start >= timeout_sec:
                raise RuntimeError(
                    f"RabbitMQ не стал доступен за {timeout_sec}s. "
                    f"Убедитесь, что контейнер запущен (docker compose up -d). "
                    f"Последняя ошибка: {last_exc}"
                ) from last_exc
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 3.0)


async def _wait_redis_ready(client, timeout_sec: int) -> None:
    start = time.monotonic()
    delay = 0.2
    while True:
        try:
            await client.ping()
            return
        except Exception:
            if time.monotonic() - start >= timeout_sec:
                raise
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 2.0)

