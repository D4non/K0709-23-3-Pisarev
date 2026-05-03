"""
Единый нагрузочный тест для трёх стратегий кеширования.

Сценарии:
  read-heavy  — 80 % чтений / 20 % записей
  balanced    — 50 % чтений / 50 % записей
  write-heavy — 20 % чтений / 80 % записей

Метрики:
  throughput  (запросов/сек)
  avg latency (мс)
  db_reads    (обращений к БД на чтение)
  db_writes   (обращений к БД на запись)
  hit rate    (%)
"""

import random
import time

from cache_strategies import (
    LazyLoadingCache,
    WriteThroughCache,
    WriteBackCache,
    Metrics,
    reset_db,
    seed_data,
    CITIES,
)

# ─── Константы ──────────────────────────────────────────────────────────────

NUM_USERS    = 100   # записей в БД
NUM_REQUESTS = 500   # запросов на один тест
RANDOM_SEED  = 42    # воспроизводимость

SCENARIOS = [
    ("Read-Heavy  (80/20)", 0.80),
    ("Balanced    (50/50)", 0.50),
    ("Write-Heavy (20/80)", 0.20),
]


# ─── Генерация одинакового набора запросов ───────────────────────────────────

def make_requests(read_ratio: float) -> list[tuple[int, bool]]:
    """
    Возвращает список (user_id, is_read) одинаковый для всех стратегий
    при одном сценарии (фиксированный seed).
    """
    rng = random.Random(RANDOM_SEED)
    return [
        (rng.randint(1, NUM_USERS), rng.random() < read_ratio)
        for _ in range(NUM_REQUESTS)
    ]


def make_write_payload(user_id: int, rng: random.Random) -> dict:
    return {
        "name": f"User_{user_id}_v{rng.randint(1, 999)}",
        "age":  rng.randint(18, 65),
        "city": rng.choice(CITIES),
    }


# ─── Прогон одного теста ────────────────────────────────────────────────────

def run_test(strategy, requests: list[tuple[int, bool]]) -> tuple[Metrics, float]:
    """
    Прогоняет список requests через strategy.
    Возвращает (metrics, throughput_rps).
    """
    strategy.reset()
    # Для write-payload нужен отдельный rng с тем же seed
    rng = random.Random(RANDOM_SEED + 1)

    if isinstance(strategy, WriteBackCache):
        strategy.start()

    t_start = time.perf_counter()

    for user_id, is_read in requests:
        if is_read:
            strategy.read(user_id)
        else:
            strategy.write(user_id, make_write_payload(user_id, rng))

    elapsed = time.perf_counter() - t_start

    if isinstance(strategy, WriteBackCache):
        strategy.stop()   # финальный flush в БД

    throughput = NUM_REQUESTS / elapsed
    return strategy.metrics, throughput


# ─── Вывод результатов ───────────────────────────────────────────────────────

COL = {
    "strategy":  28,
    "scenario":  22,
    "rps":        8,
    "latency":    9,
    "db_reads":  10,
    "db_writes": 10,
    "hit_rate":  10,
}

LINE_LEN = sum(COL.values()) + len(COL) - 1


def _header():
    h = (
        f"{'Стратегия':<{COL['strategy']}}"
        f"{'Сценарий':<{COL['scenario']}}"
        f"{'RPS':>{COL['rps']}}"
        f"{'Avg,мс':>{COL['latency']}}"
        f"{'DB reads':>{COL['db_reads']}}"
        f"{'DB writes':>{COL['db_writes']}}"
        f"{'Hit rate':>{COL['hit_rate']}}"
    )
    sep = "=" * LINE_LEN
    print(f"\n{sep}\n{h}\n{sep}")


def _row(strategy_name: str, scenario_name: str, m: Metrics, rps: float):
    print(
        f"{strategy_name:<{COL['strategy']}}"
        f"{scenario_name:<{COL['scenario']}}"
        f"{rps:>{COL['rps']}.1f}"
        f"{m.avg_latency_ms:>{COL['latency']}.3f}"
        f"{m.db_reads:>{COL['db_reads']}}"
        f"{m.db_writes:>{COL['db_writes']}}"
        f"{m.hit_rate_pct:>{COL['hit_rate']}.1f}%"
    )


# ─── Write-Back: демонстрация накопления записей ─────────────────────────────

def demo_writeback_accumulation():
    print("\n" + "=" * 60)
    print("WRITE-BACK: накопление записей до flush")
    print("=" * 60)

    reset_db()
    seed_data(NUM_USERS)

    # flush_interval=999 — фоновый поток не будет сбрасывать автоматически
    wb = WriteBackCache(flush_interval=999)
    rng = random.Random(7)

    print(f"\n  {'Запись №':>9}  {'Pending (грязных в кеше)':>25}  {'DB writes':>10}")
    print(f"  {'-'*9}  {'-'*25}  {'-'*10}")

    for i in range(1, 21):
        uid = rng.randint(1, NUM_USERS)
        wb.write(uid, make_write_payload(uid, rng))
        print(f"  {i:>9}  {wb.pending_writes:>25}  {wb.metrics.db_writes:>10}")

    print(f"\n  [flush] Сброс всех грязных записей в БД...")
    wb.flush()
    print(f"  После flush: pending={wb.pending_writes}, db_writes={wb.metrics.db_writes}")
    print()


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * LINE_LEN)
    print("  СРАВНЕНИЕ СТРАТЕГИЙ КЕШИРОВАНИЯ")
    print(f"  Пользователей в БД: {NUM_USERS}   Запросов на тест: {NUM_REQUESTS}")
    print("=" * LINE_LEN)

    all_results = []

    for scenario_name, read_ratio in SCENARIOS:
        requests = make_requests(read_ratio)

        print(f"\n>>> Сценарий: {scenario_name}")

        strategies = [
            LazyLoadingCache(),
            WriteThroughCache(),
            WriteBackCache(flush_interval=0.3),
        ]

        for strategy in strategies:
            # Каждая стратегия стартует с одинаковой чистой БД
            reset_db()
            seed_data(NUM_USERS)

            metrics, rps = run_test(strategy, requests)

            print(
                f"  {strategy.name:<28}  "
                f"RPS={rps:6.1f}  "
                f"avg={metrics.avg_latency_ms:.3f}ms  "
                f"DB_r={metrics.db_reads}  DB_w={metrics.db_writes}  "
                f"hit={metrics.hit_rate_pct:.1f}%"
            )
            all_results.append((strategy.name, scenario_name, metrics, rps))

    # Итоговая таблица
    _header()
    for strategy_name, scenario_name, m, rps in all_results:
        _row(strategy_name, scenario_name, m, rps)
    print("=" * LINE_LEN)

    # Демонстрация Write-Back
    demo_writeback_accumulation()

    # Выводы
    print("=" * LINE_LEN)
    print("ВЫВОДЫ")
    print("=" * LINE_LEN)
    print("""
  Lazy Loading (Cache-Aside):
    + Лучший hit rate при read-heavy нагрузке (после прогрева кеша).
    + Кеш заполняется только реально нужными данными.
    - При write-heavy нагрузке кеш постоянно инвалидируется → много DB reads.

  Write-Through:
    + Кеш всегда актуален: после записи данные сразу доступны из кеша.
    + Высокий hit rate при смешанной нагрузке.
    - Каждая запись = 2 операции (кеш + БД) → ниже RPS на write-heavy.

  Write-Back:
    + Максимальный RPS на write-heavy: записи в БД откладываются.
    + Наименьшая средняя задержка на записях.
    - Риск потери данных при падении сервиса до flush.
    - DB writes появляются «пачками» (видно в демо накопления).

  Рекомендации:
    Read-heavy   → Lazy Loading (минимум лишнего в кеше)
    Write-heavy  → Write-Back   (максимальная скорость записи)
    Balanced     → Write-Through (консистентность без сложности)
""")


if __name__ == "__main__":
    main()
