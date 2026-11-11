"""Sales dashboard routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import Customer, Employee, Order
from routers.auth import get_current_employee

router = APIRouter(prefix="/api/dashboard", tags=["대시보드"])


DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentEmployee = Annotated[Employee, Depends(get_current_employee)]


@router.get("/sales")
def sales_dashboard(db: DatabaseSession, _employee: CurrentEmployee):
    row = db.execute(
        select(func.coalesce(func.sum(Order.total_amount), 0), func.count(Order.order_id))
    ).one()
    customer_count = db.scalar(select(func.count(Customer.customer_id))) or 0
    return {
        "revenue": float(row[0]),
        "order_count": int(row[1]),
        "customer_count": int(customer_count),
    }
