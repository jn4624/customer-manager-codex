"""FastAPI application entry point for Customer Manager."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from database import init_db
from routers import auth, customers, dashboard, pages
from routers.auth import SessionExpiredError, clear_auth_cookie, set_auth_cookie


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create missing tables only; existing tables and rows are left intact.
    init_db()
    yield


app = FastAPI(title="Customer Manager API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(dashboard.router)
app.include_router(pages.router)


def is_browser_request(request: Request) -> bool:
    """Identify browser navigations and fetches, including JSON-accepting fetch()."""
    accept = request.headers.get("accept", "").lower()
    fetch_mode = request.headers.get("sec-fetch-mode", "").lower()
    fetch_dest = request.headers.get("sec-fetch-dest", "").lower()
    return bool(fetch_mode or fetch_dest or "text/html" in accept)


@app.middleware("http")
async def refresh_session_cookie(request: Request, call_next):
    response = await call_next(request)
    employee = getattr(request.state, "refresh_employee", None)
    if employee is not None:
        set_auth_cookie(response, employee)
    return response


@app.exception_handler(SessionExpiredError)
async def session_expired_handler(request: Request, _exc: SessionExpiredError):
    if not is_browser_request(request):
        response = JSONResponse(
            status_code=401,
            content={"detail": "세션이 만료되었습니다."},
        )
    else:
        response = RedirectResponse(url="/login?session_expired=true", status_code=303)
    clear_auth_cookie(response)
    return response


@app.exception_handler(StarletteHTTPException)
async def unauthorized_request_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401 and is_browser_request(request):
        response = RedirectResponse(url="/login?login_required=true", status_code=303)
        clear_auth_cookie(response)
        return response
    return await http_exception_handler(request, exc)


@app.get("/health")
def health():
    return {"status": "ok"}
