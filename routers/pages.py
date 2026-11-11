"""Browser pages for authentication and the protected customer list."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Customer, Employee
from routers.auth import (
    SignupRequest,
    authenticate_employee,
    clear_auth_cookie,
    get_current_employee,
    get_optional_current_employee,
    register_employee,
    set_auth_cookie,
)

router = APIRouter(tags=["페이지"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


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
):
    customers = db.scalars(select(Customer).order_by(Customer.customer_id).limit(100)).all()
    return templates.TemplateResponse(
        request=request,
        name="customers.html",
        context={"user": employee, "customers": customers},
    )


@router.post("/logout", name="logout_form")
def logout_form():
    response = RedirectResponse(url="/login", status_code=303)
    clear_auth_cookie(response)
    return response
