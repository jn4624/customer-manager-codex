"""JWT cookie authentication backed by the existing employees table."""

import os
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Annotated

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Employee

router = APIRouter(prefix="/api/auth", tags=["인증"])

APP_ENV = os.getenv("APP_ENV", "development").lower()
configured_jwt_secret = os.getenv("JWT_SECRET_KEY")
if APP_ENV == "production" and not configured_jwt_secret:
    raise RuntimeError("운영 환경에는 JWT_SECRET_KEY 환경 변수가 필요합니다.")
JWT_SECRET_KEY = configured_jwt_secret or token_urlsafe(48)
if len(JWT_SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError("JWT_SECRET_KEY는 UTF-8 기준 32바이트 이상이어야 합니다.")
JWT_ALGORITHM = "HS256"
JWT_TTL = timedelta(minutes=60)
COOKIE_NAME = "access_token"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", str(APP_ENV == "production")).lower() == "true"
if APP_ENV == "production" and not COOKIE_SECURE:
    raise RuntimeError("운영 환경에서는 COOKIE_SECURE=true 설정이 필요합니다.")
GENERIC_LOGIN_ERROR = "이메일 또는 비밀번호가 올바르지 않습니다."
DatabaseSession = Annotated[Session, Depends(get_db)]

# Use a bcrypt hash for unknown accounts too, keeping failure responses uniform.
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=8, max_length=72)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("이름을 입력해 주세요.")
        return value.strip()

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("비밀번호는 UTF-8 기준 72바이트 이하여야 합니다.")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("비밀번호 입력이 올바르지 않습니다.")
        return value


class SessionExpiredError(Exception):
    """Raised when a validly signed access cookie has expired."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str | bytes) -> bool:
    try:
        encoded_hash = password_hash.encode("utf-8") if isinstance(password_hash, str) else password_hash
        return bcrypt.checkpw(password.encode("utf-8"), encoded_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(employee: Employee) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(employee.employee_id),
        "name": employee.name,
        "iat": now,
        "exp": now + JWT_TTL,
    }
    return jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def set_auth_cookie(response: Response, employee: Employee) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_access_token(employee),
        max_age=int(JWT_TTL.total_seconds()),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )


def register_employee(payload: SignupRequest, db: Session) -> Employee:
    email = normalize_email(payload.email)
    existing = db.scalar(select(Employee).where(func.lower(Employee.email) == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    employee = Employee(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
    )
    db.add(employee)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.") from exc
    db.refresh(employee)
    return employee


def authenticate_employee(email: str, password: str, db: Session) -> Employee:
    normalized_email = normalize_email(email)
    employee = db.scalar(select(Employee).where(func.lower(Employee.email) == normalized_email))
    password_hash = employee.password_hash if employee and employee.password_hash else DUMMY_PASSWORD_HASH
    valid_password = verify_password(password, password_hash)
    if employee is None or employee.password_hash is None or not valid_password:
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    return employee


def _employee_from_cookie(request: Request, db: Session) -> Employee | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        employee_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None
    return db.get(Employee, employee_id)


def get_current_employee(request: Request, db: DatabaseSession) -> Employee:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    try:
        claims = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        employee_id = int(claims["sub"])
    except jwt.ExpiredSignatureError as exc:
        raise SessionExpiredError from exc
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.") from None

    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    expires_at = float(claims["exp"])
    seconds_remaining = expires_at - datetime.now(timezone.utc).timestamp()
    if 0 < seconds_remaining <= 5 * 60:
        request.state.refresh_employee = employee
    return employee


def get_optional_current_employee(request: Request, db: Session) -> Employee | None:
    return _employee_from_cookie(request, db)


@router.post("/signup", status_code=201)
def signup(payload: SignupRequest, db: DatabaseSession):
    employee = register_employee(payload, db)
    return {"message": "회원가입이 완료되었습니다.", "name": employee.name}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: DatabaseSession):
    employee = authenticate_employee(payload.email, payload.password, db)
    set_auth_cookie(response, employee)
    return {"employee_id": employee.employee_id, "name": employee.name}


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_auth_cookie(response)
    return response
