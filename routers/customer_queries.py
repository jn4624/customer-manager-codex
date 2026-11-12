"""Shared query helpers for customers visible in ordinary lookups."""

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Customer, HiddenCustomer


class CustomerEmailConflict(Exception):
    """Raised when a visible customer already uses the requested email."""


def visible_customers_statement():
    """Return a composable SELECT that excludes hidden customer records."""
    hidden_customer_ids = select(HiddenCustomer.customer_id).where(
        HiddenCustomer.customer_id == Customer.customer_id
    )
    return select(Customer).where(~hidden_customer_ids.exists())


def customer_region_expression():
    """Return the first address component as the customer's region."""
    address = func.trim(func.coalesce(Customer.address, ""))
    return func.substr(address, 1, func.instr(address.concat(" "), " ") - 1)


def search_customers_statement(statement, query: str | None):
    """Filter customers by case-insensitive partial name or email match."""
    search_text = query.strip() if query and query.strip() else ""
    if not search_text:
        return statement
    name_text = "".join(search_text.split())

    def escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    name_pattern = f"%{escape_like(name_text)}%"
    email_pattern = f"%{escape_like(search_text)}%"
    return statement.where(
        or_(
            func.replace(Customer.name, " ", "").ilike(name_pattern, escape="\\"),
            Customer.email.ilike(email_pattern, escape="\\"),
        )
    )


def filter_customers_statement(statement, *, tier: str | None, region: str | None):
    """Apply optional tier and address-region filters to a customer SELECT."""
    if tier:
        statement = statement.where(Customer.tier == tier)
    if region:
        statement = statement.where(customer_region_expression() == region)
    return statement


def create_customer_record(
    db: Session,
    *,
    name: str,
    email: str | None,
    phone: str | None,
    address: str | None,
    tier: str = "일반",
) -> Customer:
    """Create an active customer while allowing hidden emails to be reused."""
    normalized_email = email.strip().lower() if email and email.strip() else None
    if normalized_email:
        existing = db.scalar(
            visible_customers_statement().where(
                func.lower(Customer.email) == normalized_email
            )
        )
        if existing is not None:
            raise CustomerEmailConflict

        hidden_customer = db.scalar(
            select(Customer)
            .join(HiddenCustomer, HiddenCustomer.customer_id == Customer.customer_id)
            .where(func.lower(Customer.email) == normalized_email)
        )
        if hidden_customer is not None:
            # Reactivate the matching record to preserve the customers.email
            # unique constraint and retain its original customer/order links.
            hidden_customer.name = name.strip()
            hidden_customer.phone = phone or None
            hidden_customer.address = address or None
            hidden_customer.hidden_record = None
            db.commit()
            db.refresh(hidden_customer)
            return hidden_customer

    customer = Customer(
        name=name.strip(),
        email=normalized_email,
        phone=phone or None,
        address=address or None,
        tier=tier,
        created_at=datetime_now_iso(),
    )
    db.add(customer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CustomerEmailConflict from exc
    db.refresh(customer)
    return customer


def hide_customer_record(db: Session, customer: Customer) -> None:
    """Hide a customer without deleting the customer or associated orders."""
    hide_customer_records(db, [customer])


def hide_customer_records(db: Session, customers: list[Customer]) -> None:
    """Hide multiple customers while preserving their rows and order links."""
    for customer in customers:
        if customer.hidden_record is None:
            customer.hidden_record = HiddenCustomer()
    db.commit()


def datetime_now_iso() -> str:
    """Return a UTC ISO 8601 timestamp for a newly registered customer."""
    return datetime.now(timezone.utc).isoformat()
