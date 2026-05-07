-- ============================================================
-- НАСТРОЙКА: Создание таблиц и тестовых данных
-- ============================================================
-- Запустить ОДИН РАЗ перед демонстрацией всех аномалий.
--
-- Подключение к PostgreSQL через Docker:
--   docker exec -it football-postgres psql -U football_user -d football_db
--
-- Затем выполнить этот файл:
--   \i /path/to/00_setup.sql
-- Или скопировать и вставить содержимое в psql.
-- ============================================================

-- Очистка существующих таблиц
DROP TABLE IF EXISTS accounts CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS counters CASCADE;

-- -------------------------------------------------------
-- Таблица ACCOUNTS
-- Используется в аномалиях: dirty read, non-repeatable read
-- Хранит трансферные бюджеты футбольных клубов
-- -------------------------------------------------------
CREATE TABLE accounts (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(100)   NOT NULL,
    balance DECIMAL(10, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (name, balance) VALUES
    ('Real_Madrid', 1000.00),
    ('Barcelona',    500.00);

-- -------------------------------------------------------
-- Таблица ORDERS
-- Используется в аномалии: phantom read
-- Хранит заказы из магазина клубной атрибутики
-- -------------------------------------------------------
CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER        NOT NULL,
    product     VARCHAR(100)   NOT NULL,
    amount      DECIMAL(10, 2) NOT NULL
);

INSERT INTO orders (customer_id, product, amount) VALUES
    (1, 'VIP_Ticket',   1500.00),
    (1, 'Team_Scarf',     25.00),
    (2, 'Match_Ball',     75.00),
    (2, 'Season_Pass',   300.00),
    (1, 'Training_Kit',  120.00);

-- -------------------------------------------------------
-- Таблица COUNTERS
-- Используется в аномалии: lost update
-- Хранит статистику матчей
-- -------------------------------------------------------
CREATE TABLE counters (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(100) NOT NULL,
    value INTEGER      NOT NULL DEFAULT 0
);

INSERT INTO counters (name, value) VALUES
    ('match_views',   100),
    ('goals_scored',   50);

-- -------------------------------------------------------
-- Проверка результата
-- -------------------------------------------------------
SELECT 'accounts' AS table_name, COUNT(*) AS row_count FROM accounts
UNION ALL
SELECT 'orders',   COUNT(*) FROM orders
UNION ALL
SELECT 'counters', COUNT(*) FROM counters;

SELECT * FROM accounts;
SELECT * FROM orders;
SELECT * FROM counters;
