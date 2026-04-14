import os
import sys
from datetime import date
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
from models import Base, Customer, Product, Order, OrderItem

# Поддержка SQLite и PostgreSQL
db_type = os.getenv("DB_TYPE", "sqlite")

if db_type == "postgresql":
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@db:5432/onlinestore"
    )
    engine = create_engine(DATABASE_URL)
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///onlinestore.db")
    engine = create_engine(DATABASE_URL)

    # Включаем WAL для SQLite (имитация транзакций)
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

Session = sessionmaker(bind=engine)


def init_db():
    """Инициализация базы данных - создание всех таблиц."""
    Base.metadata.create_all(engine)
    print("База данных инициализирована.")


def seed_data():
    """Добавление тестовых данных, если их нет."""
    session = Session()
    try:
        if session.query(Customer).count() == 0:
            customers = [
                Customer(FirstName="Иван", LastName="Петров", Email="ivan@example.com"),
                Customer(FirstName="Анна", LastName="Сидорова", Email="anna@example.com"),
                Customer(FirstName="Пётр", LastName="Козлов", Email="petr@example.com"),
            ]
            session.add_all(customers)

        if session.query(Product).count() == 0:
            products = [
                Product(ProductName="Ноутбук", Price=55000.0),
                Product(ProductName="Смартфон", Price=30000.0),
                Product(ProductName="Наушники", Price=5000.0),
                Product(ProductName="Клавиатура", Price=3000.0),
                Product(ProductName="Монитор", Price=25000.0),
            ]
            session.add_all(products)

        session.commit()
        print("Тестовые данные добавлены.")
    except Exception as e:
        session.rollback()
        print(f"Ошибка при добавлении данных: {e}")
    finally:
        session.close()


# Сценарий 1: Размещение заказа
def place_order(customer_id: int, items: list[dict]):
    """
    Транзакция размещения заказа.

    :param customer_id: ID клиента
    :param items: список словарей вида {'product_id': int, 'quantity': int}
    """
    session = Session()
    try:
        # Начало транзакции
        session.begin()

        # 1. Проверяем существование клиента
        customer = session.get(Customer, customer_id)
        if not customer:
            raise ValueError(f"Клиент с ID={customer_id} не найден.")

        # 2. Создаём новый заказ
        new_order = Order(
            CustomerID=customer_id,
            OrderDate=date.today(),
            TotalAmount=0.0
        )
        session.add(new_order)
        session.flush()  # получаем OrderID

        # 3. Добавляем позиции заказа
        total_amount = 0.0
        for item in items:
            product = session.get(Product, item['product_id'])
            if not product:
                raise ValueError(f"Продукт с ID={item['product_id']} не найден.")

            subtotal = product.Price * item['quantity']

            order_item = OrderItem(
                OrderID=new_order.OrderID,
                ProductID=product.ProductID,
                Quantity=item['quantity'],
                Subtotal=subtotal
            )
            session.add(order_item)
            total_amount += subtotal

        # 4. Обновляем общую сумму заказа
        new_order.TotalAmount = total_amount

        # Коммит транзакции
        session.commit()
        print(f"Заказ #{new_order.OrderID} успешно создан на сумму {total_amount:.2f}")
        return new_order.OrderID

    except Exception as e:
        session.rollback()
        print(f"Ошибка при создании заказа: {e}")
        raise
    finally:
        session.close()


# Сценарий 2: Обновление email клиента
def update_customer_email(customer_id: int, new_email: str):
    """
    Атомарная транзакция обновления email клиента.
    """
    session = Session()
    try:
        session.begin()

        customer = session.get(Customer, customer_id)
        if not customer:
            raise ValueError(f"Клиент с ID={customer_id} не найден.")

        old_email = customer.Email
        customer.Email = new_email

        session.commit()
        print(f"Email клиента #{customer_id} обновлён: {old_email} -> {new_email}")

    except Exception as e:
        session.rollback()
        print(f"Ошибка при обновлении email: {e}")
        raise
    finally:
        session.close()


# Сценарий 3: Добавление нового продукта
def add_product(product_name: str, price: float):
    """
    Атомарная транзакция добавления нового продукта.
    """
    session = Session()
    try:
        session.begin()

        new_product = Product(
            ProductName=product_name,
            Price=price
        )
        session.add(new_product)

        session.commit()
        print(f"Продукт '{product_name}' добавлен с ID={new_product.ProductID}")
        return new_product.ProductID

    except Exception as e:
        session.rollback()
        print(f"Ошибка при добавлении продукта: {e}")
        raise
    finally:
        session.close()


# Главная функция - демонстрация всех сценариев
def main():

    # Инициализация
    init_db()
    seed_data()

    # --- Сценарий 1: Размещение заказа ---
    print("\n--- Сценарий 1: Размещение заказа ---")
    place_order(
        customer_id=1,
        items=[
            {'product_id': 1, 'quantity': 1},   # Ноутбук
            {'product_id': 3, 'quantity': 2},   # Наушники x2
        ]
    )

    # --- Сценарий 2: Обновление email ---
    print("\n--- Сценарий 2: Обновление email клиента ---")
    update_customer_email(1, "ivan.petrov@newmail.com")

    # --- Сценарий 3: Добавление нового продукта ---
    print("\n--- Сценарий 3: Добавление нового продукта ---")
    add_product("Веб-камера", 4500.0)

    print("\nВсе транзакции выполнены успешно!")


if __name__ == "__main__":
    main()
