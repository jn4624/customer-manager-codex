"""Browser pages for authentication and the protected customer list."""

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Customer, Employee, Order
from routers.auth import (
    SignupRequest,
    authenticate_employee,
    clear_auth_cookie,
    get_current_employee,
    get_optional_current_employee,
    register_employee,
    set_auth_cookie,
)
from routers.customers import CustomerUpdate
from routers.customer_queries import (
    customer_region_expression,
    filter_customers_statement,
    hide_customer_records,
    search_customers_statement,
    visible_customers_statement,
)

router = APIRouter(tags=["페이지"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", name="home_page")
def home_page(request: Request, db: Session = Depends(get_db)):
    employee = get_optional_current_employee(request, db)
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"user": employee},
    )


@router.get("/login", name="login_page")
def login_page(
    request: Request,
    db: Session = Depends(get_db),
    registered: bool = False,
    session_expired: bool = False,
    login_required: bool = False,
):
    if get_optional_current_employee(request, db):
        return RedirectResponse(url="/customers", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "registered": registered,
            "session_expired": session_expired,
            "login_required": login_required,
            "error": None,
        },
    )


@router.post("/login", name="login_form")
def login_form(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    try:
        employee = authenticate_employee(email, password, db)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "registered": False,
                "session_expired": False,
                "login_required": False,
                "error": exc.detail,
            },
            status_code=401,
        )
    response = RedirectResponse(url="/customers", status_code=303)
    set_auth_cookie(response, employee)
    return response


@router.get("/signup", name="signup_page")
def signup_page(request: Request, db: Session = Depends(get_db)):
    if get_optional_current_employee(request, db):
        return RedirectResponse(url="/customers", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={"user": None, "error": None, "name": "", "email": ""},
    )


@router.post("/signup", name="signup_form")
def signup_form(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    try:
        payload = SignupRequest(name=name, email=email, password=password)
        register_employee(payload, db)
    except ValidationError:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={
                "user": None,
                "error": "이름, 이메일 또는 비밀번호 형식을 확인해 주세요. 비밀번호는 8자 이상이어야 합니다.",
                "name": name,
                "email": email,
            },
            status_code=422,
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={"user": None, "error": exc.detail, "name": name, "email": email},
            status_code=409,
        )
    return RedirectResponse(url="/login?registered=true", status_code=303)


@router.get("/customers", name="customers_page")
def customers_page(
    request: Request,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=200),
    tier: str | None = Query(default=None, max_length=100),
    region: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
):
    search_q = q.strip() if q and q.strip() else ""
    visible_statement = visible_customers_statement()
    tier_options = [
        value
        for value in db.scalars(
            visible_statement.with_only_columns(Customer.tier)
            .distinct()
            .order_by(Customer.tier)
        ).all()
        if value
    ]
    region_expression = customer_region_expression()
    region_options = [
        value
        for value in db.scalars(
            visible_statement.with_only_columns(region_expression)
            .where(Customer.address.is_not(None))
            .distinct()
            .order_by(region_expression)
        ).all()
        if value
    ]
    selected_tier = tier if tier in tier_options else ""
    selected_region = region if region in region_options else ""
    statement = filter_customers_statement(
        search_customers_statement(visible_statement, search_q),
        tier=selected_tier,
        region=selected_region,
    )
    customer_count = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    page_count = max(1, (customer_count + 19) // 20)
    page = min(page, page_count)
    page_group_start = ((page - 1) // 10) * 10 + 1
    page_group_end = min(page_group_start + 9, page_count)
    page_numbers = list(range(page_group_start, page_group_end + 1))
    pagination_params = {
        key: value
        for key, value in (("q", search_q), ("tier", selected_tier), ("region", selected_region))
        if value
    }
    customers = db.scalars(
        statement
        .order_by(Customer.customer_id)
        .offset((page - 1) * 20)
        .limit(20)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="customers.html",
        context={
            "user": employee,
            "customers": customers,
            "page": page,
            "page_count": page_count,
            "page_numbers": page_numbers,
            "customer_count": customer_count,
            "search_q": search_q,
            "selected_tier": selected_tier,
            "selected_region": selected_region,
            "tier_options": tier_options,
            "region_options": region_options,
            "pagination_query": urlencode(pagination_params),
            "has_conditions": bool(search_q or selected_tier or selected_region),
            "previous_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < page_count else None,
            "previous_page_group": page_group_start - 10 if page_group_start > 1 else None,
            "next_page_group": page_group_start + 10 if page_group_end < page_count else None,
        },
    )


@router.post("/customers/hide-selected", name="hide_selected_customers_form")
def hide_selected_customers_form(
    customer_ids: list[int] = Form(default=[]),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    if not customer_ids:
        return RedirectResponse(url="/customers", status_code=303)
    customers = db.scalars(
        visible_customers_statement().where(Customer.customer_id.in_(set(customer_ids)))
    ).all()
    hide_customer_records(db, customers)
    return RedirectResponse(url="/customers", status_code=303)


@router.get("/customers/{customer_id}", name="customer_detail_page")
def customer_detail_page(
    request: Request,
    customer_id: int,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
    error: str | None = None,
):
    customer = db.scalar(
        visible_customers_statement().where(Customer.customer_id == customer_id)
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    order_history = db.scalars(
        select(Order)
        .options(joinedload(Order.product))
        .where(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc(), Order.order_id.desc())
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="customer_detail.html",
        context={
            "user": employee,
            "customer": customer,
            "order_history": order_history,
            "error": error,
        },
    )


@router.post("/customers/{customer_id}/edit", name="customer_edit_form")
def customer_edit_form(
    request: Request,
    customer_id: int,
    name: str = Form(),
    phone: str = Form(default=""),
    address: str = Form(default=""),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    customer = db.scalar(
        visible_customers_statement().where(Customer.customer_id == customer_id)
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    order_history = db.scalars(
        select(Order)
        .options(joinedload(Order.product))
        .where(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc(), Order.order_id.desc())
    ).all()
    try:
        payload = CustomerUpdate(name=name, phone=phone or None, address=address or None)
    except ValidationError:
        return templates.TemplateResponse(
            request=request,
            name="customer_detail.html",
            context={
                "user": employee,
                "customer": customer,
                "order_history": order_history,
                "error": "고객 이름을 입력해 주세요.",
            },
            status_code=422,
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    return RedirectResponse(url=f"/customers/{customer_id}", status_code=303)


@router.post("/logout", name="logout_form")
def logout_form():
    response = RedirectResponse(url="/login", status_code=303)
    clear_auth_cookie(response)
    return response
