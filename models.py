"""SQLAlchemy models for the customer/order practice database."""

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="고객 고유 ID")
    name: Mapped[str] = mapped_column(String, nullable=False, comment="고객 이름")
    email: Mapped[str | None] = mapped_column(String, unique=True, comment="고객 이메일(고유값)")
    phone: Mapped[str | None] = mapped_column(String, comment="고객 전화번호")
    address: Mapped[str | None] = mapped_column(Text, comment="고객 주소")
    created_at: Mapped[str] = mapped_column(String, nullable=False, comment="고객 등록 일시(ISO 8601)")
    tier: Mapped[str] = mapped_column(String, nullable=False, default="일반", comment="고객 등급(VIP/일반/신규)")

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="상품 고유 ID")
    name: Mapped[str] = mapped_column(String, nullable=False, comment="상품명")
    category: Mapped[str | None] = mapped_column(String, comment="상품 분류")
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, comment="현재 상품 단가")
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="재고 수량")

    orders: Mapped[list["Order"]] = relationship(back_populates="product")


class Employee(Base):
    __tablename__ = "employees"

    employee_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="직원 고유 ID")
    name: Mapped[str] = mapped_column(String, nullable=False, comment="직원 이름")
    email: Mapped[str | None] = mapped_column(String, unique=True, comment="직원 이메일(고유값)")
    department: Mapped[str | None] = mapped_column(String, comment="소속 부서")
    hire_date: Mapped[str | None] = mapped_column(String, comment="입사일(ISO 8601 날짜)")
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True, comment="bcrypt 비밀번호 해시")

    orders: Mapped[list["Order"]] = relationship(back_populates="employee")


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="주문 고유 ID")
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id"), nullable=False, comment="주문 고객 ID")
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False, comment="주문 상품 ID")
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.employee_id"), nullable=False, comment="담당 직원 ID")
    order_date: Mapped[str] = mapped_column(String, nullable=False, comment="주문 일시(최근 2년, ISO 8601)")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="주문 수량")
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, comment="주문 시점 단가")
    status: Mapped[str] = mapped_column(String, nullable=False, comment="주문 상태")
    total_amount: Mapped[float] = mapped_column(Float, nullable=False, comment="주문 금액(주문 시점 단가 x 수량)")

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    product: Mapped["Product"] = relationship(back_populates="orders")
    employee: Mapped["Employee"] = relationship(back_populates="orders")
