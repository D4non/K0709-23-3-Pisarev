from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RabbitMQConfig:
    amqp_url: str = "amqp://guest:guest@localhost:5672/"
    queue_name: str = "bench_queue"


@dataclass(frozen=True)
class RedisConfig:
    url: str = "redis://localhost:6379/0"
    stream_name: str = "bench_stream"
    group_name: str = "bench_group"
