from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import time
from dataclasses import asdict, dataclass

from .brokers import Consumer, Publisher, make_consumer, make_publisher
from .message import BenchMessage, make_message
from .reset_broker import reset_broker
from .stats import Counter, LatencyStats, now_ns


@dataclass
class RunResult:
    ts_iso: str
    broker: str
    duration_sec: int
    drain_sec: int
    producers: int
    consumers: int
    rate: int
    payload_bytes: int
    sent: int
    published_ok: int
    publish_errors: int
    consumed_ok: int
    consume_errors: int
    avg_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float


async def producer_task(
    pub: Publisher,
    counter: Counter,
    *,
    producer_rate: float,
    payload_bytes: int,
    stop_at_ns: int,
    seq_offset: int,
) -> None:
    seq = 0
    next_send = time.perf_counter()
    while now_ns() < stop_at_ns:
        counter.sent += 1
        msg = make_message(seq_offset + seq, payload_bytes)
        seq += 1
        try:
            # При деградации брокера publish может "подвисать" на сети/бэкенде.
            # Таймаут позволяет фиксировать ошибки и продолжать тест.
            await asyncio.wait_for(pub.publish(msg.to_bytes()), timeout=5.0)
            counter.published_ok += 1
        except Exception:
            counter.publish_errors += 1

        if producer_rate > 0:
            next_send += 1.0 / producer_rate
            delay = next_send - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                # Если мы отстаём от целевого rate, всё равно отдаём управление event loop,
                # чтобы consumer и heartbeats не "умирали" из-за CPU-starvation.
                await asyncio.sleep(0)


async def consumer_task(cons: Consumer, counter: Counter, lat: LatencyStats) -> None:
    async def on_message(raw: bytes) -> None:
        try:
            msg = BenchMessage.from_bytes(raw)
            lat.add_ns(now_ns() - msg.created_ns)
            counter.consumed_ok += 1
        except Exception:
            counter.consume_errors += 1

    await cons.run(on_message)


def _ensure_results_header(path: str, fieldnames: list[str]) -> None:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()


def _append_result(path: str, row: dict) -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writerow(row)


async def run_once(
    *,
    broker: str,
    duration_sec: int,
    drain_sec: int,
    rate: int,
    payload_bytes: int,
    producers: int,
    consumers: int,
    results_csv: str,
) -> RunResult:
    broker = broker.lower().strip()

    counter = Counter()
    lat = LatencyStats()

    pubs: list[Publisher] = []
    cons: list[Consumer] = []
    try:
        await reset_broker(broker)
        pubs = [await make_publisher(broker) for _ in range(producers)]
        cons = [await make_consumer(broker, consumer_name=f"c{i}") for i in range(consumers)]

        stop_at_ns = now_ns() + duration_sec * 1_000_000_000
        per_producer_rate = (rate / producers) if producers > 0 else 0.0

        consumer_tasks = [asyncio.create_task(consumer_task(c, counter, lat)) for c in cons]
        producer_tasks = [
            asyncio.create_task(
                producer_task(
                    pubs[i],
                    counter,
                    producer_rate=per_producer_rate,
                    payload_bytes=payload_bytes,
                    stop_at_ns=stop_at_ns,
                    seq_offset=i * 10_000_000,
                )
            )
            for i in range(producers)
        ]

        await asyncio.gather(*producer_tasks)
        await asyncio.sleep(drain_sec)

        for c in cons:
            await c.stop()

        consumer_results = await asyncio.gather(*consumer_tasks, return_exceptions=True)
        for r in consumer_results:
            if isinstance(r, Exception):
                # Для RabbitMQ consumer может выбросить исключение при штатном закрытии соединения.
                # Это не влияет на корректность метрик, поэтому не засчитываем как ошибку.
                if broker == "rabbitmq":
                    try:
                        import aio_pika

                        if isinstance(r, aio_pika.exceptions.AMQPError):
                            continue
                    except Exception:
                        pass
                counter.consume_errors += 1
                print(f"[consumer_task_error] {type(r).__name__}: {r}", file=sys.stderr)
    finally:
        for p in pubs:
            try:
                await p.close()
            except Exception:
                pass

    lat_sum = lat.summary()
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    res = RunResult(
        ts_iso=ts_iso,
        broker=broker,
        duration_sec=duration_sec,
        drain_sec=drain_sec,
        producers=producers,
        consumers=consumers,
        rate=rate,
        payload_bytes=payload_bytes,
        sent=counter.sent,
        published_ok=counter.published_ok,
        publish_errors=counter.publish_errors,
        consumed_ok=counter.consumed_ok,
        consume_errors=counter.consume_errors,
        avg_latency_ms=float(lat_sum["avg_ms"]),
        p95_latency_ms=float(lat_sum["p95_ms"]),
        max_latency_ms=float(lat_sum["max_ms"]),
    )

    row = asdict(res)
    _ensure_results_header(results_csv, list(row.keys()))
    _append_result(results_csv, row)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", choices=["rabbitmq", "redis"], required=True)
    ap.add_argument("--duration-sec", type=int, default=10)
    ap.add_argument("--drain-sec", type=int, default=2)
    ap.add_argument("--rate", type=int, default=1000)
    ap.add_argument("--payload-bytes", type=int, default=1024)
    ap.add_argument("--producers", type=int, default=1)
    ap.add_argument("--consumers", type=int, default=1)
    ap.add_argument("--results-csv", default="results/results.csv")
    args = ap.parse_args()

    res = asyncio.run(
        run_once(
            broker=args.broker,
            duration_sec=args.duration_sec,
            drain_sec=args.drain_sec,
            rate=args.rate,
            payload_bytes=args.payload_bytes,
            producers=args.producers,
            consumers=args.consumers,
            results_csv=args.results_csv,
        )
    )
    print(asdict(res))


if __name__ == "__main__":
    main()
