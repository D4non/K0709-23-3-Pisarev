from __future__ import annotations

import math
import time
from dataclasses import dataclass, field


def now_ns() -> int:
    return time.time_ns()


def ns_to_ms(ns: int) -> float:
    return ns / 1_000_000.0


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return float("nan")
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return d0 + d1


@dataclass
class LatencyStats:
    samples_ms: list[float] = field(default_factory=list)

    def add_ns(self, delta_ns: int) -> None:
        self.samples_ms.append(ns_to_ms(delta_ns))

    def summary(self) -> dict[str, float]:
        if not self.samples_ms:
            return {"avg_ms": float("nan"), "p95_ms": float("nan"), "max_ms": float("nan")}
        s = sorted(self.samples_ms)
        avg = sum(s) / len(s)
        return {"avg_ms": avg, "p95_ms": percentile(s, 95), "max_ms": s[-1]}


@dataclass
class Counter:
    sent: int = 0
    published_ok: int = 0
    publish_errors: int = 0
    consumed_ok: int = 0
    consume_errors: int = 0
