"""FastAPI application entry point for Customer Manager."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import init_db
from routers import auth, customers, dashboard


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create missing tables only; existing tables and rows are left intact.
    init_db()
    yield


app = FastAPI(title="Customer Manager API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(dashboard.router)


@app.get("/")
def root():
    return {"service": "Customer Manager", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
