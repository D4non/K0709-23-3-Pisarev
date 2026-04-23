from __future__ import annotations

import asyncio
import csv
import os
from collections import defaultdict

from .run_one import run_once


DEFAULT_PAYLOADS = [128, 1024, 10 * 1024, 100 * 1024]
DEFAULT_RATES = [1000, 5000, 10_000]


def _read_rows(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_summary_md(csv_path: str, out_md: str) -> None:
    rows = _read_rows(csv_path)
    if not rows:
        return

    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        key = (r["broker"], r["payload_bytes"], r["rate"])
        groups[key].append(r)

    lines: list[str] = []
    lines.append("## Summary результатов\n")
    lines.append("Формула throughput: `published_ok / duration_sec`.\n")
    lines.append(
        "| broker | payload_bytes | rate(msg/sec) | throughput(msg/sec) | consumed_ok | publish_errors | consume_errors | avg_ms | p95_ms | max_ms |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )

    def fnum(x: str) -> str:
        try:
            return f"{float(x):.2f}"
        except Exception:
            return x

    for (broker, payload_bytes, rate), gr in sorted(groups.items()):
        r = gr[-1]
        throughput = float(r["published_ok"]) / float(r["duration_sec"])
        lines.append(
            "| "
            + " | ".join(
                [
                    broker,
                    payload_bytes,
                    rate,
                    f"{throughput:.2f}",
                    r["consumed_ok"],
                    r["publish_errors"],
                    r["consume_errors"],
                    fnum(r["avg_latency_ms"]),
                    fnum(r["p95_latency_ms"]),
                    fnum(r["max_latency_ms"]),
                ]
            )
            + " |"
        )

    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def main_async() -> None:
    results_csv = "results/results.csv"
    duration_sec = 10
    drain_sec = 2
    producers = 1
    consumers = 1

    # Чтобы RabbitMQ/Redis успели стать "healthy" после docker compose up,
    # небольшая пауза перед стартом матрицы делает прогоны стабильнее.
    await asyncio.sleep(2)

    for broker in ("rabbitmq", "redis"):
        for payload in DEFAULT_PAYLOADS:
            for rate in DEFAULT_RATES:
                await run_once(
                    broker=broker,
                    duration_sec=duration_sec,
                    drain_sec=drain_sec,
                    rate=rate,
                    payload_bytes=payload,
                    producers=producers,
                    consumers=consumers,
                    results_csv=results_csv,
                )

    _write_summary_md(results_csv, "results/summary.md")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
