from __future__ import annotations

import base64
import time
from dataclasses import dataclass

import orjson

_PAYLOAD_B64_CACHE: dict[int, str] = {}


@dataclass(frozen=True)
class BenchMessage:
    msg_id: str
    created_ns: int
    payload_b64: str

    @property
    def payload_bytes(self) -> int:
        return len(base64.b64decode(self.payload_b64))

    def to_bytes(self) -> bytes:
        return orjson.dumps(
            {
                "msg_id": self.msg_id,
                "created_ns": self.created_ns,
                "payload_b64": self.payload_b64,
            }
        )

    @staticmethod
    def from_bytes(raw: bytes) -> "BenchMessage":
        obj = orjson.loads(raw)
        return BenchMessage(
            msg_id=str(obj["msg_id"]),
            created_ns=int(obj["created_ns"]),
            payload_b64=str(obj["payload_b64"]),
        )


def make_message(seq: int, payload_bytes: int) -> BenchMessage:
    # В бенчмарке нас интересует работа брокера, а не скорость генерации случайных байт.
    # Поэтому payload одинаковый для всех сообщений одного размера (кэшируем base64-строку).
    payload_b64 = _PAYLOAD_B64_CACHE.get(payload_bytes)
    if payload_b64 is None:
        payload = b"\x00" * payload_bytes
        payload_b64 = base64.b64encode(payload).decode("ascii")
        _PAYLOAD_B64_CACHE[payload_bytes] = payload_b64
    # msg_id: deterministic per run for easier debugging/logging
    msg_id = f"{seq}"
    return BenchMessage(msg_id=msg_id, created_ns=time.time_ns(), payload_b64=payload_b64)
