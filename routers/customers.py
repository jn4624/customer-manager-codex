"""Customer CRUD, search, filtering, pagination, and CSV export routes."""

import csv
import io
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Customer

router = APIRouter(prefix="/api/customers", tags=["고객"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DatabaseSession = Annotated[Session, Depends(get_db)]


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tier: str = "일반"


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tier: str | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    name: str
    email: str | None
    phone: str | None
    address: str | None
    created_at: str
    tier: str


@router.post("", response_model=CustomerRead, status_code=201)
def create_customer(payload: CustomerCreate, db: DatabaseSession):
    customer = Customer(
        **payload.model_dump(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(customer)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(customer)
    return customer


@router.get("", response_model=list[CustomerRead])
def list_customers(
    db: DatabaseSession,
    q: str | None = None,
    tier: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    stmt = select(Customer)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.phone.ilike(pattern),
            )
        )
    if tier:
        stmt = stmt.where(Customer.tier == tier)
    return db.scalars(
        stmt.order_by(Customer.customer_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()


@router.get("/export.csv")
def export_customers(db: DatabaseSession):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["customer_id", "name", "email", "phone", "address", "created_at", "tier"])
    for customer in db.scalars(select(Customer).order_by(Customer.customer_id)):
        writer.writerow(
            [
                customer.customer_id,
                customer.name,
                customer.email or "",
                customer.phone or "",
                customer.address or "",
                customer.created_at,
                customer.tier,
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="customers.csv"'},
    )


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: DatabaseSession):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return customer


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: int, payload: CustomerUpdate, db: DatabaseSession):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: DatabaseSession):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    db.delete(customer)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="주문 등 연결된 데이터가 있어 삭제할 수 없습니다.",
        ) from exc
    return Response(status_code=204)
