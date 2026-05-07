-- ============================================================
-- ПРЕДОТВРАЩЕНИЕ АНОМАЛИЙ ИЗОЛЯЦИИ
-- ============================================================
-- Этот скрипт показывает, как предотвратить каждую аномалию.
-- Запускается в ОДНОЙ СЕССИИ (не требует параллельных терминалов).
-- ============================================================

-- ============================================================
-- 1. DIRTY READ — PostgreSQL предотвращает автоматически
-- ============================================================
-- В PostgreSQL нет настоящего READ UNCOMMITTED.
-- Минимальный уровень — READ COMMITTED (защита от dirty read).
-- Дополнительных действий не требуется.

SHOW default_transaction_isolation;
-- Ожидаемый результат: read committed

-- ============================================================
-- 2. ПРЕДОТВРАЩЕНИЕ NON-REPEATABLE READ → REPEATABLE READ
-- ============================================================

-- Сброс данных
UPDATE accounts SET balance = 1000.00 WHERE name = 'Real_Madrid';

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

-- Первое чтение
SELECT name, balance FROM accounts WHERE name = 'Real_Madrid';
-- Результат: 1000.00

-- (Здесь другая сессия обновит balance до 2000.00 и сделает COMMIT)
-- Для чистоты демонстрации: откроем вложенный блок через dblink
-- или просто покажем что будет при повторном чтении

-- Повторное чтение в ТОЙ ЖЕ транзакции
SELECT name, balance FROM accounts WHERE name = 'Real_Madrid';
-- Результат: 1000.00 — ОДИНАКОВЫЙ результат! Аномалии нет.
-- PostgreSQL видит снимок данных на момент BEGIN (MVCC).

COMMIT;

-- ============================================================
-- 3. ПРЕДОТВРАЩЕНИЕ PHANTOM READ → SERIALIZABLE
-- ============================================================

-- Сброс
DELETE FROM orders WHERE product = 'VIP_Box';

BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS expensive_orders FROM orders WHERE amount > 100;
-- Результат: 3

-- (В параллельной сессии другой пользователь вставляет новую строку)
-- На уровне SERIALIZABLE PostgreSQL отследит зависимость чтения:
-- если параллельная вставка пройдёт — текущая транзакция получит
-- ERROR: could not serialize access due to read/write dependencies
-- и должна быть повторена приложением.

-- Примечание: REPEATABLE READ в PostgreSQL тоже предотвращает phantom read
-- (в отличие от стандарта SQL, где REPEATABLE READ не даёт такой гарантии).

SELECT COUNT(*) AS expensive_orders FROM orders WHERE amount > 100;
-- Результат: 3 — одинаковый (снимок не изменился)

COMMIT;

-- ============================================================
-- 4. ПРЕДОТВРАЩЕНИЕ LOST UPDATE — три способа
-- ============================================================

-- Сброс
UPDATE counters SET value = 100 WHERE name = 'match_views';

-- --- Способ А: Атомарный UPDATE (рекомендуется) ---
UPDATE counters SET value = value + 1 WHERE name = 'match_views';
-- Одна атомарная операция — состояния гонки невозможны

SELECT value FROM counters WHERE name = 'match_views';
-- Результат: 101

-- --- Способ Б: SELECT FOR UPDATE (пессимистичная блокировка) ---
UPDATE counters SET value = 100 WHERE name = 'match_views'; -- сброс

BEGIN;
SELECT value FROM counters WHERE name = 'match_views' FOR UPDATE;
-- Строка заблокирована. Параллельная транзакция будет ждать.
UPDATE counters SET value = (SELECT value FROM counters WHERE name = 'match_views') + 1
WHERE name = 'match_views';
COMMIT;

SELECT value FROM counters WHERE name = 'match_views';
-- Результат: 101 (правильно, без потерь)

-- ============================================================
-- ТАБЛИЦА УРОВНЕЙ ИЗОЛЯЦИИ И АНОМАЛИЙ
-- ============================================================
-- Уровень               | Dirty Read | Non-Rep. Read | Phantom Read | Lost Update
-- ----------------------|------------|---------------|--------------|------------
-- READ UNCOMMITTED      |  ВОЗМОЖНА* |    ВОЗМОЖНА   |   ВОЗМОЖНА   |  ВОЗМОЖЕН
-- READ COMMITTED (умолч)|    НЕТ     |    ВОЗМОЖНА   |   ВОЗМОЖНА   |  ВОЗМОЖЕН
-- REPEATABLE READ       |    НЕТ     |      НЕТ      |  НЕТ (в PG)  |    НЕТ
-- SERIALIZABLE          |    НЕТ     |      НЕТ      |     НЕТ      |    НЕТ
--
-- * PostgreSQL предотвращает dirty read даже при READ UNCOMMITTED
-- ============================================================
