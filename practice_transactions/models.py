from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import date

Base = declarative_base()


class Customer(Base):
    __tablename__ = 'customers'

    CustomerID = Column(Integer, primary_key=True, autoincrement=True)
    FirstName = Column(String(100), nullable=False)
    LastName = Column(String(100), nullable=False)
    Email = Column(String(150), unique=True, nullable=False)

    orders = relationship('Order', back_populates='customer')


class Product(Base):
    __tablename__ = 'products'

    ProductID = Column(Integer, primary_key=True, autoincrement=True)
    ProductName = Column(String(200), nullable=False)
    Price = Column(Float, nullable=False)

    order_items = relationship('OrderItem', back_populates='product')


class Order(Base):
    __tablename__ = 'orders'

    OrderID = Column(Integer, primary_key=True, autoincrement=True)
    CustomerID = Column(Integer, ForeignKey('customers.CustomerID'), nullable=False)
    OrderDate = Column(Date, nullable=False, default=date.today)
    TotalAmount = Column(Float, nullable=False, default=0.0)

    customer = relationship('Customer', back_populates='orders')
    order_items = relationship('OrderItem', back_populates='order')


class OrderItem(Base):
    __tablename__ = 'orderitems'

    OrderItemID = Column(Integer, primary_key=True, autoincrement=True)
    OrderID = Column(Integer, ForeignKey('orders.OrderID'), nullable=False)
    ProductID = Column(Integer, ForeignKey('products.ProductID'), nullable=False)
    Quantity = Column(Integer, nullable=False)
    Subtotal = Column(Float, nullable=False)

    order = relationship('Order', back_populates='order_items')
    product = relationship('Product', back_populates='order_items')
