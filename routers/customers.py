"""Customer CRUD, search, filtering, pagination, and CSV export routes."""

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import Customer, Employee
from routers.auth import get_current_employee
from routers.customer_queries import (
    CustomerEmailConflict,
    create_customer_record,
    filter_customers_statement,
    hide_customer_record,
    search_customers_statement,
    visible_customers_statement,
)

router = APIRouter(prefix="/api/customers", tags=["고객"])


DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentEmployee = Annotated[Employee, Depends(get_current_employee)]


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tier: str = "일반"

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("고객 이름을 입력해 주세요.")
        return stripped


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = None
    address: str | None = None

    @field_validator("name")
    @classmethod
    def name_cannot_be_null(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("고객 이름을 입력해 주세요.")
        stripped = value.strip()
        if not stripped:
            raise ValueError("고객 이름을 입력해 주세요.")
        return stripped


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
def create_customer(
    payload: CustomerCreate,
    response: Response,
    db: DatabaseSession,
    _employee: CurrentEmployee,
):
    try:
        customer = create_customer_record(db, **payload.model_dump())
    except CustomerEmailConflict as exc:
        raise HTTPException(status_code=409, detail="이미 등록된 고객입니다.") from exc
    customer_position = db.scalar(
        select(func.count()).select_from(
            visible_customers_statement()
            .where(Customer.customer_id <= customer.customer_id)
            .subquery()
        )
    ) or 1
    response.headers["X-Customer-Page"] = str((customer_position + 19) // 20)
    return customer


@router.get("", response_model=list[CustomerRead])
def list_customers(
    db: DatabaseSession,
    _employee: CurrentEmployee,
    response: Response,
    q: str | None = Query(default=None, max_length=200),
    tier: str | None = Query(default=None, max_length=100),
    region: str | None = Query(default=None, max_length=100),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=20, le=20)] = 20,
):
    stmt = filter_customers_statement(
        search_customers_statement(visible_customers_statement(), q),
        tier=tier.strip() if tier and tier.strip() else None,
        region=region.strip() if region and region.strip() else None,
    )
    response.headers["X-Total-Count"] = str(
        db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    )
    return db.scalars(
        stmt.order_by(Customer.customer_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()


@router.get("/export.csv")
def export_customers(db: DatabaseSession, _employee: CurrentEmployee):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["customer_id", "name", "email", "phone", "address", "created_at", "tier"])
    for customer in db.scalars(visible_customers_statement().order_by(Customer.customer_id)):
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
def get_customer(customer_id: int, db: DatabaseSession, _employee: CurrentEmployee):
    customer = db.scalar(visible_customers_statement().where(Customer.customer_id == customer_id))
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return customer


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: DatabaseSession,
    _employee: CurrentEmployee,
):
    customer = db.scalar(visible_customers_statement().where(Customer.customer_id == customer_id))
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: DatabaseSession, _employee: CurrentEmployee):
    customer = db.scalar(visible_customers_statement().where(Customer.customer_id == customer_id))
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    try:
        hide_customer_record(db, customer)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="고객을 숨김 처리할 수 없습니다.") from exc
    return Response(status_code=204)
