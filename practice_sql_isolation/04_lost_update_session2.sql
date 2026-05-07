-- ============================================================
-- АНОМАЛИЯ 4: LOST UPDATE — СЕССИЯ 2
-- ============================================================
-- Запустите ПОСЛЕ того, как Сессия 1 выполнила ШАГ 2
-- (прочитала значение счётчика, но ещё не обновила его)
-- ============================================================

-- ШАГ (Сессия 2): Читаем то же значение и обновляем
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT name, value FROM counters WHERE name = 'match_views';
-- Результат: value = 100 (то же самое значение, что прочитала Сессия 1!)

-- Вычисляем новое значение: 100 + 1 = 101
UPDATE counters SET value = 101 WHERE name = 'match_views';

COMMIT;
-- Зафиксировали: value = 101

-- ===> ПЕРЕКЛЮЧИТЕСЬ В ТЕРМИНАЛ 1 И ВЫПОЛНИТЕ ШАГ 3 <===

-- ========================================================
-- КАК ИЗБЕЖАТЬ LOST UPDATE:
--
-- Способ 1 — SELECT FOR UPDATE (пессимистичная блокировка):
--   BEGIN;
--   SELECT value FROM counters WHERE name = 'match_views' FOR UPDATE;
--   -- Строка заблокирована, Сессия 2 будет ждать
--   UPDATE counters SET value = <old_value + 1> WHERE name = 'match_views';
--   COMMIT;
--
-- Способ 2 — атомарный UPDATE (самый простой и надёжный):
--   UPDATE counters SET value = value + 1 WHERE name = 'match_views';
--   -- PostgreSQL выполнит операцию атомарно, без состояния гонки
--
-- Способ 3 — REPEATABLE READ (оптимистичная блокировка):
--   BEGIN;
--   SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
--   SELECT value FROM counters WHERE name = 'match_views';
--   UPDATE counters SET value = <old_value + 1> WHERE name = 'match_views';
--   COMMIT;
--   -- PostgreSQL обнаружит конфликт и выбросит serialization error
--   -- Приложение должно повторить транзакцию
-- ========================================================
