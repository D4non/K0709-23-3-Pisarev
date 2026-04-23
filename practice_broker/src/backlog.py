from __future__ import annotations

import redis.asyncio as redis

from .config import RabbitMQConfig, RedisConfig


async def rabbitmq_queue_depth(cfg: RabbitMQConfig) -> int | None:
    try:
        import aio_pika

        conn = await aio_pika.connect_robust(cfg.amqp_url)
        ch = await conn.channel()
        q = await ch.declare_queue(cfg.queue_name, passive=True)
        depth = int(q.declaration_result.message_count)
        await ch.close()
        await conn.close()
        return depth
    except Exception:
        return None


async def redis_stream_depth_and_pending(cfg: RedisConfig) -> tuple[int | None, int | None]:
    client = redis.from_url(cfg.url, decode_responses=False)
    try:
        depth = int(await client.xlen(cfg.stream_name))
    except Exception:
        depth = None
    try:
        pending = await client.xpending(cfg.stream_name, cfg.group_name)
        pending_count = int(pending["pending"]) if isinstance(pending, dict) else int(pending[0])
    except Exception:
        pending_count = None
    await client.aclose()
    return depth, pending_count
