"""
Три стратегии кеширования:
  - Lazy Loading (Cache-Aside / Write-Around)
  - Write-Through
  - Write-Back (Write-Behind)

БД  — SQLite (стандартная библиотека Python, файл practice_cache.db).
Кеш — SimpleCache: in-memory dict, симулирует поведение Redis (GET/SET/DEL).
"""

from __future__ import annotations

import sqlite3
import threading
import time
import os
from typing import Any, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "practice_cache.db")

CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург"]


# ─── База данных ────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id   INTEGER PRIMARY KEY,
                name TEXT    NOT NULL,
                age  INTEGER NOT NULL,
                city TEXT    NOT NULL
            )
        """)
        conn.commit()


def reset_db() -> None:
    """Очищает таблицу users — вызывается перед каждым тестом.
    На Windows нельзя удалить файл SQLite пока открыты соединения,
    поэтому удаляем только данные, не файл."""
    with _connect() as conn:
        conn.execute("DROP TABLE IF EXISTS users")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id   INTEGER PRIMARY KEY,
                name TEXT    NOT NULL,
                age  INTEGER NOT NULL,
                city TEXT    NOT NULL
            )
        """)
        conn.commit()


def seed_data(n: int = 100) -> None:
    """Заполняет таблицу n пользователями."""
    with _connect() as conn:
        conn.executemany(
            "INSERT INTO users (id, name, age, city) VALUES (?, ?, ?, ?)",
            [
                (i, f"User_{i}", 18 + (i % 50), CITIES[i % len(CITIES)])
                for i in range(1, n + 1)
            ],
        )
        conn.commit()


def db_read(user_id: int) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def db_write(user_id: int, data: Dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET name=?, age=?, city=? WHERE id=?",
            (data["name"], data["age"], data["city"], user_id),
        )
        conn.commit()


# ─── Метрики ────────────────────────────────────────────────────────────────

class Metrics:
    """Потокобезопасный сборщик метрик одного теста."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        self.requests  = 0
        self.db_reads  = 0
        self.db_writes = 0
        self.cache_hits   = 0
        self.cache_misses = 0
        self.latencies: list[float] = []

    # --- внутренние счётчики (вызываются из стратегий) ---

    def add_read_hit(self, latency: float):
        with self._lock:
            self.requests    += 1
            self.cache_hits  += 1
            self.latencies.append(latency)

    def add_read_miss(self, latency: float):
        with self._lock:
            self.requests      += 1
            self.cache_misses  += 1
            self.db_reads      += 1
            self.latencies.append(latency)

    def add_write(self, latency: float, db_write_now: bool = True):
        with self._lock:
            self.requests += 1
            if db_write_now:
                self.db_writes += 1
            self.latencies.append(latency)

    def add_flush_writes(self, count: int):
        """Write-Back: засчитывает отложенные записи в БД."""
        with self._lock:
            self.db_writes += count

    # --- производные метрики ---

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies) * 1000

    @property
    def hit_rate_pct(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total else 0.0

    @property
    def db_accesses(self) -> int:
        return self.db_reads + self.db_writes

    @property
    def throughput(self) -> float:
        """Вычисляется снаружи (benchmark знает elapsed time)."""
        return 0.0  # placeholder


# ─── In-memory кеш (симуляция Redis) ────────────────────────────────────────

class SimpleCache:
    """
    Словарь, имитирующий Redis-команды GET / SET / DEL.
    Отдельное множество _dirty хранит «грязные» ключи для Write-Back.
    """

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._dirty: set[str] = set()

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._dirty.discard(key)

    def mark_dirty(self, key: str) -> None:
        self._dirty.add(key)

    def pop_dirty(self) -> set[str]:
        """Возвращает и очищает все грязные ключи (атомарно для flush)."""
        dirty = self._dirty.copy()
        self._dirty.clear()
        return dirty

    @property
    def dirty_count(self) -> int:
        return len(self._dirty)

    def clear(self) -> None:
        self._store.clear()
        self._dirty.clear()


# ─── Стратегия 1: Lazy Loading / Cache-Aside / Write-Around ─────────────────

class LazyLoadingCache:
    """
    Чтение:  сначала проверяется кеш; при промахе — читаем из БД и кладём в кеш.
    Запись:  идёт напрямую в БД; кеш для этого ключа инвалидируется (Write-Around).
    """

    name = "Lazy Loading (Cache-Aside)"

    def __init__(self):
        self.cache = SimpleCache()
        self.metrics = Metrics()

    def read(self, user_id: int) -> Optional[Dict]:
        t0 = time.perf_counter()
        key = f"user:{user_id}"

        cached = self.cache.get(key)
        if cached is not None:
            self.metrics.add_read_hit(time.perf_counter() - t0)
            return cached

        # Cache miss — идём в БД и заполняем кеш
        data = db_read(user_id)
        if data:
            self.cache.set(key, data)

        self.metrics.add_read_miss(time.perf_counter() - t0)
        return data

    def write(self, user_id: int, data: Dict) -> None:
        t0 = time.perf_counter()
        # Запись в БД
        db_write(user_id, data)
        # Инвалидация кеша (Write-Around: в кеш при записи не кладём)
        self.cache.delete(f"user:{user_id}")
        self.metrics.add_write(time.perf_counter() - t0, db_write_now=True)

    def reset(self) -> None:
        self.cache.clear()
        self.metrics.reset()


# ─── Стратегия 2: Write-Through ─────────────────────────────────────────────

class WriteThroughCache:
    """
    Чтение:  через кеш, при промахе загружаем из БД.
    Запись:  одновременно в кеш И в БД — данные всегда консистентны.
    """

    name = "Write-Through"

    def __init__(self):
        self.cache = SimpleCache()
        self.metrics = Metrics()

    def read(self, user_id: int) -> Optional[Dict]:
        t0 = time.perf_counter()
        key = f"user:{user_id}"

        cached = self.cache.get(key)
        if cached is not None:
            self.metrics.add_read_hit(time.perf_counter() - t0)
            return cached

        data = db_read(user_id)
        if data:
            self.cache.set(key, data)

        self.metrics.add_read_miss(time.perf_counter() - t0)
        return data

    def write(self, user_id: int, data: Dict) -> None:
        t0 = time.perf_counter()
        full = {"id": user_id, **data}
        # Запись в кеш
        self.cache.set(f"user:{user_id}", full)
        # Запись в БД (синхронно)
        db_write(user_id, data)
        self.metrics.add_write(time.perf_counter() - t0, db_write_now=True)

    def reset(self) -> None:
        self.cache.clear()
        self.metrics.reset()


# ─── Стратегия 3: Write-Back (Write-Behind) ──────────────────────────────────

class WriteBackCache:
    """
    Чтение:  через кеш, при промахе загружаем из БД.
    Запись:  только в кеш (быстро); ключ помечается «грязным».
    Flush:   фоновый поток периодически сбрасывает грязные ключи в БД.
    """

    name = "Write-Back (Write-Behind)"

    def __init__(self, flush_interval: float = 1.0):
        self.cache = SimpleCache()
        self.metrics = Metrics()
        self.flush_interval = flush_interval
        self._flush_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ---- управление фоновым потоком ----

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._flush_loop, daemon=True, name="wb-flush")
        self._thread.start()

    def stop(self) -> None:
        """Останавливает поток и делает финальный flush."""
        self._running = False
        self.flush()

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self.flush_interval)
            self.flush()

    # ---- принудительный сброс ----

    def flush(self) -> None:
        with self._flush_lock:
            dirty = self.cache.pop_dirty()
            if not dirty:
                return
            flushed = 0
            with _connect() as conn:
                for key in dirty:
                    data = self.cache.get(key)
                    if data:
                        conn.execute(
                            "UPDATE users SET name=?, age=?, city=? WHERE id=?",
                            (data["name"], data["age"], data["city"], data["id"]),
                        )
                        flushed += 1
                conn.commit()
            self.metrics.add_flush_writes(flushed)

    # ---- CRUD ----

    def read(self, user_id: int) -> Optional[Dict]:
        t0 = time.perf_counter()
        key = f"user:{user_id}"

        cached = self.cache.get(key)
        if cached is not None:
            self.metrics.add_read_hit(time.perf_counter() - t0)
            return cached

        data = db_read(user_id)
        if data:
            self.cache.set(key, data)

        self.metrics.add_read_miss(time.perf_counter() - t0)
        return data

    def write(self, user_id: int, data: Dict) -> None:
        t0 = time.perf_counter()
        full = {"id": user_id, **data}
        key = f"user:{user_id}"
        # Только в кеш; БД обновляется позже при flush
        self.cache.set(key, full)
        self.cache.mark_dirty(key)
        # db_write_now=False — запись в БД ещё не произошла
        self.metrics.add_write(time.perf_counter() - t0, db_write_now=False)

    @property
    def pending_writes(self) -> int:
        return self.cache.dirty_count

    def reset(self) -> None:
        self.cache.clear()
        self.metrics.reset()
